"""Prediction Intelligence Platform schema (Milestone 9, docs/database_schema.md §4,
docs/prediction_markets.md, docs/decisions.md).

Runs on every dialect (like migrations 0015-0017) — plain CREATE TABLE/INDEX statements the
SQLite fast-test engine handles identically; the fast test suite itself builds these tables via
``Base.metadata.create_all`` rather than running this migration, so this file is exercised
against live Postgres only (docs/decisions.md ADR-024's offline-SQL + MCP `execute_sql`
application pattern).

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-26
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

SCHEMA = "predictions"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "prediction_markets",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("market_key", sa.String(200), nullable=False, unique=True, index=True),
        sa.Column("sport_code", sa.String(32), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, index=True),
        sa.Column("market_kind", sa.String(32), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("min_historical_window_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required_data_quality", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("explainability_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("confidence_threshold", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft", index=True),
        sa.Column("owner", sa.String(200), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(200), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "feature_market_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "market_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.prediction_markets.id"), nullable=False, index=True
        ),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence_contribution", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.UniqueConstraint("market_id", "feature_key", name="uq_feature_market_mapping"),
        schema=SCHEMA,
    )

    op.create_table(
        "models",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "market_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.prediction_markets.id"), nullable=False, index=True
        ),
        sa.Column("model_key", sa.String(200), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("algorithm", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="candidate", index=True),
        sa.Column("training_dataset_ref", sa.String(500), nullable=True),
        sa.Column("calibration_ref", sa.String(500), nullable=True),
        sa.Column("approved_by", sa.String(200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("model_key", "version", name="uq_model_key_version"),
        schema=SCHEMA,
    )

    op.create_table(
        "predictions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "market_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.prediction_markets.id"), nullable=False, index=True
        ),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=False, index=True),
        sa.Column("subject_ref", sa.String(200), nullable=False, index=True),
        sa.Column("value", sa.String(200), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("confidence", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("explanation", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("feature_snapshot", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft", index=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_freshness", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "prediction_outcomes",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "prediction_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.predictions.id"), nullable=False, unique=True, index=True
        ),
        sa.Column("actual_value", sa.String(200), nullable=False),
        sa.Column("error", sa.Float(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "model_evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=False, index=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("calibration_report", sa.JSON(), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )

    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "market_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.prediction_markets.id"), nullable=False, index=True
        ),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("decision", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "prediction_audits",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("action", sa.String(32), nullable=False, index=True),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("prediction_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.predictions.id"), nullable=True, index=True),
        sa.Column("market_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.prediction_markets.id"), nullable=True),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.models.id"), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "prediction_audits",
        "experiments",
        "model_evaluations",
        "prediction_outcomes",
        "predictions",
        "models",
        "feature_market_mappings",
        "prediction_markets",
    ):
        op.drop_table(table, schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
