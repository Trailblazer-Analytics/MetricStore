"""MetricCollection — association table linking Metrics to Collections."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from metricstore.models.base import Base


class MetricCollection(Base):
    __tablename__ = "metric_collections"

    # ── Composite primary key ─────────────────────────────────────────────────
    metric_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("metrics.id", ondelete="CASCADE"),
        primary_key=True,
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # ── Timestamp ────────────────────────────────────────────────────────────
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    metric: Mapped[Metric] = relationship("Metric", back_populates="collection_links")
    collection: Mapped[Collection] = relationship(
        "Collection", back_populates="metric_links"
    )

    def __repr__(self) -> str:
        return (
            f"<MetricCollection metric_id={self.metric_id}"
            f" collection_id={self.collection_id}>"
        )
