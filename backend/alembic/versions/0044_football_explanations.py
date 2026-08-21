"""Sports-Analyst Explainability — prediction_football_explanations

New table, same "distinct audit record, not a blob column" posture as `0043` (unique on
`prediction_id`: a fresh `explain()` call overwrites the prior row for the same prediction).

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

SCHEMA = "predictions"


def upgrade() -> None:
    op.create_table(
        "prediction_football_explanations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("prediction_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.predictions.id"), nullable=False, unique=True),
        sa.Column("market_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("prediction_value", sa.String(200), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("model_algorithm", sa.String(64), nullable=False, server_default=""),
        sa.Column("attribution_method", sa.String(32), nullable=False),
        sa.Column("key_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("counter_signals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("context", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("verdict", sa.Text(), nullable=False, server_default=""),
        sa.Column("match_profile", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence_explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("bottom_line", sa.Text(), nullable=False, server_default=""),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_prediction_football_explanations_market_key", "prediction_football_explanations", ["market_key"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prediction_football_explanations_market_key", table_name="prediction_football_explanations", schema=SCHEMA,
    )
    op.drop_table("prediction_football_explanations", schema=SCHEMA)
