"""Provider capability note

Additive-only: adds `admin.providers.capability_note`/`capability_checked_at` — a best-effort
capability read (e.g. "Free plan — historical data only") derived from a provider's own
connection-test response body, so an account-level limitation (like API-Football's free-tier
season restriction) is visible in Operations Center instead of only surfacing as a failed sync
run's error message. See connection_check_service._extract_capability_note.

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

SCHEMA = "admin"


def upgrade() -> None:
    op.add_column("providers", sa.Column("capability_note", sa.String(256), nullable=True), schema=SCHEMA)
    op.add_column("providers", sa.Column("capability_checked_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("providers", "capability_checked_at", schema=SCHEMA)
    op.drop_column("providers", "capability_note", schema=SCHEMA)
