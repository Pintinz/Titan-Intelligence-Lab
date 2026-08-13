"""Milestone 9 — News Intelligence Foundation & Market-Specific Impact Engine.

Additive-only. Extends `intelligence.news_events` with the same class of provenance columns
Milestone 5 added to structured intelligence (`fetched_at`/`sync_run_id`/
`availability_classification`/`information_available_at`), plus News-specific fields: a
resolution-status-aware entity list (`resolved_entities`, replacing the pre-Milestone-9 flat,
resolution-status-blind `affected_entity_refs` union as the authoritative source — see
`EventExtractionService.extract_and_record`'s docstring), the formal 6-tier confidence taxonomy
(`confidence_tier`), and a validity window (`validity_start`/`validity_end`).

No column removed, renamed, or reinterpreted. Every existing row (all 68 at time of writing, all
MockGeminiAdapter-originated per docs/milestone3_historical_data_audit.md) gets
`availability_classification='UNKNOWN_AVAILABILITY_TIME'`, `confidence_tier='uncertain'`,
`resolved_entities=[]`, and every timestamp/id column NULL — honest, since none of them were ever
synced via a genuine `LIVE_SCHEDULED`-equivalent pipeline. Never backfilled retroactively.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_events",
        sa.Column("resolved_entities", sa.JSON(), nullable=False, server_default="[]"),
        schema="intelligence",
    )
    op.add_column(
        "news_events",
        sa.Column("confidence_tier", sa.String(16), nullable=False, server_default="uncertain"),
        schema="intelligence",
    )
    op.add_column(
        "news_events",
        sa.Column("information_available_at", sa.DateTime(timezone=True), nullable=True),
        schema="intelligence",
    )
    op.add_column(
        "news_events",
        sa.Column(
            "availability_classification", sa.String(32), nullable=False, server_default="UNKNOWN_AVAILABILITY_TIME"
        ),
        schema="intelligence",
    )
    op.add_column(
        "news_events", sa.Column("validity_start", sa.DateTime(timezone=True), nullable=True), schema="intelligence"
    )
    op.add_column(
        "news_events", sa.Column("validity_end", sa.DateTime(timezone=True), nullable=True), schema="intelligence"
    )
    op.add_column(
        "news_events", sa.Column("sync_run_id", sa.String(36), nullable=True), schema="intelligence"
    )


def downgrade() -> None:
    for column in (
        "sync_run_id", "validity_end", "validity_start", "availability_classification",
        "information_available_at", "confidence_tier", "resolved_entities",
    ):
        op.drop_column("news_events", column, schema="intelligence")
