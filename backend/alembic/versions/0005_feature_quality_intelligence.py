"""Feature Quality Intelligence — validation reports, computation logs, consumers, usage,
and a source_provider_key column on feature_definitions (docs/feature_catalog.md,
Feature Quality Intelligence)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-25
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SCHEMA = "features"


def upgrade() -> None:
    op.add_column(
        "feature_definitions", sa.Column("source_provider_key", sa.String(64), nullable=True), schema=SCHEMA
    )

    op.create_table(
        "feature_validation_reports",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("freshness_score", sa.Float(), nullable=True),
        sa.Column("reliability_score", sa.Float(), nullable=True),
        sa.Column("completeness_score", sa.Float(), nullable=True),
        sa.Column("missing_pct", sa.Float(), nullable=True),
        sa.Column("outlier_pct", sa.Float(), nullable=True),
        sa.Column("null_pct", sa.Float(), nullable=True),
        sa.Column("invalid_pct", sa.Float(), nullable=True),
        sa.Column("duplicate_pct", sa.Float(), nullable=True),
        sa.Column("coverage_pct", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False, server_default="[]"),
        schema=SCHEMA,
    )

    op.create_table(
        "feature_computation_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("memory_bytes", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "feature_consumers",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("consumer_key", sa.String(200), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("feature_key", "consumer_key", name="uq_feature_consumer"),
        schema=SCHEMA,
    )

    op.create_table(
        "feature_usage_records",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("window_key", sa.String(16), nullable=False, index=True),
        sa.Column("read_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("feature_key", "window_key", name="uq_feature_usage_window"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in ("feature_usage_records", "feature_consumers", "feature_computation_logs", "feature_validation_reports"):
        op.drop_table(table, schema=SCHEMA)

    op.drop_column("feature_definitions", "source_provider_key", schema=SCHEMA)
