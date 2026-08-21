"""Statistical-baseline charter, Phase 3 — raw goal counts on prediction_outcomes

Additive-only: adds `prediction_outcomes.raw_home_goals`/`raw_away_goals` (both nullable, no
default). Populated only by the resolvers backing football's 12 goals/score markets
(`total_goals_over_under*`, `home/away_team_total_goals`, `correct_score`, `home/away_clean_sheet`,
`home/away_win_to_nil` — see `outcome_resolution_service.py`'s GRID and binary resolver branches);
`NULL` for every other market and for every existing row, never backfilled or fabricated. Exists so
a genuine Poisson baseline (`FootballGoalsPoissonAdapter`) can fit λ_home/λ_away directly from the
real final score, instead of the derived 0/1 classification label every other roster candidate
reads via `DatasetBuilder`.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

SCHEMA = "predictions"


def upgrade() -> None:
    op.add_column("prediction_outcomes", sa.Column("raw_home_goals", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("prediction_outcomes", sa.Column("raw_away_goals", sa.Integer(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("prediction_outcomes", "raw_away_goals", schema=SCHEMA)
    op.drop_column("prediction_outcomes", "raw_home_goals", schema=SCHEMA)
