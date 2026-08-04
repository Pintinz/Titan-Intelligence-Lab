"""Provider Registry field expansion (docs/admin_center.md §2, Milestone 11B)

Additive-only: extends `admin.providers` with the connection/lifecycle metadata the
Operations Center's Provider Registry UI needs (base URL, auth type, region, version,
environment, timeout/retry policy, created_by/updated_by) so an admin can fully describe a
provider through the API instead of only the handful of fields Milestone 3 originally modeled.
All new columns are nullable or carry a server default — no existing row, query, or service
method that predates this migration is affected.

Also switches every `provider_id`/`credential_id` foreign key back to `providers`/
`provider_credentials` to `ON DELETE CASCADE` — needed for the new `DELETE
/api/v1/admin/providers/{id}` endpoint to remove a provider's full history in one call instead
of failing with a foreign-key violation. Existing rows and existing read/write paths are
unaffected; this only changes what happens on a provider delete, which was not possible before
this milestone (no delete endpoint existed).

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

SCHEMA = "admin"
TABLE = "providers"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("base_url", sa.String(512), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("auth_type", sa.String(32), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("region", sa.String(64), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("version", sa.String(32), nullable=True), schema=SCHEMA)
    op.add_column(
        TABLE, sa.Column("environment", sa.String(32), nullable=False, server_default="production"), schema=SCHEMA
    )
    op.add_column(
        TABLE, sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="10"), schema=SCHEMA
    )
    op.add_column(TABLE, sa.Column("retry_count", sa.Integer(), nullable=False, server_default="2"), schema=SCHEMA)
    op.add_column(
        TABLE, sa.Column("retry_delay_seconds", sa.Integer(), nullable=False, server_default="1"), schema=SCHEMA
    )
    op.add_column(TABLE, sa.Column("created_by", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("updated_by", sa.Uuid(), nullable=True), schema=SCHEMA)

    # provider_id / credential_id FKs -> ON DELETE CASCADE, so a provider delete removes its
    # full history (credentials, usage, health checks, incidents, materialized health state)
    # instead of raising a foreign-key violation. Postgres-only — the RLS/schema conventions
    # this repo follows elsewhere already assume a Postgres target for real deployments; SQLite
    # test fixtures rebuild from models.py's ondelete="CASCADE" directly, not via this migration.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("provider_credentials_provider_id_fkey", "provider_credentials", schema=SCHEMA, type_="foreignkey")
        op.create_foreign_key(
            "provider_credentials_provider_id_fkey", "provider_credentials", "providers",
            ["provider_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
        )

        op.drop_constraint("provider_usage_records_provider_id_fkey", "provider_usage_records", schema=SCHEMA, type_="foreignkey")
        op.create_foreign_key(
            "provider_usage_records_provider_id_fkey", "provider_usage_records", "providers",
            ["provider_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
        )
        op.drop_constraint("provider_usage_records_credential_id_fkey", "provider_usage_records", schema=SCHEMA, type_="foreignkey")
        op.create_foreign_key(
            "provider_usage_records_credential_id_fkey", "provider_usage_records", "provider_credentials",
            ["credential_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
        )

        op.drop_constraint("provider_health_checks_provider_id_fkey", "provider_health_checks", schema=SCHEMA, type_="foreignkey")
        op.create_foreign_key(
            "provider_health_checks_provider_id_fkey", "provider_health_checks", "providers",
            ["provider_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
        )

        op.drop_constraint("provider_incidents_provider_id_fkey", "provider_incidents", schema=SCHEMA, type_="foreignkey")
        op.create_foreign_key(
            "provider_incidents_provider_id_fkey", "provider_incidents", "providers",
            ["provider_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
        )

        op.drop_constraint("provider_health_state_provider_id_fkey", "provider_health_state", schema=SCHEMA, type_="foreignkey")
        op.create_foreign_key(
            "provider_health_state_provider_id_fkey", "provider_health_state", "providers",
            ["provider_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for child, column, parent, fk_name in (
            ("provider_credentials", "provider_id", "providers", "provider_credentials_provider_id_fkey"),
            ("provider_usage_records", "provider_id", "providers", "provider_usage_records_provider_id_fkey"),
            ("provider_usage_records", "credential_id", "provider_credentials", "provider_usage_records_credential_id_fkey"),
            ("provider_health_checks", "provider_id", "providers", "provider_health_checks_provider_id_fkey"),
            ("provider_incidents", "provider_id", "providers", "provider_incidents_provider_id_fkey"),
            ("provider_health_state", "provider_id", "providers", "provider_health_state_provider_id_fkey"),
        ):
            op.drop_constraint(fk_name, child, schema=SCHEMA, type_="foreignkey")
            op.create_foreign_key(fk_name, child, parent, [column], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA)

    for column in (
        "updated_by",
        "created_by",
        "retry_delay_seconds",
        "retry_count",
        "timeout_seconds",
        "environment",
        "version",
        "region",
        "auth_type",
        "base_url",
    ):
        op.drop_column(TABLE, column, schema=SCHEMA)
