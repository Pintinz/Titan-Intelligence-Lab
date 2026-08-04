"""Provider auth header name (docs/admin_center.md §2)

Additive-only: adds `admin.providers.auth_header_name`, letting an admin configure the exact
HTTP header a provider expects its API key on (e.g. API-Football's `x-apisports-key`) instead of
the connection tester's hardcoded `X-API-Key`. Nullable — existing `api_key_header` providers
keep working via the same default header name they always used.

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

SCHEMA = "admin"
TABLE = "providers"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("auth_header_name", sa.String(128), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column(TABLE, "auth_header_name", schema=SCHEMA)
