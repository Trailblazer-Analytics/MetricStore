"""MetricService — all business logic for Metric and MetricVersion operations."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from metricstore.models.metric import Metric
from metricstore.models.metric_collection import MetricCollection
from metricstore.models.metric_version import MetricVersion
from metricstore.schemas.metric import MetricCreate, MetricUpdate


class MetricService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_metric(self, data: MetricCreate) -> Metric:
        """Create a metric and auto-version it as v1. Raises 409 if name exists."""
        # Uniqueness check
        existing = await self.session.scalar(
            select(Metric.id).where(Metric.name == data.name)
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A metric named '{data.name}' already exists.",
            )

        metric = Metric(**data.model_dump())
        self.session.add(metric)
        await self.session.flush()  # populate metric.id before version snapshot

        version = MetricVersion(
            metric_id=metric.id,
            version_number=1,
            snapshot=self._build_snapshot(metric),
            change_summary="Initial version",
        )
        self.session.add(version)
        await self.session.commit()
        await self.session.refresh(metric)
        return metric

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_metric(self, metric_id: UUID) -> Metric:
        """Fetch by PK. Raises 404 if not found."""
        metric = await self.session.get(Metric, metric_id)
        if metric is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metric '{metric_id}' not found.",
            )
        return metric

    async def get_metric_by_name(self, name: str) -> Metric:
        """Fetch by exact name. Raises 404 if not found."""
        metric = await self.session.scalar(select(Metric).where(Metric.name == name))
        if metric is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metric '{name}' not found.",
            )
        return metric

    async def list_metrics(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
        metric_type: str | None = None,
        owner: str | None = None,
        collection_id: UUID | None = None,
    ) -> tuple[list[Metric], int]:
        """Return (metrics, total) for the given filter set."""
        query = select(Metric)
        count_query = select(func.count()).select_from(Metric)

        # ── Filters ───────────────────────────────────────────────────────────
        if search:
            # Use PostgreSQL full-text search when the term contains only
            # word characters; fall back to ILIKE for wildcard-like inputs.
            if search.replace(" ", "").isalnum():
                ts_query = func.plainto_tsquery("english", search)
                ts_vector = func.to_tsvector(
                    "english",
                    func.coalesce(Metric.name, "")
                    + text("' '")
                    + func.coalesce(Metric.description, ""),
                )
                fts_filter = ts_vector.op("@@")(ts_query)
                query = query.where(fts_filter)
                count_query = count_query.where(fts_filter)
            else:
                pattern = f"%{search}%"
                ilike_filter = Metric.name.ilike(pattern) | Metric.description.ilike(
                    pattern
                )
                query = query.where(ilike_filter)
                count_query = count_query.where(ilike_filter)

        if tags:
            # && = array overlap: metric has at least one of the given tags
            tags_filter = Metric.tags.op("&&")(tags)
            query = query.where(tags_filter)
            count_query = count_query.where(tags_filter)

        if status:
            query = query.where(Metric.status == status)
            count_query = count_query.where(Metric.status == status)

        if metric_type:
            query = query.where(Metric.metric_type == metric_type)
            count_query = count_query.where(Metric.metric_type == metric_type)

        if owner:
            query = query.where(Metric.owner == owner)
            count_query = count_query.where(Metric.owner == owner)

        if collection_id:
            query = query.join(
                MetricCollection,
                MetricCollection.metric_id == Metric.id,
            ).where(MetricCollection.collection_id == collection_id)
            count_query = count_query.join(
                MetricCollection,
                MetricCollection.metric_id == Metric.id,
            ).where(MetricCollection.collection_id == collection_id)

        # ── Total count (before pagination) ───────────────────────────────────
        total: int = await self.session.scalar(count_query) or 0

        # ── Pagination ────────────────────────────────────────────────────────
        offset = (page - 1) * page_size
        query = query.order_by(Metric.updated_at.desc()).offset(offset).limit(page_size)

        result = await self.session.scalars(query)
        return list(result.all()), total

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_metric(self, metric_id: UUID, data: MetricUpdate) -> Metric:
        """
        Apply a partial update and create a new version snapshot.
        Only fields present in data.model_fields_set are written.
        """
        metric = await self.get_metric(metric_id)

        # If renaming, check the new name isn't taken
        if "name" in data.model_fields_set and data.name != metric.name:
            taken = await self.session.scalar(
                select(Metric.id).where(Metric.name == data.name)
            )
            if taken:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A metric named '{data.name}' already exists.",
                )

        for field in data.model_fields_set:
            setattr(metric, field, getattr(data, field))

        # Determine next version number
        max_version: int = (
            await self.session.scalar(
                select(func.max(MetricVersion.version_number)).where(
                    MetricVersion.metric_id == metric_id
                )
            )
            or 0
        )

        version = MetricVersion(
            metric_id=metric.id,
            version_number=max_version + 1,
            snapshot=self._build_snapshot(metric),
            change_summary=(
                f"Updated fields: {', '.join(sorted(data.model_fields_set))}"
            ),
        )
        self.session.add(version)
        await self.session.commit()
        await self.session.refresh(metric)
        return metric

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_metric(self, metric_id: UUID) -> None:
        """Delete metric (cascades to versions and collection links). Raises 404."""
        metric = await self.get_metric(metric_id)
        await self.session.delete(metric)
        await self.session.commit()

    # ── Versions ──────────────────────────────────────────────────────────────

    async def get_versions(self, metric_id: UUID) -> list[MetricVersion]:
        """Return all versions for a metric, newest first. Raises 404."""
        await self.get_metric(metric_id)  # validate existence
        result = await self.session.scalars(
            select(MetricVersion)
            .where(MetricVersion.metric_id == metric_id)
            .order_by(MetricVersion.version_number.desc())
        )
        return list(result.all())

    async def get_version(self, metric_id: UUID, version_number: int) -> MetricVersion:
        """Return a specific version. Raises 404 if metric or version not found."""
        await self.get_metric(metric_id)  # validate metric exists
        version = await self.session.scalar(
            select(MetricVersion).where(
                MetricVersion.metric_id == metric_id,
                MetricVersion.version_number == version_number,
            )
        )
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(f"Version {version_number} of metric '{metric_id}' not found."),
            )
        return version

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_snapshot(self, metric: Metric) -> dict:
        """
        Serialize the current metric state to a JSON-compatible dict.
        Excludes id, created_at, and updated_at (identity / audit fields).
        """
        exclude = {"id", "created_at", "updated_at", "versions", "collection_links"}
        snapshot: dict = {}
        for col in metric.__table__.columns:
            if col.key in exclude:
                continue
            val = getattr(metric, col.key)
            # Coerce enum values to their string form for JSON
            if hasattr(val, "value"):
                val = val.value
            snapshot[col.key] = val
        return snapshot
