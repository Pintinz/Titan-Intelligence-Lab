"""Schema/table GRANTs for anon/authenticated roles (docs/security.md, docs/decisions.md).

Discovered while verifying migration 0011's policies: Supabase auto-grants ``USAGE`` on the
``public`` schema (and a handful of its own) to ``anon``/``authenticated`` when a project is
created, but schemas introduced via our own Alembic migrations (identity, tenancy, billing,
webhooks, sports, admin, features, ingestion, knowledge_graph) never received that grant. RLS
policies are irrelevant if the connecting role can't even reference the schema/table at the
SQL permission level — Postgres checks GRANTs before RLS ever runs.

This migration grants broadly at the table level (``GRANT ALL ... TO anon, authenticated``),
matching Supabase's own convention for tables created through its dashboard/API: GRANT is the
coarse, traditional Postgres permission gate, while RLS (migrations 0010-0011) is the actual
fine-grained enforcement layer that decides which *rows* are visible/writable. This is safe
specifically because every table in every one of these schemas already has RLS enabled — a
table with no SELECT/write policy remains fully inaccessible to anon/authenticated regardless
of this GRANT (e.g. identity.audit_log_entries has no write policy at all).

``ALTER DEFAULT PRIVILEGES`` ensures tables added by *future* migrations (run by the same role)
inherit the same grant automatically, so this doesn't need repeating per schema-owning
migration going forward.

Postgres-only, same dialect-guard rationale as 0010/0011.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-25
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_SCHEMAS = [
    "identity", "tenancy", "billing", "webhooks",
    "sports", "admin", "features", "ingestion", "knowledge_graph",
]


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
