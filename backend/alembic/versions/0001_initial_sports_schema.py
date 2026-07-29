"""Initial sports schema (docs/database_schema.md §2)

Revision ID: 0001
Revises:
Create Date: 2026-07-25
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "sports"


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "sports",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("code", sa.String(32), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "venues",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("country", sa.String(120), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("surface", sa.String(64), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "competitions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("sport_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.sports.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("country", sa.String(120), nullable=True),
        sa.Column("tier", sa.Integer(), nullable=True),
        sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "seasons",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "competition_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.competitions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="upcoming"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("sport_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.sports.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("short_name", sa.String(32), nullable=False),
        sa.Column("country", sa.String(120), nullable=True),
        sa.Column("venue_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.venues.id"), nullable=True),
        sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "players",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("sport_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.sports.id"), nullable=False, index=True),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=True, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("date_of_birth", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.String(64), nullable=True),
        sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "coaching_staff",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=False, index=True),
        sa.Column("person_name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "officials",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("sport_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.sports.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "fixtures",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("season_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.seasons.id"), nullable=False, index=True),
        sa.Column("home_team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=False),
        sa.Column("away_team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=False),
        sa.Column("venue_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.venues.id"), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="scheduled", index=True),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "fixture_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.fixtures.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_state", sa.JSON(), nullable=False, server_default="{}"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "match_events",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("match_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.matches.id"), nullable=False, index=True),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=True),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.players.id"), nullable=True),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "team_statistics",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("match_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.matches.id"), nullable=False, index=True),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=False, index=True),
        sa.Column("stat_set", sa.JSON(), nullable=False, server_default="{}"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "player_statistics",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("match_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.matches.id"), nullable=False, index=True),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.players.id"), nullable=False, index=True),
        sa.Column("stat_set", sa.JSON(), nullable=False, server_default="{}"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "standings",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("season_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.seasons.id"), nullable=False, index=True),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=False, index=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("points", sa.Float(), nullable=False),
        sa.Column("record", sa.JSON(), nullable=False, server_default="{}"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "injuries",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.players.id"), nullable=False, index=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("expected_return", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_ref", sa.JSON(), nullable=True),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "suspensions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.players.id"), nullable=False, index=True),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "transfers",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.players.id"), nullable=False, index=True),
        sa.Column("from_team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=True),
        sa.Column("to_team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=True),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "rankings",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("sport_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.sports.id"), nullable=False, index=True),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("system", sa.String(64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        *_timestamp_columns(),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "rankings",
        "transfers",
        "suspensions",
        "injuries",
        "standings",
        "player_statistics",
        "team_statistics",
        "match_events",
        "matches",
        "fixtures",
        "officials",
        "coaching_staff",
        "players",
        "teams",
        "seasons",
        "competitions",
        "venues",
        "sports",
    ):
        op.drop_table(table, schema=SCHEMA)

    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
