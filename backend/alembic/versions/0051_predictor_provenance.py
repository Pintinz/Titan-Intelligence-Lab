"""Add predictions.predictions.predictor_provenance — real prod incident audit (2026-08-23).

`PredictionEngine._resolve_predictor` silently falls back from the market's real Champion model
to a generic formula predictor whenever the Champion's trained artifact fails to load — a real,
already-handled failure mode (never breaks generation) — but nothing previously recorded *which*
predictor actually served a given prediction. `Prediction.model_id`/`model_version` always name
the Champion either way, so the API could only ever report "Champion, ACTIVE" even on a run where
a formula fallback actually computed the published value/probability — misattributing a
formula-computed prediction as ML-computed with no way to tell the difference after the fact.

This column closes that gap going forward: `PredictionEngine.generate()` now sets it explicitly to
"trained_model" or "formula_fallback" on every new prediction. Nullable and not backfilled —
existing rows genuinely have no recorded provenance, and inferring one after the fact from
`model_id` alone would repeat the exact conflation this column exists to close.

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

PREDICTIONS = "predictions"


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column("predictor_provenance", sa.String(32), nullable=True),
        schema=PREDICTIONS,
    )


def downgrade() -> None:
    op.drop_column("predictions", "predictor_provenance", schema=PREDICTIONS)
