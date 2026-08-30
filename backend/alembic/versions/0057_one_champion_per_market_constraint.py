"""Enforce "exactly one CHAMPION per market" at the DB layer — forensic audit finding #6
(2026-08-30).

`ModelRegistryService.promote_to_champion` has always retired the prior Champion before
promoting a new one, but that ordering was the only thing preventing two `models` rows with
`status='champion'` for the same `market_id` — a service-layer promise, not a constraint. Nothing
stopped a race between two concurrent promotions, or a caller bypassing the service entirely (a
raw script, a bad migration), from leaving two live Champions standing; the only place that would
ever have surfaced was `ModelRepositoryPort.get_champion`'s `scalar_one_or_none()` raising
`MultipleResultsFound` on the next read.

This partial unique index makes the invariant real: any INSERT/UPDATE that would leave a second
`status='champion'` row for a market_id now fails at the database, immediately, at write time.

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-30
"""

from __future__ import annotations

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

PREDICTIONS = "predictions"


def upgrade() -> None:
    op.create_index(
        "uq_models_one_champion_per_market",
        "models",
        ["market_id"],
        unique=True,
        schema=PREDICTIONS,
        postgresql_where="status = 'champion'",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_models_one_champion_per_market",
        table_name="models",
        schema=PREDICTIONS,
    )
