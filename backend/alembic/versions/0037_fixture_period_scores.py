"""Fixture period scores

Additive-only: adds `sports.fixtures.period_scores` (JSON, nullable) — the sport-specific
period-by-period score breakdown (quarters for basketball, innings for baseball). None for
football (not fetched by that adapter) and for any fixture not yet played. Populated by
`ApiBasketballAdapter._extract_quarter_scores`/`ApiBaseballAdapter._extract_inning_scores`
during fixture sync, both verified live against the real provider response shape (2026-08-10).

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

SCHEMA = "sports"


def upgrade() -> None:
    op.add_column("fixtures", sa.Column("period_scores", sa.JSON(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("fixtures", "period_scores", schema=SCHEMA)
