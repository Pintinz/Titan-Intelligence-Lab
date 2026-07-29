"""Enterprise ML Platform schema (Milestone 9.1, docs/decisions.md ADR-053) — 7 new tables under
the existing `predictions` schema (Dataset Platform, Training Platform, Calibration Reporting,
SHAP feature-importance snapshots, Model Monitoring latency samples, Retraining Scheduler
decisions, Model Serving artifact registry) plus 9 new nullable columns on `models` recording
each `ModelDefinition`'s framework/algorithm-training provenance additively.

No GRANT step needed here: migration 0020's `ALTER DEFAULT PRIVILEGES IN SCHEMA predictions GRANT
ALL ON TABLES TO anon, authenticated` already covers every table created in this schema *after*
it ran (that's what "default privileges" means) — the ADR-027 gap that bit migrations 0018/0019
literally cannot recur for a schema that already has this default set. RLS for these 7 tables is
migration 0024, following the same schema-then-RLS split as 0018/0019 -> 0021.

Same dialect posture as 0018: plain CREATE TABLE/ALTER TABLE, runs on every dialect (SQLite fast
tests build these via `Base.metadata.create_all`, not this file — this file is exercised against
live Postgres only, docs/decisions.md ADR-024).

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-26
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

SCHEMA = "predictions"


def upgrade() -> None:
    op.add_column("models", sa.Column("framework", sa.String(32), nullable=True), schema=SCHEMA)
    op.add_column("models", sa.Column("dataset_version", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("models", sa.Column("feature_versions", sa.JSON(), nullable=False, server_default="{}"), schema=SCHEMA)
    op.add_column("models", sa.Column("training_run_ref", sa.String(500), nullable=True), schema=SCHEMA)
    op.add_column("models", sa.Column("calibration_report_ref", sa.String(500), nullable=True), schema=SCHEMA)
    op.add_column("models", sa.Column("feature_importance_ref", sa.String(500), nullable=True), schema=SCHEMA)
    op.add_column("models", sa.Column("artifact_ref", sa.String(500), nullable=True), schema=SCHEMA)
    op.add_column("models", sa.Column("deployment_mode", sa.String(16), nullable=True), schema=SCHEMA)
    op.add_column("models", sa.Column("trained_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)

    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("market_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.prediction_markets.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, index=True),
        sa.Column("samples", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("statistics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("lineage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("quality_issues", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("market_id", "version", name="uq_dataset_market_version"),
        schema=SCHEMA,
    )

    op.create_table(
        "training_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("market_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.prediction_markets.id"), nullable=False, index=True),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=True, index=True),
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.datasets.id"), nullable=True, index=True),
        sa.Column("algorithm", sa.String(64), nullable=False),
        sa.Column("framework", sa.String(32), nullable=False),
        sa.Column("train_metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("test_metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("feature_order", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("selected_features", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("samples_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outliers_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "calibration_reports",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=False, index=True),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("expected_calibration_error", sa.Float(), nullable=False),
        sa.Column("brier_score", sa.Float(), nullable=False),
        sa.Column("reliability_curve", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "feature_importance_reports",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=False, index=True),
        sa.Column("global_importance", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "latency_samples",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("market_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.prediction_markets.id"), nullable=False, index=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, index=True),
        schema=SCHEMA,
    )

    op.create_table(
        "retraining_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("market_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.prediction_markets.id"), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column("trigger_reason", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "model_artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=False, index=True),
        sa.Column("storage_ref", sa.String(500), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "model_artifacts",
        "retraining_jobs",
        "latency_samples",
        "feature_importance_reports",
        "calibration_reports",
        "training_runs",
        "datasets",
    ):
        op.drop_table(table, schema=SCHEMA)

    for column in (
        "trained_at",
        "deployment_mode",
        "artifact_ref",
        "feature_importance_ref",
        "calibration_report_ref",
        "training_run_ref",
        "feature_versions",
        "dataset_version",
        "framework",
    ):
        op.drop_column("models", column, schema=SCHEMA)
