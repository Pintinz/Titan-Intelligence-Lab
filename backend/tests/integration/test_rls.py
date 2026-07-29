"""RLS dimension of the Milestone 6 integration suite (docs/rls.md).

Pytest-native version of the SQL harness used to hand-verify migrations 0010-0011 against the
live ``titaniq`` project during development (23/23 checks passed at the time — see
docs/decisions.md ADR for the record). Fixture rows are inserted once per module inside an
outer transaction that is rolled back at teardown; each individual role-impersonation check
runs inside a SAVEPOINT (nested transaction) so ``SET LOCAL ROLE``/``request.jwt.claims``
never leaks between checks and no row survives the test run either way.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
import pytest_asyncio

from tests.integration.conftest import _asyncpg_dsn, requires_db, DB_URL

OWNER = str(uuid.uuid4())
MEMBER = str(uuid.uuid4())
OUTSIDER = str(uuid.uuid4())
MODERATOR = str(uuid.uuid4())
ANALYST = str(uuid.uuid4())
ADMIN = str(uuid.uuid4())
ORG_A = str(uuid.uuid4())
SPORT = str(uuid.uuid4())
PLAN = str(uuid.uuid4())
SUBSCRIPTION = str(uuid.uuid4())
SECURITY_EVENT = str(uuid.uuid4())
AUDIT_ENTRY = str(uuid.uuid4())
WEBHOOK_ENDPOINT = str(uuid.uuid4())
PRED_MARKET = str(uuid.uuid4())
PRED_MODEL = str(uuid.uuid4())
PRED_PREDICTION = str(uuid.uuid4())
PRED_AUDIT = str(uuid.uuid4())
PRED_MAPPING = str(uuid.uuid4())
NEWS_SOURCE = str(uuid.uuid4())
NEWS_ARTICLE = str(uuid.uuid4())
SYNC_RUN = str(uuid.uuid4())


@pytest_asyncio.fixture(scope="module")
async def rls_fixtures():
    if not DB_URL:
        pytest.skip("TITANIQ_INTEGRATION_DB_URL not set")
    conn = await asyncpg.connect(_asyncpg_dsn(DB_URL))
    outer_tx = conn.transaction()
    await outer_tx.start()
    try:
        await conn.execute(
            """
            INSERT INTO identity.users (id, email, role, status, email_verified) VALUES
                ($1, 'owner@rlstest.local', 'free', 'active', true),
                ($2, 'member@rlstest.local', 'free', 'active', true),
                ($3, 'outsider@rlstest.local', 'free', 'active', true),
                ($4, 'moderator@rlstest.local', 'moderator', 'active', true),
                ($5, 'analyst@rlstest.local', 'analyst', 'active', true),
                ($6, 'admin@rlstest.local', 'administrator', 'active', true)
            """,
            OWNER, MEMBER, OUTSIDER, MODERATOR, ANALYST, ADMIN,
        )
        await conn.execute(
            "INSERT INTO tenancy.organizations (id, name, slug, owner_user_id) VALUES ($1, 'RLS IT Org', 'rls-it-org', $2)",
            ORG_A, OWNER,
        )
        await conn.execute(
            "INSERT INTO tenancy.memberships (id, organization_id, user_id, role) VALUES (gen_random_uuid(), $1, $2, 'owner'), (gen_random_uuid(), $1, $3, 'member')",
            ORG_A, OWNER, MEMBER,
        )
        await conn.execute(
            "INSERT INTO identity.security_events (id, event_type, occurred_at, user_id) VALUES ($1, 'login_failure', now(), $2)",
            SECURITY_EVENT, MEMBER,
        )
        await conn.execute(
            "INSERT INTO identity.audit_log_entries (id, action, occurred_at, actor_user_id, target_type, target_id) VALUES ($1, 'user_registered', now(), $2, 'user', $2::text)",
            AUDIT_ENTRY, MEMBER,
        )
        await conn.execute("INSERT INTO sports.sports (id, code, name) VALUES ($1, 'rls_it_sport', 'RLS IT Sport')", SPORT)
        await conn.execute("INSERT INTO billing.plans (id, key, name, tier) VALUES ($1, 'rls_it_plan', 'RLS IT Plan', 'free')", PLAN)
        await conn.execute(
            "INSERT INTO billing.subscriptions (id, subject_type, subject_id, plan_id, status) VALUES ($1, 'user', $2, $3, 'active')",
            SUBSCRIPTION, MEMBER, PLAN,
        )
        await conn.execute(
            "INSERT INTO webhooks.webhook_endpoints (id, organization_id, url, signing_secret_encrypted, subscribed_events) VALUES ($1, $2, 'https://example.com/hook', 'enc:test', '[\"*\"]'::jsonb)",
            WEBHOOK_ENDPOINT, ORG_A,
        )

        # -- Milestone 9: predictions schema (migration 0021 RLS) -----------------------------
        await conn.execute(
            "INSERT INTO predictions.prediction_markets (id, market_key, sport_code, name, category, market_kind, target_type) "
            "VALUES ($1, 'rls_it.market', 'football', 'RLS IT Market', 'match_outcome', 'binary', 'classification')",
            PRED_MARKET,
        )
        await conn.execute(
            "INSERT INTO predictions.models (id, market_id, model_key, version, algorithm) "
            "VALUES ($1, $2, 'rls_it.market.heuristic', 1, 'heuristic_logistic_v1')",
            PRED_MODEL, PRED_MARKET,
        )
        await conn.execute(
            "INSERT INTO predictions.predictions (id, market_id, model_id, subject_ref, value, probability, model_version) "
            "VALUES ($1, $2, $3, 'rls-it-fixture', 'positive', 0.6, '1')",
            PRED_PREDICTION, PRED_MARKET, PRED_MODEL,
        )
        await conn.execute(
            "INSERT INTO predictions.prediction_audits (id, action, actor, occurred_at, prediction_id) "
            "VALUES ($1, 'generated', 'rls-it-test', now(), $2)",
            PRED_AUDIT, PRED_PREDICTION,
        )
        await conn.execute(
            "INSERT INTO predictions.feature_market_mappings (id, market_id, feature_key) VALUES ($1, $2, 'rls_it.feature')",
            PRED_MAPPING, PRED_MARKET,
        )

        # -- Milestone 8: intelligence schema (migration 0022 RLS) ----------------------------
        await conn.execute(
            "INSERT INTO intelligence.news_sources (id, source_type, name, url) "
            "VALUES ($1, 'rss', 'RLS IT Source', 'https://rls-it.example.com/feed')",
            NEWS_SOURCE,
        )
        await conn.execute(
            "INSERT INTO intelligence.news_articles (id, source_id, title, url, content_hash, raw_text, published_at, fetched_at) "
            "VALUES ($1, $2, 'RLS IT Article', 'https://rls-it.example.com/article', 'rls-it-hash', 'body', now(), now())",
            NEWS_ARTICLE, NEWS_SOURCE,
        )
        await conn.execute(
            "INSERT INTO intelligence.intelligence_sync_runs (id, channel_type, channel_key, trigger, status, started_at) "
            "VALUES ($1, 'news', 'rls-it-channel', 'scheduled', 'running', now())",
            SYNC_RUN,
        )

        yield conn
    finally:
        await outer_tx.rollback()
        await conn.close()


async def _as_role(conn: asyncpg.Connection, role: str, user_id: str | None, query: str, *args):
    async with conn.transaction():  # SAVEPOINT since an outer transaction is already open
        await conn.execute(f"SET LOCAL ROLE {role}")
        if user_id is not None:
            await conn.execute(
                "SELECT set_config('request.jwt.claims', $1, true)",
                f'{{"sub":"{user_id}","role":"{role}"}}',
            )
        try:
            return await conn.fetch(query, *args)
        finally:
            await conn.execute("RESET ROLE")


@requires_db
async def test_user_sees_own_row(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM identity.users WHERE id = $1", uuid.UUID(MEMBER))
    assert len(rows) == 1


@requires_db
async def test_user_cannot_see_other_row(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM identity.users WHERE id = $1", uuid.UUID(OWNER))
    assert len(rows) == 0


@requires_db
async def test_moderator_sees_any_user(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MODERATOR, "SELECT 1 FROM identity.users WHERE id = $1", uuid.UUID(MEMBER))
    assert len(rows) == 1


@requires_db
async def test_non_member_cannot_see_org(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", OUTSIDER, "SELECT 1 FROM tenancy.organizations WHERE id = $1", uuid.UUID(ORG_A))
    assert len(rows) == 0


@requires_db
async def test_member_sees_own_org(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM tenancy.organizations WHERE id = $1", uuid.UUID(ORG_A))
    assert len(rows) == 1


@requires_db
async def test_admin_sees_any_org(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ADMIN, "SELECT 1 FROM tenancy.organizations WHERE id = $1", uuid.UUID(ORG_A))
    assert len(rows) == 1


@requires_db
async def test_member_cannot_update_org(rls_fixtures):
    async with rls_fixtures.transaction():
        await rls_fixtures.execute("SET LOCAL ROLE authenticated")
        await rls_fixtures.execute("SELECT set_config('request.jwt.claims', $1, true)", f'{{"sub":"{MEMBER}","role":"authenticated"}}')
        result = await rls_fixtures.execute("UPDATE tenancy.organizations SET name = 'hacked' WHERE id = $1", uuid.UUID(ORG_A))
        await rls_fixtures.execute("RESET ROLE")
    assert result == "UPDATE 0"


@requires_db
async def test_owner_can_update_org(rls_fixtures):
    async with rls_fixtures.transaction():
        await rls_fixtures.execute("SET LOCAL ROLE authenticated")
        await rls_fixtures.execute("SELECT set_config('request.jwt.claims', $1, true)", f'{{"sub":"{OWNER}","role":"authenticated"}}')
        result = await rls_fixtures.execute("UPDATE tenancy.organizations SET name = 'renamed' WHERE id = $1", uuid.UUID(ORG_A))
        await rls_fixtures.execute("RESET ROLE")
    assert result == "UPDATE 1"


@requires_db
async def test_analyst_reads_sports_catalog(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ANALYST, "SELECT 1 FROM sports.sports WHERE id = $1", uuid.UUID(SPORT))
    assert len(rows) == 1


@requires_db
async def test_free_user_cannot_read_sports_catalog(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM sports.sports WHERE id = $1", uuid.UUID(SPORT))
    assert len(rows) == 0


@requires_db
async def test_free_user_cannot_read_security_events(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM identity.security_events WHERE id = $1", uuid.UUID(SECURITY_EVENT))
    assert len(rows) == 0


@requires_db
async def test_moderator_reads_security_events(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MODERATOR, "SELECT 1 FROM identity.security_events WHERE id = $1", uuid.UUID(SECURITY_EVENT))
    assert len(rows) == 1


@requires_db
async def test_moderator_cannot_read_audit_log(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MODERATOR, "SELECT 1 FROM identity.audit_log_entries WHERE id = $1", uuid.UUID(AUDIT_ENTRY))
    assert len(rows) == 0


@requires_db
async def test_admin_reads_audit_log(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ADMIN, "SELECT 1 FROM identity.audit_log_entries WHERE id = $1", uuid.UUID(AUDIT_ENTRY))
    assert len(rows) == 1


@requires_db
async def test_anon_reads_public_plans(rls_fixtures):
    rows = await _as_role(rls_fixtures, "anon", None, "SELECT 1 FROM billing.plans WHERE id = $1", uuid.UUID(PLAN))
    assert len(rows) == 1


@requires_db
async def test_anon_guest_cannot_read_users(rls_fixtures):
    rows = await _as_role(rls_fixtures, "anon", None, "SELECT 1 FROM identity.users LIMIT 1")
    assert len(rows) == 0


@requires_db
async def test_user_sees_own_subscription(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM billing.subscriptions WHERE id = $1", uuid.UUID(SUBSCRIPTION))
    assert len(rows) == 1


@requires_db
async def test_other_user_cannot_see_subscription(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", OUTSIDER, "SELECT 1 FROM billing.subscriptions WHERE id = $1", uuid.UUID(SUBSCRIPTION))
    assert len(rows) == 0


@requires_db
async def test_analyst_sees_all_subscriptions(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ANALYST, "SELECT 1 FROM billing.subscriptions WHERE id = $1", uuid.UUID(SUBSCRIPTION))
    assert len(rows) == 1


@requires_db
async def test_org_member_cannot_see_webhook_endpoint(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM webhooks.webhook_endpoints WHERE id = $1", uuid.UUID(WEBHOOK_ENDPOINT))
    assert len(rows) == 0


@requires_db
async def test_org_owner_sees_webhook_endpoint(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", OWNER, "SELECT 1 FROM webhooks.webhook_endpoints WHERE id = $1", uuid.UUID(WEBHOOK_ENDPOINT))
    assert len(rows) == 1


# -- Milestone 9: predictions schema RLS (migration 0021) -------------------------------------


@requires_db
async def test_free_user_reads_prediction_markets(rls_fixtures):
    """App-facing product data — any real authenticated user (free+), same flat threshold as
    every other elevated-read policy, no invented row-level status filter."""
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM predictions.prediction_markets WHERE id = $1", uuid.UUID(PRED_MARKET))
    assert len(rows) == 1


@requires_db
async def test_free_user_reads_predictions(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM predictions.predictions WHERE id = $1", uuid.UUID(PRED_PREDICTION))
    assert len(rows) == 1


@requires_db
async def test_anon_cannot_read_predictions(rls_fixtures):
    """`has_role_at_least` coalesces to -1 for a caller with no `identity.users` row — anon
    never satisfies even the lowest ('free') threshold."""
    rows = await _as_role(rls_fixtures, "anon", None, "SELECT 1 FROM predictions.predictions WHERE id = $1", uuid.UUID(PRED_PREDICTION))
    assert len(rows) == 0


@requires_db
async def test_free_user_cannot_read_model_registry(rls_fixtures):
    """Champion/Challenger registry protection — not app-facing, analyst+ only."""
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM predictions.models WHERE id = $1", uuid.UUID(PRED_MODEL))
    assert len(rows) == 0


@requires_db
async def test_analyst_reads_model_registry(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ANALYST, "SELECT 1 FROM predictions.models WHERE id = $1", uuid.UUID(PRED_MODEL))
    assert len(rows) == 1


@requires_db
async def test_free_user_cannot_read_feature_market_mappings(rls_fixtures):
    """Feature-to-Market Registry protection — analyst+ only, same shape as the model registry."""
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM predictions.feature_market_mappings WHERE id = $1", uuid.UUID(PRED_MAPPING))
    assert len(rows) == 0


@requires_db
async def test_analyst_reads_feature_market_mappings(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ANALYST, "SELECT 1 FROM predictions.feature_market_mappings WHERE id = $1", uuid.UUID(PRED_MAPPING))
    assert len(rows) == 1


@requires_db
async def test_analyst_cannot_read_prediction_audits(rls_fixtures):
    """Audit protection — `prediction_audits` is administrator+ only, mirroring
    `identity.audit_log_entries` (analyst does NOT qualify, unlike the registry tables above)."""
    rows = await _as_role(rls_fixtures, "authenticated", ANALYST, "SELECT 1 FROM predictions.prediction_audits WHERE id = $1", uuid.UUID(PRED_AUDIT))
    assert len(rows) == 0


@requires_db
async def test_admin_reads_prediction_audits(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ADMIN, "SELECT 1 FROM predictions.prediction_audits WHERE id = $1", uuid.UUID(PRED_AUDIT))
    assert len(rows) == 1


@requires_db
async def test_member_cannot_write_prediction_markets(rls_fixtures):
    """No role ever gets a write path through RLS — every mutation continues exclusively
    through FastAPI's service-role connection (ADR-026)."""
    async with rls_fixtures.transaction():
        await rls_fixtures.execute("SET LOCAL ROLE authenticated")
        await rls_fixtures.execute("SELECT set_config('request.jwt.claims', $1, true)", f'{{"sub":"{MEMBER}","role":"authenticated"}}')
        result = await rls_fixtures.execute("UPDATE predictions.prediction_markets SET name = 'hacked' WHERE id = $1", uuid.UUID(PRED_MARKET))
        await rls_fixtures.execute("RESET ROLE")
    assert result == "UPDATE 0"


