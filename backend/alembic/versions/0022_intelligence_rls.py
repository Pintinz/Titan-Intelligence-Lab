"""Row Level Security for the `intelligence` schema (Milestone 8, completed as part of
Milestone 9's RLS closure pass) — same building blocks as migrations 0011/0021, no new SQL
functions, no write policies.

Two access tiers, chosen by what `apps/api/routers/intelligence_router.py` actually does today
— every one of its routes is gated at `get_current_user` (any authenticated user, no role
check), so RLS mirrors that exactly rather than inventing a stricter model:

- **Tables the router directly serves** (`news_articles`, `news_events`, `community_topics`,
  `sentiment_results`, `impact_scores`, `summaries`, `source_reliability_scores`) —
  `has_role_at_least('free')`, the same flat any-authenticated-user threshold as
  `predictions.predictions`/`prediction_markets` (migration 0021).
- **Tables never returned by any route** (`news_sources` — only ever referenced by its `id` from
  inside an article/event row, never fetched directly; `community_posts` — `community/topics`
  reads `community_topics`, not raw posts; `intelligence_sync_runs`/`intelligence_sync_checkpoints`
  — pure ingestion bookkeeping) — `analyst+`, matching the M2-M5 backend/catalog pattern
  (rls.md §6) these four are structurally identical to.

Postgres-only, same dialect-guard rationale as 0010/0011/0021. Requires migration 0020's GRANTs.

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_APP_FACING_TABLES = [
    "news_articles",
    "news_events",
    "community_topics",
    "sentiment_results",
    "impact_scores",
    "summaries",
    "source_reliability_scores",
]
_ANALYST_TABLES = [
    "news_sources",
    "community_posts",
    "intelligence_sync_runs",
    "intelligence_sync_checkpoints",
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in _APP_FACING_TABLES + _ANALYST_TABLES:
        op.execute(f"ALTER TABLE intelligence.{table} ENABLE ROW LEVEL SECURITY")

    for table in _APP_FACING_TABLES:
        op.execute(
            f"CREATE POLICY {table}_select_free_plus ON intelligence.{table} "
            f"FOR SELECT USING (identity.has_role_at_least('free'))"
        )

    for table in _ANALYST_TABLES:
        op.execute(
            f"CREATE POLICY {table}_select_analyst_plus ON intelligence.{table} "
            f"FOR SELECT USING (identity.has_role_at_least('analyst'))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in _APP_FACING_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_select_free_plus ON intelligence.{table}")
    for table in _ANALYST_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_select_analyst_plus ON intelligence.{table}")
    for table in _APP_FACING_TABLES + _ANALYST_TABLES:
        op.execute(f"ALTER TABLE intelligence.{table} DISABLE ROW LEVEL SECURITY")
