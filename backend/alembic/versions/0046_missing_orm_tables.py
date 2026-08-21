"""Create three tables declared in the ORM but never captured by any migration.

Found live (2026-08-22) migrating real data to production Postgres for the first time:
`sports.market_lines` (real, 9,022-row table — provider sportsbook quotes), and
`predictions.calibration_parameters` / `predictions.challenger_evaluations` (both currently
empty) exist in their modules' SQLAlchemy ``Base.metadata`` and therefore get created by
``scripts/init_local_sqlite_db.py``'s ``Base.metadata.create_all()`` in every local dev.db — but
no migration ever created them, so a database built purely from ``alembic upgrade head`` (i.e.
every real deploy) has always been missing all three. RLS-enabled with no policies, matching
0010's treatment of every other backend-internal (non-user-owned) table in these two schemas —
these three didn't exist yet when 0010 was written, the same gap 0035 already closed once for
watchlist/alerts.

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-22
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

SPORTS = "sports"
PREDICTIONS = "predictions"

_NEW_NO_POLICY_TABLES = [
    (SPORTS, "market_lines"),
    (PREDICTIONS, "calibration_parameters"),
    (PREDICTIONS, "challenger_evaluations"),
]


def upgrade() -> None:
    op.create_table(
        "market_lines",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("fixture_id", sa.Uuid(), sa.ForeignKey(f"{SPORTS}.fixtures.id"), nullable=False, index=True),
        sa.Column("sport_code", sa.String(32), nullable=False, index=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("bookmaker", sa.String(128), nullable=False),
        sa.Column("market_type", sa.String(32), nullable=False, index=True),
        sa.Column("selection", sa.String(16), nullable=False),
        sa.Column("line", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("team_side", sa.String(8), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=SPORTS,
    )

    op.create_table(
        "calibration_parameters",
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey(f"{PREDICTIONS}.models.id"), primary_key=True),
        sa.Column("a", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("b", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fitted_at", sa.DateTime(timezone=True), nullable=False),
        schema=PREDICTIONS,
    )

    op.create_table(
        "challenger_evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "market_id", sa.Uuid(), sa.ForeignKey(f"{PREDICTIONS}.prediction_markets.id"), nullable=False,
            index=True,
        ),
        sa.Column("challenger_model_id", sa.Uuid(), sa.ForeignKey(f"{PREDICTIONS}.models.id"), nullable=False),
        sa.Column("champion_model_id", sa.Uuid(), sa.ForeignKey(f"{PREDICTIONS}.models.id"), nullable=True),
        sa.Column("challenger_metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("champion_metrics", sa.JSON(), nullable=True),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("decisive_metric", sa.String(64), nullable=False),
        sa.Column("holdout_sample_count", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, index=True),
        schema=PREDICTIONS,
    )

    if op.get_bind().dialect.name == "postgresql":
        for schema, table in _NEW_NO_POLICY_TABLES:
            op.execute(f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for schema, table in reversed(_NEW_NO_POLICY_TABLES):
            op.execute(f"ALTER TABLE {schema}.{table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("challenger_evaluations", schema=PREDICTIONS)
    op.drop_table("calibration_parameters", schema=PREDICTIONS)
    op.drop_table("market_lines", schema=SPORTS)
