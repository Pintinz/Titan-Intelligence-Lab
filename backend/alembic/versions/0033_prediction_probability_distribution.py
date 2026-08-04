"""Prediction probability distribution + regression uncertainty fields

Additive-only (Universal Probability Engine, 2026-08-02): adds `predictions.predictions.
probability_distribution`/`confidence_interval_low`/`confidence_interval_high`/`expected_error`.
`probability_distribution` is populated for TargetType.CLASSIFICATION markets (every outcome's
calibrated probability, not just the winning one — "Alternative Outcomes"); the three
`confidence_interval_*`/`expected_error` columns are populated only for TargetType.REGRESSION
markets, where a single winning probability was never a meaningful thing to publish. See
modules/predictions/domain/entities.py's `Prediction` docstring.

No data migration: existing `Prediction` rows get an empty JSON object for
`probability_distribution` (the column default) and NULL for the three regression-only columns —
neither is fabricated for predictions generated before this migration.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

SCHEMA = "predictions"


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("probability_distribution", sa.JSON(), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )
    op.add_column("predictions", sa.Column("confidence_interval_low", sa.Float(), nullable=True), schema=SCHEMA)
    op.add_column("predictions", sa.Column("confidence_interval_high", sa.Float(), nullable=True), schema=SCHEMA)
    op.add_column("predictions", sa.Column("expected_error", sa.Float(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("predictions", "expected_error", schema=SCHEMA)
    op.drop_column("predictions", "confidence_interval_high", schema=SCHEMA)
    op.drop_column("predictions", "confidence_interval_low", schema=SCHEMA)
    op.drop_column("predictions", "probability_distribution", schema=SCHEMA)
