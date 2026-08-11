"""Squad intelligence fields — injuries, transfers, coaching staff

Additive-only, wiring real ingestion onto the `injuries`/`transfers`/`coaching_staff` tables
that already existed schema-only since the Milestone 5 Entity Expansion Matrix (no rows were
ever written to them — this migration adds what real sync needs, it does not create new
tables):

- `injuries`/`transfers`/`coaching_staff` gain `version`/`provider_ref` (VersionedMixin), the
  same optimistic-version + provider-attribution pair every actively-ingested entity carries —
  required for idempotent re-sync (match an existing row by provider ref instead of duplicating
  it on every sync run).
- `injuries.reason` — the provider's own detail text (e.g. "Hamstring"), separate from
  `status` (the provider's own type text, e.g. "Missing Fixture").
- `transfers.transfer_type` — the provider's own raw fee/type text (e.g. "Loan", "Free",
  "€25.5M"); no negotiation-stage columns are added because no connected provider reports them.
- `coaching_staff.valid_from`/`valid_to` — makes manager history time-aware; a departure closes
  the row (`valid_to` set) rather than being overwritten, so history is never lost.

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

SCHEMA = "sports"


def upgrade() -> None:
    op.add_column("injuries", sa.Column("version", sa.Integer(), nullable=False, server_default="1"), schema=SCHEMA)
    op.add_column("injuries", sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"), schema=SCHEMA)
    op.add_column("injuries", sa.Column("reason", sa.String(255), nullable=True), schema=SCHEMA)

    op.add_column("transfers", sa.Column("version", sa.Integer(), nullable=False, server_default="1"), schema=SCHEMA)
    op.add_column("transfers", sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"), schema=SCHEMA)
    op.add_column("transfers", sa.Column("transfer_type", sa.String(64), nullable=True), schema=SCHEMA)
    op.create_index("ix_transfers_from_team_id", "transfers", ["from_team_id"], schema=SCHEMA)
    op.create_index("ix_transfers_to_team_id", "transfers", ["to_team_id"], schema=SCHEMA)

    op.add_column("coaching_staff", sa.Column("version", sa.Integer(), nullable=False, server_default="1"), schema=SCHEMA)
    op.add_column("coaching_staff", sa.Column("provider_ref", sa.JSON(), nullable=False, server_default="{}"), schema=SCHEMA)
    op.add_column("coaching_staff", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("coaching_staff", sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.create_index("ix_coaching_staff_valid_to", "coaching_staff", ["valid_to"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_coaching_staff_valid_to", table_name="coaching_staff", schema=SCHEMA)
    op.drop_column("coaching_staff", "valid_to", schema=SCHEMA)
    op.drop_column("coaching_staff", "valid_from", schema=SCHEMA)
    op.drop_column("coaching_staff", "provider_ref", schema=SCHEMA)
    op.drop_column("coaching_staff", "version", schema=SCHEMA)

    op.drop_index("ix_transfers_to_team_id", table_name="transfers", schema=SCHEMA)
    op.drop_index("ix_transfers_from_team_id", table_name="transfers", schema=SCHEMA)
    op.drop_column("transfers", "transfer_type", schema=SCHEMA)
    op.drop_column("transfers", "provider_ref", schema=SCHEMA)
    op.drop_column("transfers", "version", schema=SCHEMA)

    op.drop_column("injuries", "reason", schema=SCHEMA)
    op.drop_column("injuries", "provider_ref", schema=SCHEMA)
    op.drop_column("injuries", "version", schema=SCHEMA)
