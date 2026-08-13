"""Milestone 5 — Verified Pre-Match Data Availability.

Additive-only. Adds `fetched_at`/`sync_run_id` to `sports.injuries`/`sports.suspensions`/
`sports.transfers`/`sports.lineups` — the two new provenance-traceability columns
(modules.ingestion.application.provenance's module docstring) alongside Milestone 4's existing
`availability_classification`/`information_available_at` pair on the same four tables. No column
removed, renamed, or reinterpreted; every existing row gets `fetched_at=NULL`/`sync_run_id=NULL`
(honest — those rows predate this milestone's tracking, never backfilled retroactively).

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

_TABLES = ("injuries", "suspensions", "transfers", "lineups")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True), schema="sports")
        op.add_column(table, sa.Column("sync_run_id", sa.String(64), nullable=True), schema="sports")


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "sync_run_id", schema="sports")
        op.drop_column(table, "fetched_at", schema="sports")
