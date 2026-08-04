"""Competition fixture-source preferences (football-data.org integration)

Additive-only: adds `ingestion.competition_fixture_source_preferences`, a small admin-managed
routing table — one row per competition that should use a non-default provider
(e.g. football-data.org) for *upcoming* fixture syncing, per the
`SyncOrchestrator.sync_upcoming_fixtures`/`SportsProviderRouter.fetch_upcoming_fixtures`
addition. Absence of a row for a competition means "keep using the sport's default provider,"
which is every competition's existing behavior before this table existed.

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-03
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

SCHEMA = "ingestion"


def upgrade() -> None:
    op.create_table(
        "competition_fixture_source_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("competition_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("preferred_provider_key", sa.String(64), nullable=False),
        sa.Column("provider_competition_ref", sa.String(64), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("competition_fixture_source_preferences", schema=SCHEMA)
