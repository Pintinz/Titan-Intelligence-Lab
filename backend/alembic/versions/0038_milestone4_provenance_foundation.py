"""Milestone 4 — data/feature provenance foundation

Additive-only, no destructive changes, no column removed or renamed. Implements the schema
side of TitanIQ's Milestone 4 (Data & Feature Foundation Hardening), following the Milestone 3
historical-data audit's findings (docs/milestone3_historical_data_audit.md).

1. FK indexes flagged missing by Milestone 1/3 (`sports.fixtures.home_team_id`/`away_team_id`/
   `venue_id`, `sports.teams.venue_id`, `sports.match_events.team_id`/`player_id`,
   `predictions.prediction_audits.market_id`/`model_id`) — index-only, no column change.
2. `availability_classification` (+ `information_available_at`) on `sports.injuries`,
   `sports.suspensions`, `sports.transfers`, `sports.lineups` — the KNOWN_BEFORE_EVENT /
   UNKNOWN / KNOWN_AFTER_EVENT concept (named VERIFIED_PRE_MATCH / VERIFIED_POST_MATCH /
   UNKNOWN_AVAILABILITY_TIME for injuries specifically, same 3-state concept, more specific
   naming) — defaults every existing and future row to UNKNOWN_AVAILABILITY_TIME until a real
   verification pass classifies it otherwise. Never auto-classified as pre-match by default.
3. `predictions.models.provenance_status` — PROVENANCE_VERIFIED / PROVENANCE_UNVERIFIED,
   defaults every existing row to PROVENANCE_UNVERIFIED (honest default; a model earns
   PROVENANCE_VERIFIED only after an explicit provenance trace, see
   `scripts/trace_football_champion_provenance.py`).
4. `features.feature_definitions.leakage_classification` — PRE_MATCH_SAFE / POST_MATCH_ONLY /
   POINT_IN_TIME_REQUIRED / UNKNOWN_PROVENANCE, defaults every existing row to
   UNKNOWN_PROVENANCE (complements, does not replace, the existing `leakage_reviewed` boolean).
5. `intelligence.news_articles.information_available_at` — groundwork only (Milestone 4 item 9
   explicitly forbids activating this), nullable, unpopulated by this migration.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- 1. Missing FK indexes (Milestone 1/3 finding) -----------------------------------------
    op.create_index("ix_fixtures_home_team_id", "fixtures", ["home_team_id"], schema="sports")
    op.create_index("ix_fixtures_away_team_id", "fixtures", ["away_team_id"], schema="sports")
    op.create_index("ix_fixtures_venue_id", "fixtures", ["venue_id"], schema="sports")
    op.create_index("ix_teams_venue_id", "teams", ["venue_id"], schema="sports")
    op.create_index("ix_match_events_team_id", "match_events", ["team_id"], schema="sports")
    op.create_index("ix_match_events_player_id", "match_events", ["player_id"], schema="sports")
    op.create_index("ix_prediction_audits_market_id", "prediction_audits", ["market_id"], schema="predictions")
    op.create_index("ix_prediction_audits_model_id", "prediction_audits", ["model_id"], schema="predictions")

    # -- 2. Structured-intelligence availability classification ---------------------------------
    for table in ("injuries", "suspensions", "transfers", "lineups"):
        op.add_column(
            table,
            sa.Column("availability_classification", sa.String(32), nullable=False, server_default="UNKNOWN_AVAILABILITY_TIME"),
            schema="sports",
        )
        op.add_column(table, sa.Column("information_available_at", sa.DateTime(timezone=True), nullable=True), schema="sports")

    # -- 3. Model provenance status --------------------------------------------------------------
    op.add_column(
        "models",
        sa.Column("provenance_status", sa.String(24), nullable=False, server_default="PROVENANCE_UNVERIFIED"),
        schema="predictions",
    )

    # -- 4. Feature Registry leakage classification ----------------------------------------------
    op.add_column(
        "feature_definitions",
        sa.Column("leakage_classification", sa.String(32), nullable=False, server_default="UNKNOWN_PROVENANCE"),
        schema="features",
    )

    # -- 5. News temporal-foundation groundwork (unpopulated — see module docstring) ------------
    op.add_column(
        "news_articles",
        sa.Column("information_available_at", sa.DateTime(timezone=True), nullable=True),
        schema="intelligence",
    )


def downgrade() -> None:
    op.drop_column("news_articles", "information_available_at", schema="intelligence")
    op.drop_column("feature_definitions", "leakage_classification", schema="features")
    op.drop_column("models", "provenance_status", schema="predictions")
    for table in ("injuries", "suspensions", "transfers", "lineups"):
        op.drop_column(table, "information_available_at", schema="sports")
        op.drop_column(table, "availability_classification", schema="sports")
    op.drop_index("ix_prediction_audits_model_id", table_name="prediction_audits", schema="predictions")
    op.drop_index("ix_prediction_audits_market_id", table_name="prediction_audits", schema="predictions")
    op.drop_index("ix_match_events_player_id", table_name="match_events", schema="sports")
    op.drop_index("ix_match_events_team_id", table_name="match_events", schema="sports")
    op.drop_index("ix_teams_venue_id", table_name="teams", schema="sports")
    op.drop_index("ix_fixtures_venue_id", table_name="fixtures", schema="sports")
    op.drop_index("ix_fixtures_away_team_id", table_name="fixtures", schema="sports")
    op.drop_index("ix_fixtures_home_team_id", table_name="fixtures", schema="sports")
