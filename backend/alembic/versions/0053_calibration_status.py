"""Add predictions.predictions.calibration_status — Section 31 audit fix (2026-08-23).

`CalibratorPort.calibrate()`'s identity pass-through for a model that has never been fitted is a
legitimate, honestly-scoped return value (docs/decisions.md ADR-008) — but nothing previously
recorded whether a given prediction's probability actually passed through a genuinely fitted
calibration or just that raw pass-through. The API could only ever imply "calibrated" for every
prediction regardless of whether `CalibrationFittingService` had ever actually run for that
model, the same class of silent-fallback conflation `predictor_provenance` (0051) already closed
for the Champion/formula-fallback split.

This column closes that gap going forward: `PredictionEngine.generate()` now sets it explicitly to
"calibrated" or "uncalibrated" on every new prediction, via the new `CalibratorPort.is_fitted()`
method. Nullable and not backfilled — existing rows genuinely have no recorded calibration
status, and inferring one after the fact would repeat the same conflation this column exists to
close.

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

PREDICTIONS = "predictions"


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("calibration_status", sa.String(32), nullable=True),
        schema=PREDICTIONS,
    )


def downgrade() -> None:
    op.drop_column("predictions", "calibration_status", schema=PREDICTIONS)
