"""Row Level Security for watchlist/alerts — closes the coverage gap left by 0010 (Security
Milestone finding M-6). `watchlist.watchlist_entries` and `alerts.alert_events` are genuinely
user-owned tables (both carry a direct `user_id` column) added in Milestones 27/28, after 0010
was written, so they were never brought under RLS the way every other user-owned table was.

Same caveat 0010 itself documents: FastAPI connects via the service-role connection, which
bypasses RLS unconditionally by Postgres design (docs/rls.md), so this is defense-in-depth for
direct Supabase-client/PostgREST access, not the actual authorization boundary — that remains
`WatchlistService`/`AlertService`'s own ownership checks. Postgres-only; no-ops on SQLite.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-09
"""

from __future__ import annotations

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

_TABLES = [("watchlist", "watchlist_entries"), ("alerts", "alert_events")]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for schema, table in _TABLES:
        op.execute(f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY")

    op.execute(
        "CREATE POLICY watchlist_entries_select_self ON watchlist.watchlist_entries "
        "FOR SELECT USING (user_id = auth.uid())"
    )
    op.execute(
        "CREATE POLICY watchlist_entries_delete_self ON watchlist.watchlist_entries "
        "FOR DELETE USING (user_id = auth.uid())"
    )

    op.execute("CREATE POLICY alert_events_select_self ON alerts.alert_events FOR SELECT USING (user_id = auth.uid())")
    op.execute(
        "CREATE POLICY alert_events_update_self ON alerts.alert_events "
        "FOR UPDATE USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        """
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT schemaname, tablename, policyname FROM pg_policies
                WHERE schemaname IN ('watchlist', 'alerts')
            LOOP
                EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', r.policyname, r.schemaname, r.tablename);
            END LOOP;
        END $$;
        """
    )

    for schema, table in _TABLES:
        op.execute(f"ALTER TABLE {schema}.{table} DISABLE ROW LEVEL SECURITY")
