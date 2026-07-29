"""Ingestion schema — SyncRun, SyncCheckpoint, TimelineEvent, DataQualityReport,
ProviderRefIndex (docs/roadmap.md Milestone 5, docs/database_schema.md Entity Expansion Matrix)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-25
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SCHEMA = "ingestion"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("sport_code", sa.String(32), nullable=False, index=True),
        sa.Column("entity_kind", sa.String(32), nullable=False, index=True),
        sa.Column("scope_key", sa.String(200), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(1000), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "sync_checkpoints",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("sport_code", sa.String(32), nullable=False, index=True),
        sa.Column("entity_kind", sa.String(32), nullable=False, index=True),
        sa.Column("scope_key", sa.String(200), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor", sa.String(500), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("sport_code", "entity_kind", "scope_key", name="uq_sync_checkpoint_scope"),
        schema=SCHEMA,
    )

    op.create_table(
        "timeline_events",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("event_type", sa.String(32), nullable=False, index=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("actor", sa.String(64), nullable=False, server_default="ingestion"),
        sa.Column("sport_code", sa.String(32), nullable=True, index=True),
        sa.Column("entity_kind", sa.String(32), nullable=True, index=True),
        sa.Column("entity_id", sa.String(128), nullable=True, index=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )

    op.create_table(
        "data_quality_reports",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("sport_code", sa.String(32), nullable=False, index=True),
        sa.Column("entity_kind", sa.String(32), nullable=False, index=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("completeness_pct", sa.Float(), nullable=True),
        sa.Column("consistency_pct", sa.Float(), nullable=True),
        sa.Column("freshness_score", sa.Float(), nullable=True),
        sa.Column("accuracy_pct", sa.Float(), nullable=True),
        sa.Column("validity_pct", sa.Float(), nullable=True),
        sa.Column("reliability_score", sa.Float(), nullable=True),
        sa.Column("coverage_pct", sa.Float(), nullable=True),
        sa.Column("provider_quality_score", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("issues", sa.JSON(), nullable=False, server_default="[]"),
        schema=SCHEMA,
    )

    op.create_table(
        "provider_ref_index",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("provider", sa.String(64), nullable=False, index=True),
        sa.Column("external_id", sa.String(200), nullable=False, index=True),
        sa.Column("entity_kind", sa.String(32), nullable=False, index=True),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.UniqueConstraint("provider", "external_id", "entity_kind", name="uq_provider_ref_index"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in ("provider_ref_index", "data_quality_reports", "timeline_events", "sync_checkpoints", "sync_runs"):
        op.drop_table(table, schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
