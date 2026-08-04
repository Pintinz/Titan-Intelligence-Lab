"""Alerts module (docs — Alerts vertical slice)

New `alerts` schema, single `alert_events` table — one row per alert delivered to one user.
Fired by real triggers only: fixture status transitions (kickoff/final result) and prediction
republishing (prediction changed), scoped to users who are actually following the affected
match/team/competition in their Watchlist (`AlertService.notify_watchers` -> `WatchlistRepository
.list_watchers`). No FK into `identity.users` or the referenced entity tables, matching the same
convention as `watchlist_entries` (0027).

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

SCHEMA = "alerts"
TABLE = "alert_events"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("alert_type", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_ref", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_alert_events_user_id", TABLE, ["user_id"], schema=SCHEMA)
    op.create_index("ix_alert_events_alert_type", TABLE, ["alert_type"], schema=SCHEMA)
    op.create_index("ix_alert_events_created_at", TABLE, ["created_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_alert_events_created_at", table_name=TABLE, schema=SCHEMA)
    op.drop_index("ix_alert_events_alert_type", table_name=TABLE, schema=SCHEMA)
    op.drop_index("ix_alert_events_user_id", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
