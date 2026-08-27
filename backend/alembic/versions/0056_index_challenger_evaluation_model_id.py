"""Index challenger_evaluations.challenger_model_id — Phase 7 audit fix (2026-08-25).

The champion-promotion gate (`ModelRegistryService._require_favorable_comparison`) previously
found a candidate's own comparison by scanning the market's most recent 50 comparisons and
filtering client-side — a real false-negative risk (COMPARISON_MISSING) once 50+ other
comparisons had been recorded for the same market since. It now looks up directly by
`(market_id, challenger_model_id)` via `ModelComparisonRepositoryPort.get_for_challenger`, which
this index backs.

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

PREDICTIONS = "predictions"


def upgrade() -> None:
    op.create_index(
        "ix_predictions_challenger_evaluations_challenger_model_id",
        "challenger_evaluations",
        ["challenger_model_id"],
        unique=False,
        schema=PREDICTIONS,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_predictions_challenger_evaluations_challenger_model_id",
        table_name="challenger_evaluations",
        schema=PREDICTIONS,
    )
