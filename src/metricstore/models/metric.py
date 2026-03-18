"""Metric ORM model — core entity of MetricStore."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from metricstore.models.base import Base


class MetricType(str, enum.Enum):
    simple = "simple"
    derived = "derived"
    cumulative = "cumulative"
    conversion = "conversion"


class MetricStatus(str, enum.Enum):
    active = "active"
    draft = "draft"
    deprecated = "deprecated"


class Metric(Base):
    __tablename__ = "metrics"

    # ── Primary key ───────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Identity fields ───────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    # ── Formula / SQL ─────────────────────────────────────────────────────────
    formula: Mapped[str | None] = mapped_column(Text)
    sql_expression: Mapped[str | None] = mapped_column(Text)

    # ── Classification ────────────────────────────────────────────────────────
    metric_type: Mapped[MetricType] = mapped_column(
        Enum(MetricType, name="metric_type_enum"),
        nullable=False,
        default=MetricType.simple,
        server_default=MetricType.simple.value,
    )

    # ── Time dimensions ───────────────────────────────────────────────────────
    time_grains: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)),
        nullable=False,
        default=lambda: ["day", "week", "month"],
        server_default=text("ARRAY['day','week','month']::varchar(50)[]"),
    )
    default_time_grain: Mapped[str] = mapped_column(
        String(50), nullable=False, default="day", server_default="day"
    )

    # ── Semantic metadata ─────────────────────────────────────────────────────
    dimensions: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    filters: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    # ── Ownership ────────────────────────────────────────────────────────────
    owner: Mapped[str | None] = mapped_column(String(255))
    owner_email: Mapped[str | None] = mapped_column(String(255))

    # ── Source lineage ────────────────────────────────────────────────────────
    source_platform: Mapped[str | None] = mapped_column(String(100))
    source_ref: Mapped[str | None] = mapped_column(String(500))

    # ── Taxonomy / discovery ──────────────────────────────────────────────────
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)),
        nullable=False,
        default=list,
        server_default=text("ARRAY[]::varchar(100)[]"),
    )
    meta: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    status: Mapped[MetricStatus] = mapped_column(
        Enum(MetricStatus, name="metric_status_enum"),
        nullable=False,
        default=MetricStatus.active,
        server_default=MetricStatus.active.value,
    )
    deprecated_reason: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    versions: Mapped[list[MetricVersion]] = relationship(
        "MetricVersion", back_populates="metric", cascade="all, delete-orphan"
    )
    collection_links: Mapped[list[MetricCollection]] = relationship(
        "MetricCollection", back_populates="metric", cascade="all, delete-orphan"
    )

    # ── Table-level indexes ───────────────────────────────────────────────────
    __table_args__ = (
        # GIN index for efficient array containment queries on tags
        Index("ix_metric_tags_gin", "tags", postgresql_using="gin"),
        # GIN index for full-text search across name + description
        Index(
            "ix_metric_fts_gin",
            text(
                "to_tsvector('english',"
                " coalesce(name,'') || ' ' || coalesce(description,''))"
            ),
            postgresql_using="gin",
        ),
    )

    def __repr__(self) -> str:
        return f"<Metric id={self.id} name={self.name!r}>"
