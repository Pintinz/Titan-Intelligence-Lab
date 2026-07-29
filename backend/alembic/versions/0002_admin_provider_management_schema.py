"""Admin schema — Provider Management System + Health Intelligence (docs/admin_center.md §2)

Milestone 3 built the Provider Management System's SQLAlchemy models but this migration was
never written at the time (caught while extending the schema for Health Intelligence) — this
revision covers the full `admin` schema as it exists now: everything from Milestone 3
(providers, credentials, usage records, health checks) plus the Health Intelligence addition
(health state, incidents).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-25
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SCHEMA = "admin"


def _admin_timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "providers",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("key", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="inactive"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("daily_quota_limit", sa.Integer(), nullable=True),
        sa.Column("monthly_quota_limit", sa.Integer(), nullable=True),
        sa.Column("cache_ttl_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        *_admin_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.providers.id"), nullable=False, index=True),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_admin_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "provider_usage_records",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.providers.id"), nullable=False, index=True),
        sa.Column(
            "credential_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.provider_credentials.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("window_key", sa.String(16), nullable=False, index=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "provider_id", "credential_id", "period", "window_key", name="uq_provider_usage_window"
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "provider_health_checks",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.providers.id"), nullable=False, index=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "provider_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.providers.id"), nullable=False, index=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger", sa.Text(), nullable=False),
        *_admin_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "provider_health_state",
        sa.Column("provider_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.providers.id"), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="healthy"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_successes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "open_incident_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.provider_incidents.id"), nullable=True
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "provider_health_state",
        "provider_incidents",
        "provider_health_checks",
        "provider_usage_records",
        "provider_credentials",
        "providers",
    ):
        op.drop_table(table, schema=SCHEMA)

    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
