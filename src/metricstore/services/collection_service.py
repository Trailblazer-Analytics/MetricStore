"""CollectionService — business logic for Collection and membership operations."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from metricstore.models.collection import Collection
from metricstore.models.metric import Metric
from metricstore.models.metric_collection import MetricCollection
from metricstore.schemas.collection import CollectionCreate


class CollectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_collection(self, data: CollectionCreate) -> Collection:
        """Create a collection. Raises 409 if the name is already taken."""
        existing = await self.session.scalar(
            select(Collection.id).where(Collection.name == data.name)
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A collection named '{data.name}' already exists.",
            )
        collection = Collection(**data.model_dump())
        self.session.add(collection)
        await self.session.commit()
        await self.session.refresh(collection)
        return collection

    # ── Read ──────────────────────────────────────────────────────────────────

    async def list_collections(self) -> list[Collection]:
        """Return all collections ordered by name."""
        result = await self.session.scalars(
            select(Collection).order_by(Collection.name)
        )
        return list(result.all())

    async def get_collection(self, collection_id: UUID) -> Collection:
        """Fetch by PK. Raises 404 if not found."""
        collection = await self.session.get(Collection, collection_id)
        if collection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection '{collection_id}' not found.",
            )
        return collection

    async def get_metric_count(self, collection_id: UUID) -> int:
        """Return the number of metrics in a collection."""
        return await self.session.scalar(
            select(func.count())
            .select_from(MetricCollection)
            .where(MetricCollection.collection_id == collection_id)
        ) or 0

    # ── Membership management ─────────────────────────────────────────────────

    async def add_metric_to_collection(
        self, collection_id: UUID, metric_id: UUID
    ) -> None:
        """Add a metric to a collection. Raises 404 for either entity, 409 if already linked."""
        # Validate both entities exist
        await self.get_collection(collection_id)
        metric = await self.session.get(Metric, metric_id)
        if metric is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metric '{metric_id}' not found.",
            )

        # Idempotency: check for existing link
        existing = await self.session.scalar(
            select(MetricCollection).where(
                MetricCollection.collection_id == collection_id,
                MetricCollection.metric_id == metric_id,
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Metric is already in this collection.",
            )

        self.session.add(
            MetricCollection(collection_id=collection_id, metric_id=metric_id)
        )
        await self.session.commit()

    async def remove_metric_from_collection(
        self, collection_id: UUID, metric_id: UUID
    ) -> None:
        """Remove a metric from a collection. Raises 404 if the link doesn't exist."""
        link = await self.session.scalar(
            select(MetricCollection).where(
                MetricCollection.collection_id == collection_id,
                MetricCollection.metric_id == metric_id,
            )
        )
        if link is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Metric is not in this collection.",
            )
        await self.session.delete(link)
        await self.session.commit()
