"""MetricVersion ORM model — immutable audit trail for Metric changes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from metricstore.models.base import Base

if TYPE_CHECKING:
    from metricstore.models.metric import Metric


class MetricVersion(Base):
    __tablename__ = "metric_versions"

    # ── Primary key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Foreign key ───────────────────────────────────────────────────────────
    metric_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("metrics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Version data ──────────────────────────────────────────────────────────
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[str | None] = mapped_column(String(255))

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    metric: Mapped[Metric] = relationship("Metric", back_populates="versions")

    # ── Constraints ───────────────────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint("metric_id", "version_number", name="uq_metric_version"),
    )

    def __repr__(self) -> str:
        return f"<MetricVersion metric_id={self.metric_id} v={self.version_number}>"
