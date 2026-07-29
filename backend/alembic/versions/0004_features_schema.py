"""Features schema — Feature Intelligence Platform offline store (docs/database_schema.md §3,
docs/feature_catalog.md)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-25
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SCHEMA = "features"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "feature_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("feature_key", sa.String(200), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sport_code", sa.String(32), nullable=False, index=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("data_type", sa.String(16), nullable=False),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("expected_range_low", sa.Float(), nullable=True),
        sa.Column("expected_range_high", sa.Float(), nullable=True),
        sa.Column("update_frequency", sa.String(64), nullable=False, server_default="unspecified"),
        sa.Column("online_ttl_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft", index=True),
        sa.Column("dependencies", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("leakage_reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "feature_definition_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, index=True),
        schema=SCHEMA,
    )

    op.create_table(
        "feature_values_offline",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False, index=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False, server_default="[]"),
        schema=SCHEMA,
    )

    op.create_table(
        "feature_lineage",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("depends_on_feature_key", sa.String(200), nullable=False, index=True),
        sa.UniqueConstraint("feature_key", "depends_on_feature_key", name="uq_feature_lineage_edge"),
        schema=SCHEMA,
    )

    op.create_table(
        "feature_drift_reports",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("window", sa.String(32), nullable=False),
        sa.Column("drift_score", sa.Float(), nullable=False),
        sa.Column("method", sa.String(64), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, index=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "feature_drift_reports",
        "feature_lineage",
        "feature_values_offline",
        "feature_definition_versions",
        "feature_definitions",
    ):
        op.drop_table(table, schema=SCHEMA)

    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
