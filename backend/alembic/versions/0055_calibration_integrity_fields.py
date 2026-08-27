"""Add predictions.raw_probability/calibration_sample_count/calibration_fitted_at — Phase 4
Calibration Integrity (2026-08-25).

Three additive columns, same "nullable, never backfilled" posture as 0051/0053/0054:

- `raw_probability` — the pre-calibration probability for `value`, same semantic as
  `probability` but with the identity/no-op calibration applied.
- `calibration_sample_count` / `calibration_fitted_at` — how much evidence backed, and when, the
  calibration fit named by the (now four-state: UNFITTED/FITTED/STALE/INVALID)
  `calibration_status` column added in 0053. `None` for a model-baked calibration
  (`ModelDefinition.calibration_ref`) or a prediction from before these columns existed.

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

PREDICTIONS = "predictions"


def upgrade() -> None:
    op.add_column("predictions", sa.Column("raw_probability", sa.Float(), nullable=True), schema=PREDICTIONS)
    op.add_column(
        "predictions", sa.Column("calibration_sample_count", sa.Integer(), nullable=True), schema=PREDICTIONS
    )
    op.add_column(
        "predictions",
        sa.Column("calibration_fitted_at", sa.DateTime(timezone=True), nullable=True),
        schema=PREDICTIONS,
    )


def downgrade() -> None:
    op.drop_column("predictions", "calibration_fitted_at", schema=PREDICTIONS)
    op.drop_column("predictions", "calibration_sample_count", schema=PREDICTIONS)
    op.drop_column("predictions", "raw_probability", schema=PREDICTIONS)