@requires_db
async def test_admin_cannot_write_prediction_audits(rls_fixtures):
    """Audit tables are append-only from every role's perspective, including administrator —
    no write policy exists at all, so even the most privileged RLS-visible role can't mutate
    the audit trail directly; only the service-role connection can."""
    async with rls_fixtures.transaction():
        await rls_fixtures.execute("SET LOCAL ROLE authenticated")
        await rls_fixtures.execute("SELECT set_config('request.jwt.claims', $1, true)", f'{{"sub":"{ADMIN}","role":"authenticated"}}')
        result = await rls_fixtures.execute("DELETE FROM predictions.prediction_audits WHERE id = $1", uuid.UUID(PRED_AUDIT))
        await rls_fixtures.execute("RESET ROLE")
    assert result == "DELETE 0"


# -- Milestone 8: intelligence schema RLS (migration 0022) ------------------------------------


@requires_db
async def test_free_user_reads_news_articles(rls_fixtures):
    """Mirrors `apps/api/routers/intelligence_router.py`'s actual `get_current_user` (any
    authenticated user) posture for the tables it directly serves."""
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM intelligence.news_articles WHERE id = $1", uuid.UUID(NEWS_ARTICLE))
    assert len(rows) == 1


@requires_db
async def test_anon_cannot_read_news_articles(rls_fixtures):
    rows = await _as_role(rls_fixtures, "anon", None, "SELECT 1 FROM intelligence.news_articles WHERE id = $1", uuid.UUID(NEWS_ARTICLE))
    assert len(rows) == 0


