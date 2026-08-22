"""Add sports.fixtures.last_verified_at — real provenance, found missing during a Premier League
data-enrichment audit.

`FixtureModel` had no timestamp recording when a fixture was last confirmed against a live
provider sync (only the generic `provider_ref` JSON blob from `VersionedMixin`, which is
optimistic-lock/audit bookkeeping, not a "when was this actually re-verified" signal).
Cross-provider identity itself is intentionally NOT duplicated here — `ProviderRefIndexModel`
(modules.ingestion) already does that job as the real O(1) per-provider lookup; adding a second,
redundant `source_ids` column on Fixture would fork that concept rather than reuse it.

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

SPORTS = "sports"


def upgrade() -> None:
    op.add_column(
        "fixtures",
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        schema=SPORTS,
    )


def downgrade() -> None:
    op.drop_column("fixtures", "last_verified_at", schema=SPORTS)
