"""Fixture scores + team logos

Additive-only: adds `sports.fixtures.home_score`/`away_score` (populated once a fixture reaches
COMPLETED, null otherwise) and `sports.teams.logo_url` (the provider's team crest URL) — both
needed for match cards to show final scores and team logos instead of text-only fixtures.

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

SCHEMA = "sports"


def upgrade() -> None:
    op.add_column("fixtures", sa.Column("home_score", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("fixtures", sa.Column("away_score", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("teams", sa.Column("logo_url", sa.String(512), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("teams", "logo_url", schema=SCHEMA)
    op.drop_column("fixtures", "away_score", schema=SCHEMA)
    op.drop_column("fixtures", "home_score", schema=SCHEMA)