@requires_db
async def test_free_user_cannot_read_news_sources(rls_fixtures):
    """`news_sources` is never returned directly by any route (only referenced by id from
    inside an article row) — analyst+ only, same as the M2-M5 ingestion-internal tables."""
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM intelligence.news_sources WHERE id = $1", uuid.UUID(NEWS_SOURCE))
    assert len(rows) == 0


@requires_db
async def test_analyst_reads_news_sources(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ANALYST, "SELECT 1 FROM intelligence.news_sources WHERE id = $1", uuid.UUID(NEWS_SOURCE))
    assert len(rows) == 1


@requires_db
async def test_free_user_cannot_read_intelligence_sync_runs(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", MEMBER, "SELECT 1 FROM intelligence.intelligence_sync_runs WHERE id = $1", uuid.UUID(SYNC_RUN))
    assert len(rows) == 0


@requires_db
async def test_analyst_reads_intelligence_sync_runs(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ANALYST, "SELECT 1 FROM intelligence.intelligence_sync_runs WHERE id = $1", uuid.UUID(SYNC_RUN))
    assert len(rows) == 1


@requires_db
async def test_member_cannot_write_news_articles(rls_fixtures):
    async with rls_fixtures.transaction():
        await rls_fixtures.execute("SET LOCAL ROLE authenticated")
        await rls_fixtures.execute("SELECT set_config('request.jwt.claims', $1, true)", f'{{"sub":"{MEMBER}","role":"authenticated"}}')
        result = await rls_fixtures.execute("UPDATE intelligence.news_articles SET title = 'hacked' WHERE id = $1", uuid.UUID(NEWS_ARTICLE))
        await rls_fixtures.execute("RESET ROLE")
    assert result == "UPDATE 0"


# -- Regression: existing Milestone 6 RLS behavior is unchanged --------------------------------


@requires_db
async def test_regression_analyst_still_reads_sports_catalog(rls_fixtures):
    """Migrations 0020-0022 only add GRANTs/policies for the `predictions`/`intelligence`
    schemas — this re-asserts a representative pre-existing Milestone 6 check to confirm nothing
    about the M2-M5 catalog/identity RLS behavior regressed."""
    rows = await _as_role(rls_fixtures, "authenticated", ANALYST, "SELECT 1 FROM sports.sports WHERE id = $1", uuid.UUID(SPORT))
    assert len(rows) == 1


@requires_db
async def test_regression_admin_still_reads_audit_log(rls_fixtures):
    rows = await _as_role(rls_fixtures, "authenticated", ADMIN, "SELECT 1 FROM identity.audit_log_entries WHERE id = $1", uuid.UUID(AUDIT_ENTRY))
    assert len(rows) == 1
