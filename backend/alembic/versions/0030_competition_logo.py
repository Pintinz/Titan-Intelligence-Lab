"""Competition logo

Additive-only: adds `sports.competitions.logo_url` (the competition's crest/badge URL) so
Competition Intelligence cards can show the league logo alongside its name instead of text-only,
mirroring the same field already added for teams in 0029.

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

SCHEMA = "sports"


def upgrade() -> None:
    op.add_column("competitions", sa.Column("logo_url", sa.String(512), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("competitions", "logo_url", schema=SCHEMA)
