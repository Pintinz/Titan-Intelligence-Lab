"""Row Level Security — defense-in-depth for direct Supabase-client/PostgREST access
(docs/security.md, docs/roadmap.md Milestone 6 "enable RLS on every user-owned table").

FastAPI is the actual authorization layer (Clean Architecture — Supabase remains
infrastructure only) and always connects via the service-role, which bypasses RLS entirely.
These policies exist so that if anything ever queries Postgres directly with the anon/
authenticated key (a Supabase client SDK, PostgREST, Realtime), it sees only what it should:

  - identity/tenancy/billing/webhooks (genuinely user/org-owned M6 data): real ownership and
    org-membership policies, keyed off ``auth.uid()`` — which equals ``identity.users.id``
    because ``IdentityService.ensure_provisioned`` provisions the shadow user row with that
    same id (docs/authentication.md).
  - identity.security_events / account_lock_states / audit_log_entries: RLS enabled, NO
    policies at all — these are security-internal, never read directly by end users, only by
    FastAPI's service-role connection or an admin-gated API endpoint.
  - sports/admin/features/ingestion/knowledge_graph (M2-M5 backend/catalog data): RLS enabled,
    NO policies — there is no per-user ownership concept for this data; it is populated by the
    ingestion pipeline and read by FastAPI only, so default-deny for anon/authenticated is
    correct as-is.

Postgres-only: SQLite (the fast offline test suite) has no ``auth.uid()``/RLS support, so this
migration no-ops there (docs/decisions.md — same dialect-guard rationale considered for any
Postgres-specific DDL in a migration history shared with SQLite tests).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-25
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_BACKEND_INTERNAL_TABLES = [
    ("sports", "sports"), ("sports", "venues"), ("sports", "competitions"), ("sports", "seasons"),
    ("sports", "teams"), ("sports", "players"), ("sports", "coaching_staff"), ("sports", "officials"),
    ("sports", "fixtures"), ("sports", "matches"), ("sports", "match_events"), ("sports", "team_statistics"),
    ("sports", "player_statistics"), ("sports", "standings"), ("sports", "injuries"), ("sports", "suspensions"),
    ("sports", "transfers"), ("sports", "rankings"), ("sports", "countries"), ("sports", "lineups"),
    ("sports", "alembic_version"),
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

_SECURITY_INTERNAL_TABLES = [
    ("identity", "security_events"), ("identity", "account_lock_states"), ("identity", "audit_log_entries"),
]

_NO_POLICY_TABLES = _BACKEND_INTERNAL_TABLES + _SECURITY_INTERNAL_TABLES


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for schema, table in _NO_POLICY_TABLES:
        op.execute(f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY")

    # -- helper functions (SECURITY DEFINER so they see all of tenancy.memberships regardless
    # of the calling role's own RLS visibility — the standard Supabase pattern for permission-
    # check helpers used inside another table's policy, avoiding RLS recursion) ----------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tenancy.is_org_member(org_id uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = tenancy, pg_temp AS $$
          SELECT EXISTS (
            SELECT 1 FROM tenancy.memberships m
            WHERE m.organization_id = org_id AND m.user_id = auth.uid()
          );
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tenancy.is_org_admin(org_id uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = tenancy, pg_temp AS $$
          SELECT EXISTS (
            SELECT 1 FROM tenancy.memberships m
            WHERE m.organization_id = org_id AND m.user_id = auth.uid() AND m.role IN ('owner', 'admin')
          );
        $$;
        """
    )
    op.execute("GRANT EXECUTE ON FUNCTION tenancy.is_org_member(uuid) TO authenticated, anon")
    op.execute("GRANT EXECUTE ON FUNCTION tenancy.is_org_admin(uuid) TO authenticated, anon")

    # -- identity -----------------------------------------------------------------------------
    op.execute("ALTER TABLE identity.users ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY users_select_self ON identity.users FOR SELECT USING (id = auth.uid())")

    op.execute("ALTER TABLE identity.profiles ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY profiles_select_self ON identity.profiles FOR SELECT USING (user_id = auth.uid())")
    op.execute("CREATE POLICY profiles_insert_self ON identity.profiles FOR INSERT WITH CHECK (user_id = auth.uid())")
    op.execute(
        "CREATE POLICY profiles_update_self ON identity.profiles FOR UPDATE "
        "USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())"
    )

    op.execute("ALTER TABLE identity.federated_identities ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY federated_identities_select_self ON identity.federated_identities "
        "FOR SELECT USING (user_id = auth.uid())"
    )
    op.execute(
        "CREATE POLICY federated_identities_delete_self ON identity.federated_identities "
        "FOR DELETE USING (user_id = auth.uid())"
    )

    op.execute("ALTER TABLE identity.personal_access_tokens ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY pats_select_self ON identity.personal_access_tokens FOR SELECT USING (user_id = auth.uid())"
    )
    op.execute(
        "CREATE POLICY pats_delete_self ON identity.personal_access_tokens FOR DELETE USING (user_id = auth.uid())"
    )

    op.execute("ALTER TABLE identity.sessions ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY sessions_select_self ON identity.sessions FOR SELECT USING (user_id = auth.uid())")
    op.execute("CREATE POLICY sessions_delete_self ON identity.sessions FOR DELETE USING (user_id = auth.uid())")

    for schema, table in _SECURITY_INTERNAL_TABLES:
        op.execute(f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY")

    # -- tenancy ------------------------------------------------------------------------------
    op.execute("ALTER TABLE tenancy.organizations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY org_select_members ON tenancy.organizations "
        "FOR SELECT USING (tenancy.is_org_member(id))"
    )
    op.execute(
        "CREATE POLICY org_insert_self_owner ON tenancy.organizations "
        "FOR INSERT WITH CHECK (owner_user_id = auth.uid())"
    )
    op.execute(
        "CREATE POLICY org_update_admins ON tenancy.organizations "
        "FOR UPDATE USING (tenancy.is_org_admin(id)) WITH CHECK (tenancy.is_org_admin(id))"
    )
    op.execute(
        "CREATE POLICY org_delete_owner ON tenancy.organizations FOR DELETE USING (owner_user_id = auth.uid())"
    )

    op.execute("ALTER TABLE tenancy.teams ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY teams_select_members ON tenancy.teams "
        "FOR SELECT USING (tenancy.is_org_member(organization_id))"
    )
    op.execute(
        "CREATE POLICY teams_write_admins ON tenancy.teams FOR ALL "
        "USING (tenancy.is_org_admin(organization_id)) WITH CHECK (tenancy.is_org_admin(organization_id))"
    )

    op.execute("ALTER TABLE tenancy.memberships ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY memberships_select_org_members ON tenancy.memberships "
        "FOR SELECT USING (tenancy.is_org_member(organization_id))"
    )
    op.execute(
        "CREATE POLICY memberships_write_admins ON tenancy.memberships FOR ALL "
        "USING (tenancy.is_org_admin(organization_id)) WITH CHECK (tenancy.is_org_admin(organization_id))"
    )

    op.execute("ALTER TABLE tenancy.invitations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY invitations_select_admins_or_invitee ON tenancy.invitations FOR SELECT USING "
        "(tenancy.is_org_admin(organization_id) OR email = (auth.jwt() ->> 'email'))"
    )
    op.execute(
        "CREATE POLICY invitations_write_admins ON tenancy.invitations FOR ALL "
        "USING (tenancy.is_org_admin(organization_id)) WITH CHECK (tenancy.is_org_admin(organization_id))"
    )

    # -- billing ------------------------------------------------------------------------------
    op.execute("ALTER TABLE billing.plans ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY plans_select_public ON billing.plans FOR SELECT USING (true)")

    op.execute("ALTER TABLE billing.entitlements ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY entitlements_select_public ON billing.entitlements FOR SELECT USING (true)")

    op.execute("ALTER TABLE billing.subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY subscriptions_select_owner ON billing.subscriptions FOR SELECT USING ("
        "  (subject_type = 'user' AND subject_id = auth.uid()::text)"
        "  OR (subject_type = 'organization' AND tenancy.is_org_member(subject_id::uuid))"
        ")"
    )

    op.execute("ALTER TABLE billing.usage_counters ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY usage_counters_select_owner ON billing.usage_counters FOR SELECT USING ("
        "  (subject_type = 'user' AND subject_id = auth.uid()::text)"
        "  OR (subject_type = 'organization' AND tenancy.is_org_member(subject_id::uuid))"
        ")"
    )

    # -- webhooks -----------------------------------------------------------------------------
    op.execute("ALTER TABLE webhooks.webhook_endpoints ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY webhook_endpoints_admins ON webhooks.webhook_endpoints FOR ALL "
        "USING (tenancy.is_org_admin(organization_id::uuid)) WITH CHECK (tenancy.is_org_admin(organization_id::uuid))"
    )

    op.execute("ALTER TABLE webhooks.webhook_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY webhook_deliveries_select_admins ON webhooks.webhook_deliveries FOR SELECT USING ("
        "  EXISTS ("
        "    SELECT 1 FROM webhooks.webhook_endpoints e"
        "    WHERE e.id = webhook_deliveries.endpoint_id AND tenancy.is_org_admin(e.organization_id::uuid)"
        "  )"
        ")"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    policy_tables = [
        ("identity", "users"), ("identity", "profiles"), ("identity", "federated_identities"),
        ("identity", "personal_access_tokens"), ("identity", "sessions"),
        ("tenancy", "organizations"), ("tenancy", "teams"), ("tenancy", "memberships"), ("tenancy", "invitations"),
        ("billing", "plans"), ("billing", "entitlements"), ("billing", "subscriptions"), ("billing", "usage_counters"),
        ("webhooks", "webhook_endpoints"), ("webhooks", "webhook_deliveries"),
    ]
    op.execute(
        """
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT schemaname, tablename, policyname FROM pg_policies
                WHERE schemaname IN ('identity', 'tenancy', 'billing', 'webhooks')
            LOOP
                EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', r.policyname, r.schemaname, r.tablename);
            END LOOP;
        END $$;
        """
    )

    op.execute("DROP FUNCTION IF EXISTS tenancy.is_org_admin(uuid)")
    op.execute("DROP FUNCTION IF EXISTS tenancy.is_org_member(uuid)")

    for schema, table in policy_tables + _SECURITY_INTERNAL_TABLES + _BACKEND_INTERNAL_TABLES:
        op.execute(f"ALTER TABLE {schema}.{table} DISABLE ROW LEVEL SECURITY")
