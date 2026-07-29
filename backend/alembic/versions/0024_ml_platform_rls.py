"""Row Level Security for the 7 Milestone 9.1 ML Platform tables (migration 0023) — same
`identity.has_role_at_least('analyst')` tier as the existing Model Registry/Dataset internals
(`models`, `feature_market_mappings`, `experiments`, migration 0021 `_ANALYST_TABLES`): none of
these 7 tables are read directly by an app user (no `/api/v1/*` route serves them unfiltered the
way `predictions`/`prediction_markets` are) — they're Dataset Platform, Training Platform,
Calibration/SHAP, Model Monitoring, and Model Serving internals, exactly the same shape as the
Model Registry tables they extend. No new SQL functions, no write policies (writes stay on
FastAPI's service-role connection) — same posture as every RLS migration since 0010.

Postgres-only, same dialect-guard rationale as 0010-0012/0021/0022. GRANT already covered by
migration 0020's `ALTER DEFAULT PRIVILEGES` (see 0023's docstring) — no GRANT step needed here.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

_ANALYST_TABLES = [
    "datasets",
    "training_runs",
    "calibration_reports",
    "feature_importance_reports",
    "latency_samples",
    "retraining_jobs",
    "model_artifacts",
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in _ANALYST_TABLES:
        op.execute(f"ALTER TABLE predictions.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_select_analyst_plus ON predictions.{table} "
            f"FOR SELECT USING (identity.has_role_at_least('analyst'))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in _ANALYST_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_select_analyst_plus ON predictions.{table}")
        op.execute(f"ALTER TABLE predictions.{table} DISABLE ROW LEVEL SECURITY")
