"""Sports entity versioning/provider-tracking + Country/Lineup entities
(docs/roadmap.md Milestone 5 — "every entity must support versioning ... source tracking ...
provider tracking"; Entity Expansion Matrix additions).

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-25
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

SCHEMA = "sports"

# Tables that already had provider_ref from 0001 — only need `version` added.
_VERSION_ONLY = ("competitions", "teams", "players")
# Tables that need both `version` and `provider_ref` added (they had neither before).
_VERSION_AND_PROVIDER_REF = ("sports", "venues", "seasons", "fixtures", "team_statistics", "standings")


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    for table in _VERSION_ONLY:
        op.add_column(table, sa.Column("version", sa.Integer(), nullable=False, server_default="1"), schema=SCHEMA)

    for table in _VERSION_AND_PROVIDER_REF:
        op.add_column(table, sa.Column("version", sa.Integer(), nullable=False, server_default="1"), schema=SCHEMA)
        op.add_column(table, sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"), schema=SCHEMA)

    op.create_table(
        "countries",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("code", sa.String(8), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"),
        *_timestamp_columns(),
        schema=SCHEMA,
    )

    op.create_table(
        "lineups",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("match_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.matches.id"), nullable=False, index=True),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.teams.id"), nullable=False, index=True),
        sa.Column("formation", sa.String(32), nullable=True),
        sa.Column("slots", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"),
        *_timestamp_columns(),
        sa.UniqueConstraint("match_id", "team_id", name="uq_lineup_match_team"),
        schema=SCHEMA,
    )

    op.create_unique_constraint(
        "uq_team_statistics_match_team", "team_statistics", ["match_id", "team_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_constraint("uq_team_statistics_match_team", "team_statistics", schema=SCHEMA, type_="unique")
    op.drop_table("lineups", schema=SCHEMA)
    op.drop_table("countries", schema=SCHEMA)

    for table in _VERSION_AND_PROVIDER_REF:
        op.drop_column(table, "provider_ref", schema=SCHEMA)
        op.drop_column(table, "version", schema=SCHEMA)

    for table in _VERSION_ONLY:
        op.drop_column(table, "version", schema=SCHEMA)
