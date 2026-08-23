"""Add sports.players.photo_url — real player headshot from the provider (2026-08-23).

Additive-only, mirrors `sports.teams.logo_url` (migration 0029). API-Football's `/players`
response already includes a `player.photo` URL that `ApiSportsAdapter.fetch_players` was
previously dropping during mapping — this column, plus the adapter/entity/mapper/serializer
changes alongside it, lets that real photo reach the API instead of the frontend's initials
placeholder. Nullable and not backfilled — existing players only get a photo the next time they're
re-synced from the provider.

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

SCHEMA = "sports"


def upgrade() -> None:
    op.add_column("players", sa.Column("photo_url", sa.String(512), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("players", "photo_url", schema=SCHEMA)
