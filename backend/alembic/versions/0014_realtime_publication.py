"""Realtime — enable only the tables that genuinely need live push (docs/roadmap.md Milestone
6 REALTIME spec: "Notifications, Live Match Updates, Admin Dashboard, Provider Status,
Background Job Monitoring"). Mapped onto tables that actually exist today:

  - sports.matches, sports.match_events       -> Live Match Updates
  - admin.provider_health_state, admin.provider_incidents -> Provider Status
  - ingestion.sync_runs                       -> Background Job Monitoring
  - identity.sessions                         -> Session Intelligence (a user's own device
                                                  list updating live when a new session starts
                                                  or one is revoked)
  - identity.security_events                  -> Admin/security dashboard live monitoring
  - webhooks.webhook_deliveries                -> live delivery/retry status feed

"Notifications" has no backing table yet (deferred to a later milestone per docs/roadmap.md)
so it is deliberately NOT enabled here — there is nothing to subscribe to.

Every other table (44 backend/catalog rows with no live-update use case, all of billing,
tenancy's low-frequency membership/org data, audit/PAT/webhook-endpoint config tables, etc.)
is deliberately left OUT of the realtime publication. Broadcasts still respect RLS per
subscriber (Supabase Realtime evaluates each subscriber's own JWT against the same policies
from migrations 0010-0011), so enabling these adds no new data exposure — just live push for
rows a client access already can already SELECT one-shot.

Postgres-only, same dialect-guard rationale as prior Supabase-only migrations.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-25
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_REALTIME_TABLES = [
    ("sports", "matches"),
    ("sports", "match_events"),
    ("admin", "provider_health_state"),
    ("admin", "provider_incidents"),
    ("ingestion", "sync_runs"),
    ("identity", "sessions"),
    ("identity", "security_events"),
    ("webhooks", "webhook_deliveries"),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for schema, table in _REALTIME_TABLES:
        op.execute(f"ALTER PUBLICATION supabase_realtime ADD TABLE {schema}.{table}")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for schema, table in _REALTIME_TABLES:
        op.execute(f"ALTER PUBLICATION supabase_realtime DROP TABLE {schema}.{table}")
