"""Milestone 4 item 12 — data quality constraints.

Adds `CHECK` constraints preventing a narrow, real class of impossible states that nothing today
enforces at the database level: a negative fixture score. `Fixture.home_score`/`away_score` are
plain nullable integers (modules/sports/infrastructure/persistence/models.py) populated from
provider responses (`ProviderFixtureRecord.home_score`/`away_score`) with no validation between
the provider adapter and the database — a provider parsing bug or malformed payload could silently
store a negative score, which would then corrupt every goals-based market (`correct_score`,
`total_goals_over_under*`, `*_clean_sheet`, `*_win_to_nil`) without raising anywhere. Verified
against dev.db before writing this migration: zero existing rows violate it, so this is purely
preventative, not a corrective backfill.

Deliberately narrow, not a blanket "add every plausible constraint" pass — see the Milestone 4
verification report for the fuller list of *application-level* guards already covering related
cases without a DB constraint (`_canonical_entity_id`'s tolerant UUID parsing per Milestone 4
item 1, `uq_provider_ref_index`'s existing uniqueness constraint preventing duplicate provider
references, `_resolve_fixture_status`'s transition-legality guard preventing impossible status
regressions). Adding a CHECK constraint for each of those would duplicate logic that already lives
correctly at the layer that actually understands it (domain/application), not add real safety.

SQLite cannot add a CHECK constraint to an existing table without a full table rebuild (no
`ALTER TABLE ... ADD CONSTRAINT` support) — `upgrade()` is written for a real Postgres target
(this project's Alembic migrations are dialect-portable per docs/decisions.md's established
convention; dev.db itself is not Alembic-managed, per the same convention noted throughout the
Milestone 4 migrations). Running this migration against SQLite is a documented no-op guarded by a
dialect check, not a silent failure.

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

_CONSTRAINTS = (
    ("ck_fixtures_home_score_non_negative", "home_score >= 0"),
    ("ck_fixtures_away_score_non_negative", "away_score >= 0"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # See module docstring — SQLite can't add a CHECK constraint to an existing table without
        # a full rebuild; this is intentionally a documented no-op there, not a silent failure.
        return
    for name, condition in _CONSTRAINTS:
        op.create_check_constraint(name, "fixtures", condition, schema="sports")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    for name, _condition in _CONSTRAINTS:
        op.drop_constraint(name, "fixtures", schema="sports", type_="check")
