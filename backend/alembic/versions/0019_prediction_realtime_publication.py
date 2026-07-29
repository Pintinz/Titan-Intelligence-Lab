"""Realtime — enable the tables Milestone 9's Part 5 REALTIME spec names ("Live Predictions,
Confidence Changes, Feature Updates, Market Updates, Prediction Status") that didn't already
have a backing publication entry (docs/roadmap.md, same "only tables with a genuine live-update
use case" posture as migration 0014):

  - predictions.predictions        -> Live Predictions, Confidence Changes (embedded in the same
                                       row's `confidence` JSON column), Prediction Status
  - predictions.prediction_markets -> Market Updates
  - predictions.prediction_audits  -> live audit feed for the Admin Control Center (Part 6)
  - features.feature_values_offline -> Feature Updates — named in every milestone's realtime spec
                                       since Milestone 6 but never actually added to the
                                       publication until now; closed here rather than left as a
                                       silent gap.

Postgres-only, same dialect-guard rationale as migration 0014.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_REALTIME_TABLES = [
    ("predictions", "predictions"),
    ("predictions", "prediction_markets"),
    ("predictions", "prediction_audits"),
    ("features", "feature_values_offline"),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for schema, table in _REALTIME_TABLES:
        op.execute(f"ALTER PUBLICATION supabase_realtime ADD TABLE {schema}.{table}")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for schema, table in _REALTIME_TABLES:
        op.execute(f"ALTER PUBLICATION supabase_realtime DROP TABLE {schema}.{table}")
