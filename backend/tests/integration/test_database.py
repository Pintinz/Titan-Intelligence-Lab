"""Live-database dimension of the Milestone 6 integration suite (docs/supabase.md).

Verifies the actual provisioned Supabase Postgres instance: connectivity, that every
Alembic-managed schema/table exists, and that the migration ledger is at the expected head —
catching drift between what the migration history *says* it created and what's actually live.
"""

from __future__ import annotations

from tests.integration.conftest import requires_db

EXPECTED_SCHEMAS = {
    "sports", "admin", "features", "ingestion", "knowledge_graph",
    "identity", "tenancy", "billing", "webhooks",
}

EXPECTED_HEAD_REVISION = "0014"


@requires_db
async def test_can_connect(db_connection):
    version = await db_connection.fetchval("SELECT version()")
    assert "PostgreSQL" in version


@requires_db
async def test_all_app_schemas_exist(db_connection):
    rows = await db_connection.fetch(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name = ANY($1::text[])",
        list(EXPECTED_SCHEMAS),
    )
    found = {r["schema_name"] for r in rows}
    assert found == EXPECTED_SCHEMAS


@requires_db
async def test_alembic_version_at_expected_head(db_connection):
    version = await db_connection.fetchval("SELECT version_num FROM sports.alembic_version")
    assert version == EXPECTED_HEAD_REVISION


@requires_db
async def test_every_app_table_has_rls_enabled(db_connection):
    rows = await db_connection.fetch(
        """
        SELECT n.nspname AS schema, c.relname AS table_name, c.relrowsecurity AS rls_enabled
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = ANY($1::text[]) AND c.relkind = 'r'
        """,
        list(EXPECTED_SCHEMAS),
    )
    without_rls = [f"{r['schema']}.{r['table_name']}" for r in rows if not r["rls_enabled"]]
    assert without_rls == [], f"Tables missing RLS: {without_rls}"


@requires_db
async def test_storage_buckets_exist(db_connection):
    expected = {
        "avatars", "team-logos", "competition-logos", "ai-reports",
        "generated-charts", "uploads", "temporary-files",
    }
    rows = await db_connection.fetch("SELECT id FROM storage.buckets WHERE id = ANY($1::text[])", list(expected))
    found = {r["id"] for r in rows}
    assert found == expected


@requires_db
async def test_realtime_publication_has_expected_tables_only(db_connection):
    rows = await db_connection.fetch(
        "SELECT schemaname, tablename FROM pg_publication_tables WHERE pubname = 'supabase_realtime'"
    )
    actual = {f"{r['schemaname']}.{r['tablename']}" for r in rows}
    expected = {
        "sports.matches", "sports.match_events",
        "admin.provider_health_state", "admin.provider_incidents",
        "ingestion.sync_runs",
        "identity.sessions", "identity.security_events",
        "webhooks.webhook_deliveries",
    }
    assert actual == expected, (
        "Realtime publication drifted from the deliberately-selective table list "
        "(migration 0014) — every table here should be a conscious addition, not accidental."
    )
