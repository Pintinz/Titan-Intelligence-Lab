"""Market outcome registry fields

Additive-only (Milestone 9.2 — Market Registry & Prediction Domain Normalization, Phase 1): adds
`predictions.prediction_markets.outcome_type`/`allowed_values`/`resolver_key`/
`gemini_prompt_template`, and a new `legacy_unresolved` value for the existing
`predictions.predictions.status` column (no schema change needed for that — it's a plain string
column, not a DB-level enum). See modules/predictions/domain/market_outcome_registry.py.

No data migration: existing `MarketDefinition` rows get NULL for all four new columns, and no
existing `Prediction` row's `status` is touched by this migration.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

SCHEMA = "predictions"


def upgrade() -> None:
    op.add_column("prediction_markets", sa.Column("outcome_type", sa.String(32), nullable=True), schema=SCHEMA)
    op.add_column("prediction_markets", sa.Column("allowed_values", sa.JSON(), nullable=True), schema=SCHEMA)
    op.add_column("prediction_markets", sa.Column("resolver_key", sa.String(200), nullable=True), schema=SCHEMA)
    op.add_column("prediction_markets", sa.Column("gemini_prompt_template", sa.Text(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("prediction_markets", "gemini_prompt_template", schema=SCHEMA)
    op.drop_column("prediction_markets", "resolver_key", schema=SCHEMA)
    op.drop_column("prediction_markets", "allowed_values", schema=SCHEMA)
    op.drop_column("prediction_markets", "outcome_type", schema=SCHEMA)
