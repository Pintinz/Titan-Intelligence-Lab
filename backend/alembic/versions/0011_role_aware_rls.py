"""Role-aware, least-privilege RLS — extends migration 0010 (docs/security.md, docs/decisions.md).

0010 established ownership/org-membership policies plus a blanket "RLS enabled, no policies"
stance for tables with no per-user ownership concept. This migration replaces that blanket
stance with real, role-differentiated read access mirroring the full RBAC ladder
(``modules.identity.domain.value_objects.Role``): Guest, Free, Rewarded, Premium, Moderator,
Analyst, Administrator, Super Administrator — plus the implicit "Authenticated User" tier that
ownership checks already cover (``auth.uid() = owner`` is false for anon/unauthenticated by
construction, so no separate anon-vs-authenticated branch is needed).

Design principles (see docs/decisions.md ADR for the full write-up):

  - One SQL function, ``identity.has_role_at_least(min_role)``, encodes the ladder ordinal
    comparison ONCE — every elevated-read policy picks a single threshold role and the ladder
    ordering (mirrored from the Python ``Role.level`` mapping) automatically covers every role
    above it. A Moderator-threshold policy is satisfied by Moderator, Analyst, Administrator,
    and Super Administrator alike — no need for one policy per role.
  - Free / Rewarded / Premium are billing/entitlement tiers, not distinct database-level
    permissions — they get identical ownership-scoped access to their own data. Tier-gated
    *feature* access is enforced by ``modules.billing.application.billing_service`` at the
    application layer, not by RLS (docs/decisions.md).
  - Elevated access granted here is READ-ONLY. Every write path — including administrative
    writes — continues to flow exclusively through FastAPI's service-role connection (which
    bypasses RLS entirely), so there is exactly one place mutations are validated and audited.
    Granting Administrators a parallel direct-write path via RLS would create a second,
    unaudited mutation route around ``IdentityService``/``TenancyService``/etc. — deliberately
    avoided.
  - Analyst+ gets read access to the M2-M5 backend/catalog schemas (sports, admin, features,
    ingestion, knowledge_graph) — this is what "Analyst" role concretely means: broad read
    access to operational/analytics data without needing to go through the API for every query
    (e.g. a BI tool connected with an analyst's JWT). Regular end users never need this data
    directly; they only ever see it through prediction/analytics endpoints (out of scope until
    later milestones).

Postgres-only, same dialect-guard rationale as 0010 (SQLite has no ``auth.uid()``/RLS).

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-25
"""

