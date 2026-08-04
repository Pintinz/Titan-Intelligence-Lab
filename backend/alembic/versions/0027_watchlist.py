"""Watchlist module (docs — Watchlist vertical slice)

New `watchlist` schema, single `watchlist_entries` table. A user can follow a match, team,
competition, or prediction — loose `entity_type`/`entity_ref` reference into whichever module
owns that entity (sports/predictions), the same pattern already used by the Knowledge Graph and
by `Prediction.subject_ref`. No FK into `identity.users` or the referenced entity tables,
matching the existing convention of storing `created_by`/`updated_by` as bare UUID columns
(see 0025) rather than cross-schema foreign keys.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

SCHEMA = "watchlist"
TABLE = "watchlist_entries"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_ref", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "entity_type", "entity_ref", name="uq_watchlist_entry_per_user"),
        schema=SCHEMA,
    )
    op.create_index("ix_watchlist_entries_user_id", TABLE, ["user_id"], schema=SCHEMA)
    op.create_index("ix_watchlist_entries_entity_type", TABLE, ["entity_type"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_watchlist_entries_entity_type", table_name=TABLE, schema=SCHEMA)
    op.drop_index("ix_watchlist_entries_user_id", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
