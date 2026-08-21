"""Gemini Prediction Reasoning Engine — prediction_context_reviews

New table, not a blob column on `predictions`: a distinct, independently-versioned audit record
(one row per prediction, overwritten on re-review), matching how `model_evaluations`/`sync_runs`
are already separated from their parent tables in this schema rather than crammed into an opaque
JSON blob on an existing row. `unique=True` on `prediction_id` is a real invariant — a prediction
has at most one *current* contextual review.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

SCHEMA = "predictions"


def upgrade() -> None:
    op.create_table(
        "prediction_context_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("prediction_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.predictions.id"), nullable=False, unique=True),
        sa.Column("market_key", sa.String(200), nullable=False),
        sa.Column("base_selection", sa.String(200), nullable=False),
        sa.Column("base_probability", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("statistical_baseline", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("overall_assessment", sa.Text(), nullable=False, server_default=""),
        sa.Column("contextual_assessment", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("supporting_factors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("risk_factors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("missing_context", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("reconsideration_direction", sa.String(32), nullable=True),
        sa.Column("reconsideration_reason", sa.Text(), nullable=True),
        sa.Column("material_change", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("context_confidence_level", sa.String(16), nullable=False),
        sa.Column("context_confidence_score", sa.Float(), nullable=False),
        sa.Column("evidence_quality", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("prediction_cutoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    # `prediction_id`'s `unique=True` above already creates a unique index covering lookups by
    # prediction — only `market_key` needs its own separate (non-unique) index.
    op.create_index(
        "ix_prediction_context_reviews_market_key", "prediction_context_reviews", ["market_key"], schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_prediction_context_reviews_market_key", table_name="prediction_context_reviews", schema=SCHEMA)
    op.drop_table("prediction_context_reviews", schema=SCHEMA)
