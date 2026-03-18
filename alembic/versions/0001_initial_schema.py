"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-17

Creates all core tables for MetricStore v0.1:
  - collections
  - metrics          (with GIN index on tags + tsvector FTS index)
  - metric_versions  (immutable audit trail)
  - metric_collections (many-to-many join table)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ── Revision identifiers ──────────────────────────────────────────────────────
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Enum types ────────────────────────────────────────────────────────────
    metric_type_enum = postgresql.ENUM(
        "simple",
        "derived",
        "cumulative",
        "conversion",
        name="metric_type_enum",
    )
    metric_type_enum.create(op.get_bind(), checkfirst=True)

    metric_status_enum = postgresql.ENUM(
        "active",
        "draft",
        "deprecated",
        name="metric_status_enum",
    )
    metric_status_enum.create(op.get_bind(), checkfirst=True)

    # ── collections ───────────────────────────────────────────────────────────
    op.create_table(
        "collections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # ── metrics ───────────────────────────────────────────────────────────────
    op.create_table(
        "metrics",
        # identity
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        # formula / sql
        sa.Column("formula", sa.Text(), nullable=True),
        sa.Column("sql_expression", sa.Text(), nullable=True),
        # classification
        sa.Column(
            "metric_type",
            sa.Enum(
                "simple",
                "derived",
                "cumulative",
                "conversion",
                name="metric_type_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="simple",
        ),
        # time dimensions
        sa.Column(
            "time_grains",
            postgresql.ARRAY(sa.String(50)),
            nullable=False,
            server_default=sa.text("ARRAY['day','week','month']::varchar(50)[]"),
        ),
        sa.Column(
            "default_time_grain",
            sa.String(50),
            nullable=False,
            server_default="day",
        ),
        # semantic metadata
        sa.Column(
            "dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # ownership
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("owner_email", sa.String(255), nullable=True),
        # source lineage
        sa.Column("source_platform", sa.String(100), nullable=True),
        sa.Column("source_ref", sa.String(500), nullable=True),
        # taxonomy
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String(100)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar(100)[]"),
        ),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # lifecycle
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "draft",
                "deprecated",
                name="metric_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("deprecated_reason", sa.Text(), nullable=True),
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        # timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # B-tree index on name (supports equality and prefix lookups)
    op.create_index("ix_metrics_name", "metrics", ["name"])

    # GIN index on tags array (supports @> containment and ANY() queries)
    op.create_index(
        "ix_metric_tags_gin",
        "metrics",
        ["tags"],
        postgresql_using="gin",
    )

    # GIN index on tsvector for full-text search across name + description
    op.create_index(
        "ix_metric_fts_gin",
        "metrics",
        [
            sa.text(
                "to_tsvector('english',"
                " coalesce(name,'') || ' ' || coalesce(description,''))"
            )
        ],
        postgresql_using="gin",
    )

    # ── metric_versions ───────────────────────────────────────────────────────
    op.create_table(
        "metric_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("metric_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["metric_id"], ["metrics.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "metric_id", "version_number", name="uq_metric_version"
        ),
    )
    op.create_index("ix_metric_versions_metric_id", "metric_versions", ["metric_id"])

    # ── metric_collections ────────────────────────────────────────────────────
    op.create_table(
        "metric_collections",
        sa.Column("metric_id", sa.UUID(), nullable=False),
        sa.Column("collection_id", sa.UUID(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["metric_id"], ["metrics.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("metric_id", "collection_id"),
    )


def downgrade() -> None:
    op.drop_table("metric_collections")

    op.drop_index("ix_metric_versions_metric_id", table_name="metric_versions")
    op.drop_table("metric_versions")

    op.drop_index("ix_metric_fts_gin", table_name="metrics")
    op.drop_index("ix_metric_tags_gin", table_name="metrics")
    op.drop_index("ix_metrics_name", table_name="metrics")
    op.drop_table("metrics")

    op.drop_table("collections")

    sa.Enum(name="metric_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="metric_type_enum").drop(op.get_bind(), checkfirst=True)
