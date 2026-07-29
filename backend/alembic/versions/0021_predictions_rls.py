"""Row Level Security for the `predictions` schema (Milestone 9) — extends migrations 0010/0011
(docs/security.md, docs/decisions.md ADR-026) to the tables migration 0018 added, using the
exact same building blocks: `identity.has_role_at_least(min_role)` for the ordinal RBAC-ladder
threshold check, no new SQL functions, no write policies (every write continues through
FastAPI's service-role connection, which bypasses RLS entirely).

Two access tiers, chosen by what each table actually is:

- **App-facing product data** (`prediction_markets`, `predictions`) — the data
  `/api/v1/predictions`/`/api/v1/markets` actually serve to any logged-in user
  (`get_current_user`, no role gate). RLS mirrors that: `has_role_at_least('free')` — every real
  authenticated user, the lowest real tier on the ladder — same flat-threshold shape as every
  other elevated-read policy in this codebase, not a new filtering mechanism. Unfiltered by
  status, matching how `billing.plans`/`billing.entitlements` are unfiltered "SELECT: public"
  despite also having a lifecycle concept — this migration does not introduce row-level status
  filtering where no existing policy does.
- **Registry/operational data** (`feature_market_mappings`, `models`, `prediction_outcomes`,
  `model_evaluations`, `experiments`) — never read directly by an app user; `analyst+`, same as
  the M2-M5 backend/catalog schemas (rls.md §6).
- **`prediction_audits`** — who performed what action on what entity, structurally identical to
  `identity.audit_log_entries`, which is `administrator+`-only (not analyst+) precisely because
  it's an audit trail, not analytics data. Mirrored here for the same reason. No table gets a
  write or update/delete policy at all, so every audit/history table (`prediction_audits`,
  `prediction_outcomes`, `model_evaluations`, `experiments`) is append-only from any role's
  perspective except the service-role connection.

Postgres-only, same dialect-guard rationale as 0010/0011. Requires migration 0020's GRANTs to
have run first (ADR-027) — without them, these policies would be unreachable code.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_APP_FACING_TABLES = ["prediction_markets", "predictions"]
_ANALYST_TABLES = ["feature_market_mappings", "models", "prediction_outcomes", "model_evaluations", "experiments"]
_ADMIN_ONLY_TABLES = ["prediction_audits"]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in _APP_FACING_TABLES + _ANALYST_TABLES + _ADMIN_ONLY_TABLES:
        op.execute(f"ALTER TABLE predictions.{table} ENABLE ROW LEVEL SECURITY")

    for table in _APP_FACING_TABLES:
        op.execute(
            f"CREATE POLICY {table}_select_free_plus ON predictions.{table} "
            f"FOR SELECT USING (identity.has_role_at_least('free'))"
        )

    for table in _ANALYST_TABLES:
        op.execute(
            f"CREATE POLICY {table}_select_analyst_plus ON predictions.{table} "
            f"FOR SELECT USING (identity.has_role_at_least('analyst'))"
        )

    for table in _ADMIN_ONLY_TABLES:
        op.execute(
            f"CREATE POLICY {table}_select_admin_plus ON predictions.{table} "
            f"FOR SELECT USING (identity.has_role_at_least('administrator'))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in _APP_FACING_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_select_free_plus ON predictions.{table}")
    for table in _ANALYST_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_select_analyst_plus ON predictions.{table}")
    for table in _ADMIN_ONLY_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_select_admin_plus ON predictions.{table}")
    for table in _APP_FACING_TABLES + _ANALYST_TABLES + _ADMIN_ONLY_TABLES:
        op.execute(f"ALTER TABLE predictions.{table} DISABLE ROW LEVEL SECURITY")
