"""Identity, Tenancy, Billing, and Webhooks schemas — Enterprise Supabase Platform & Identity
(docs/roadmap.md Milestone 6, docs/security.md, docs/decisions.md).

Four schemas land together because they were designed as one milestone-scoped unit: identity
(users/profiles/federated auth/PATs/sessions/security events/audit), tenancy
(organizations/teams/memberships/invitations), billing (plans/entitlements/subscriptions/usage),
and webhooks (endpoint registration/delivery bookkeeping for future payment/integration
providers) — same rationale as migration 0002 bundling all of Provider Management + Health
Intelligence into one admin-schema migration.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-25
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

IDENTITY = "identity"
TENANCY = "tenancy"
BILLING = "billing"
WEBHOOKS = "webhooks"


def upgrade() -> None:
    # -- identity ---------------------------------------------------------------------------------
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {IDENTITY}")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="free"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_verification"),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        schema=IDENTITY,
    )

    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(f"{IDENTITY}.users.id"), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("locale", sa.String(16), nullable=False, server_default="en"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        schema=IDENTITY,
    )

    op.create_table(
        "federated_identities",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(f"{IDENTITY}.users.id"), nullable=False, index=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("provider_email", sa.String(320), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_federated_identity_provider_ref"),
        schema=IDENTITY,
    )

    op.create_table(
        "personal_access_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(f"{IDENTITY}.users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        schema=IDENTITY,
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(f"{IDENTITY}.users.id"), nullable=False, index=True),
        sa.Column("device_label", sa.String(200), nullable=True),
        sa.Column("browser", sa.String(120), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("risk_indicators", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        schema=IDENTITY,
    )

    op.create_table(
        "security_events",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("event_type", sa.String(32), nullable=False, index=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(f"{IDENTITY}.users.id"), nullable=True, index=True),
        sa.Column("email_attempted", sa.String(320), nullable=True, index=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False, server_default="{}"),
        schema=IDENTITY,
    )

    op.create_table(
        "account_lock_states",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey(f"{IDENTITY}.users.id"), primary_key=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        schema=IDENTITY,
    )

    op.create_table(
        "audit_log_entries",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("action", sa.String(64), nullable=False, index=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey(f"{IDENTITY}.users.id"), nullable=True, index=True),
        sa.Column("target_type", sa.String(64), nullable=True, index=True),
        sa.Column("target_id", sa.String(64), nullable=True, index=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False, server_default="{}"),
        schema=IDENTITY,
    )

    # -- tenancy ----------------------------------------------------------------------------------
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {TENANCY}")

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False, unique=True, index=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        schema=TENANCY,
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey(f"{TENANCY}.organizations.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=TENANCY,
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey(f"{TENANCY}.organizations.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey(f"{TENANCY}.teams.id"), nullable=True, index=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        schema=TENANCY,
    )

    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey(f"{TENANCY}.organizations.id"), nullable=False, index=True),
        sa.Column("email", sa.String(320), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        schema=TENANCY,
    )

    # -- billing ----------------------------------------------------------------------------------
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {BILLING}")

    op.create_table(
        "plans",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("key", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("billing_period", sa.String(16), nullable=False, server_default="monthly"),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=BILLING,
    )

    op.create_table(
        "entitlements",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey(f"{BILLING}.plans.id"), nullable=False, index=True),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.UniqueConstraint("plan_id", "feature_key", name="uq_entitlement_plan_feature"),
        schema=BILLING,
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("subject_type", sa.String(16), nullable=False, index=True),
        sa.Column("subject_id", sa.String(64), nullable=False, index=True),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey(f"{BILLING}.plans.id"), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        schema=BILLING,
    )

    op.create_table(
        "usage_counters",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("subject_type", sa.String(16), nullable=False, index=True),
        sa.Column("subject_id", sa.String(64), nullable=False, index=True),
        sa.Column("feature_key", sa.String(200), nullable=False, index=True),
        sa.Column("window_key", sa.String(16), nullable=False),
        sa.Column("used_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("subject_type", "subject_id", "feature_key", "window_key", name="uq_usage_counter_window"),
        schema=BILLING,
    )

    # -- webhooks ----------------------------------------------------------------------------------
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {WEBHOOKS}")

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("signing_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("subscribed_events", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        schema=WEBHOOKS,
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "endpoint_id", sa.Uuid(), sa.ForeignKey(f"{WEBHOOKS}.webhook_endpoints.id"), nullable=False, index=True
        ),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=WEBHOOKS,
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries", schema=WEBHOOKS)
    op.drop_table("webhook_endpoints", schema=WEBHOOKS)
    op.execute(f"DROP SCHEMA IF EXISTS {WEBHOOKS} CASCADE")

    op.drop_table("usage_counters", schema=BILLING)
    op.drop_table("subscriptions", schema=BILLING)
    op.drop_table("entitlements", schema=BILLING)
    op.drop_table("plans", schema=BILLING)
    op.execute(f"DROP SCHEMA IF EXISTS {BILLING} CASCADE")

    op.drop_table("invitations", schema=TENANCY)
    op.drop_table("memberships", schema=TENANCY)
    op.drop_table("teams", schema=TENANCY)
    op.drop_table("organizations", schema=TENANCY)
    op.execute(f"DROP SCHEMA IF EXISTS {TENANCY} CASCADE")

    op.drop_table("audit_log_entries", schema=IDENTITY)
    op.drop_table("account_lock_states", schema=IDENTITY)
    op.drop_table("security_events", schema=IDENTITY)
    op.drop_table("sessions", schema=IDENTITY)
    op.drop_table("personal_access_tokens", schema=IDENTITY)
    op.drop_table("federated_identities", schema=IDENTITY)
    op.drop_table("profiles", schema=IDENTITY)
    op.drop_table("users", schema=IDENTITY)
    op.execute(f"DROP SCHEMA IF EXISTS {IDENTITY} CASCADE")