from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_BACKEND_INTERNAL_TABLES = [
    ("sports", "sports"), ("sports", "venues"), ("sports", "competitions"), ("sports", "seasons"),
    ("sports", "teams"), ("sports", "players"), ("sports", "coaching_staff"), ("sports", "officials"),
    ("sports", "fixtures"), ("sports", "matches"), ("sports", "match_events"), ("sports", "team_statistics"),
    ("sports", "player_statistics"), ("sports", "standings"), ("sports", "injuries"), ("sports", "suspensions"),
    ("sports", "transfers"), ("sports", "rankings"), ("sports", "countries"), ("sports", "lineups"),
    ("admin", "providers"), ("admin", "provider_credentials"), ("admin", "provider_usage_records"),
    ("admin", "provider_health_checks"), ("admin", "provider_incidents"), ("admin", "provider_health_state"),
    ("admin", "feature_flags"),
    ("features", "feature_definitions"), ("features", "feature_definition_versions"),
    ("features", "feature_values_offline"), ("features", "feature_lineage"), ("features", "feature_drift_reports"),
    ("features", "feature_validation_reports"), ("features", "feature_computation_logs"),
    ("features", "feature_consumers"), ("features", "feature_usage_records"),
    ("ingestion", "sync_runs"), ("ingestion", "sync_checkpoints"), ("ingestion", "timeline_events"),
    ("ingestion", "data_quality_reports"), ("ingestion", "provider_ref_index"),
    ("knowledge_graph", "kg_nodes"), ("knowledge_graph", "kg_edges"),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # -- RBAC ladder helper functions -----------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION identity.role_level(role text) RETURNS smallint
        LANGUAGE sql IMMUTABLE AS $$
          SELECT CASE role
            WHEN 'guest' THEN 0
            WHEN 'free' THEN 1
            WHEN 'rewarded' THEN 2
            WHEN 'premium' THEN 3
            WHEN 'moderator' THEN 4
            WHEN 'analyst' THEN 5
            WHEN 'administrator' THEN 6
            WHEN 'super_administrator' THEN 7
            ELSE -1
          END;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION identity.current_role_level() RETURNS smallint
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = identity, pg_temp AS $$
          SELECT identity.role_level(u.role) FROM identity.users u WHERE u.id = auth.uid();
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION identity.has_role_at_least(min_role text) RETURNS boolean
        LANGUAGE sql STABLE AS $$
          SELECT COALESCE(identity.current_role_level(), -1) >= identity.role_level(min_role);
        $$;
        """
    )
    op.execute("GRANT EXECUTE ON FUNCTION identity.role_level(text) TO authenticated, anon")
    op.execute("GRANT EXECUTE ON FUNCTION identity.current_role_level() TO authenticated, anon")
    op.execute("GRANT EXECUTE ON FUNCTION identity.has_role_at_least(text) TO authenticated, anon")

    # -- identity: moderator+ / administrator+ elevated read -----------------------------------
    op.execute(
        "CREATE POLICY users_select_moderator_plus ON identity.users "
        "FOR SELECT USING (identity.has_role_at_least('moderator'))"
    )
    op.execute(
        "CREATE POLICY profiles_select_moderator_plus ON identity.profiles "
        "FOR SELECT USING (identity.has_role_at_least('moderator'))"
    )
    op.execute(
        "CREATE POLICY federated_identities_select_admin_plus ON identity.federated_identities "
        "FOR SELECT USING (identity.has_role_at_least('administrator'))"
    )
    op.execute(
        "CREATE POLICY pats_select_admin_plus ON identity.personal_access_tokens "
        "FOR SELECT USING (identity.has_role_at_least('administrator'))"
    )
    op.execute(
        "CREATE POLICY sessions_select_moderator_plus ON identity.sessions "
        "FOR SELECT USING (identity.has_role_at_least('moderator'))"
    )
    op.execute(
        "CREATE POLICY security_events_select_moderator_plus ON identity.security_events "
        "FOR SELECT USING (identity.has_role_at_least('moderator'))"
    )
    op.execute(
        "CREATE POLICY account_lock_states_select_moderator_plus ON identity.account_lock_states "
        "FOR SELECT USING (identity.has_role_at_least('moderator'))"
    )
    op.execute(
        "CREATE POLICY audit_log_entries_select_admin_plus ON identity.audit_log_entries "
        "FOR SELECT USING (identity.has_role_at_least('administrator'))"
    )

    # -- tenancy: administrator+ support/ops visibility across all orgs ------------------------
    op.execute(
        "CREATE POLICY org_select_admin_plus ON tenancy.organizations "
        "FOR SELECT USING (identity.has_role_at_least('administrator'))"
    )
    op.execute(
        "CREATE POLICY teams_select_admin_plus ON tenancy.teams "
        "FOR SELECT USING (identity.has_role_at_least('administrator'))"
    )
    op.execute(
        "CREATE POLICY memberships_select_admin_plus ON tenancy.memberships "
        "FOR SELECT USING (identity.has_role_at_least('administrator'))"
    )
    op.execute(
        "CREATE POLICY invitations_select_admin_plus ON tenancy.invitations "
        "FOR SELECT USING (identity.has_role_at_least('administrator'))"
    )

    # -- billing: analyst+ cross-subject visibility for business analytics ---------------------
    op.execute(
        "CREATE POLICY subscriptions_select_analyst_plus ON billing.subscriptions "
        "FOR SELECT USING (identity.has_role_at_least('analyst'))"
    )
    op.execute(
        "CREATE POLICY usage_counters_select_analyst_plus ON billing.usage_counters "
        "FOR SELECT USING (identity.has_role_at_least('analyst'))"
    )

    # -- webhooks: administrator+ support/ops visibility across all orgs -----------------------
    op.execute(
        "CREATE POLICY webhook_endpoints_select_admin_plus ON webhooks.webhook_endpoints "
        "FOR SELECT USING (identity.has_role_at_least('administrator'))"
    )
    op.execute(
        "CREATE POLICY webhook_deliveries_select_admin_plus ON webhooks.webhook_deliveries "
        "FOR SELECT USING (identity.has_role_at_least('administrator'))"
    )

    # -- M2-M5 backend/catalog schemas: analyst+ read-only (replaces 0010's no-policy stance) --
    for schema, table in _BACKEND_INTERNAL_TABLES:
        op.execute(
            f"CREATE POLICY {table}_select_analyst_plus ON {schema}.{table} "
            f"FOR SELECT USING (identity.has_role_at_least('analyst'))"
        )
    # sports.alembic_version stays service-role-only (pure schema bookkeeping, not analytics data)


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
                WHERE policyname LIKE '%_moderator_plus' OR policyname LIKE '%_admin_plus'
                   OR policyname LIKE '%_analyst_plus'
            LOOP
                EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', r.policyname, r.schemaname, r.tablename);
            END LOOP;
        END $$;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS identity.has_role_at_least(text)")
    op.execute("DROP FUNCTION IF EXISTS identity.current_role_level()")
    op.execute("DROP FUNCTION IF EXISTS identity.role_level(text)")
