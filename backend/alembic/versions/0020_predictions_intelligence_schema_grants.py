"""Schema/table GRANTs for anon/authenticated on `predictions` (Milestone 9) and `intelligence`
(Milestone 8) — extends migration 0012's fix (docs/decisions.md ADR-027) to the two schemas that
were missed when it ran, since neither existed yet at Milestone 6.

Discovered while completing predictions' RLS: the Supabase security advisor correctly flagged
RLS-disabled on both schemas' tables, but even after enabling RLS, ADR-027 applies identically
here — Postgres checks GRANTs before RLS ever runs, and a schema introduced by our own Alembic
migrations never receives Supabase's auto-grant. Without this, the RLS policies added by
migrations 0021/0022 would be unreachable code for anon/authenticated, exactly as it was for
identity/tenancy/billing/webhooks/sports/admin/features/ingestion/knowledge_graph before 0012.

Postgres-only, same dialect-guard rationale as 0010-0012.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_SCHEMAS = ["predictions", "intelligence"]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for schema in _SCHEMAS:
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO anon, authenticated")
        op.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA {schema} TO anon, authenticated")
        op.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA {schema} TO anon, authenticated")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT ALL ON TABLES TO anon, authenticated"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT ALL ON SEQUENCES TO anon, authenticated"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for schema in _SCHEMAS:
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE ALL ON TABLES FROM anon, authenticated")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE ALL ON SEQUENCES FROM anon, authenticated")
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM anon, authenticated")
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {schema} FROM anon, authenticated")
        op.execute(f"REVOKE USAGE ON SCHEMA {schema} FROM anon, authenticated")
