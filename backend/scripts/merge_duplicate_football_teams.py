"""One-off local dev helper: merges the 3 duplicate football teams the logo backfill (2026-08-04)
surfaced — Arsenal, Chelsea, Fulham each exist as TWO `Team` rows: an original api-football
version (with full historical stats/features already computed under it) and a second version
`CrossProviderTeamMappingService`'s admin review never matched to the football-data.org fixture
sync (see `docs`/session notes — 5 of 8 football-data.org teams were confirmed-mapped that day, 3
weren't). Every fixture reconciled through `sync_upcoming_fixtures` for these 3 clubs references
the UNMAPPED duplicate — which has no rolling-form/expected-goals history at all, since those are
computed from *that team id's own* match history — so Match Winner (and every other) prediction
generation fails with `MissingRequiredFeatureError` for any fixture involving one of them.

This script:
1. Repoints every real foreign-key reference to each duplicate team's id onto the canonical
   (api-football) team's id, across every table that can hold a team reference — `fixtures`
   (home/away), `players`, `coaching_staff`, `match_events`, `team_statistics`, `standings`,
   `lineups`, `transfers` (from/to), `memberships` (tenancy's own distinct "team" concept, sharing
   the `teams` table — included for completeness even though no dev-org row is expected to
   reference a football club), plus the two non-FK string-keyed tables that can reference an
   entity by id (`provider_ref_index.entity_id`, `feature_values_offline.entity_id`, both stored
   DASHED unlike the raw-hex `teams.id` column — see docs/decisions.md ADR-007's SQLite
   undashed-UUID note) and `watchlist_entries.entity_ref` (also string, dashed).
2. Deletes the now-unreferenced duplicate `Team` row.
3. Recomputes the fixture-level differential/expected-goals/odds features for every repointed
   fixture, now that they resolve to a team id with real match history — the exact same
   calculators `seed_football_markets.py` already uses for backfill, not new logic.

Every step logs what it touched; nothing here fabricates a value — repointing a foreign key to
the correct, already-real team and then recomputing a feature from that team's own real match
history is a correction, not new data.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/merge_duplicate_football_teams.py
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import (
    build_football_expected_goals_calculator,
    build_football_form_differential_calculators,
    build_football_odds_feature_writer,
    get_engine,
)
from modules.ingestion.application.data_validation_engine import DataValidationEngine
from modules.sports.domain.value_objects import ProviderRef, TeamId
from modules.sports.infrastructure.providers.mock_provider import MockSportsDataProvider
from scripts.production_safety_guard import require_confirmation_outside_development

# (canonical api-football name, duplicate football-data.org name) — the 3 pairs the logo backfill
# (2026-08-04) surfaced. Extend this list if a future sync creates another unmapped duplicate.
DUPLICATE_TEAM_PAIRS: tuple[tuple[str, str], ...] = (
    ("Arsenal", "Arsenal FC"),
    ("Chelsea", "Chelsea FC"),
    ("Fulham", "Fulham FC"),
)

# (table, column) for every real foreign-key-shaped team reference in the schema.
TEAM_FK_COLUMNS: tuple[tuple[str, str], ...] = (
    ("fixtures", "home_team_id"),
    ("fixtures", "away_team_id"),
    ("players", "team_id"),
    ("coaching_staff", "team_id"),
    ("match_events", "team_id"),
    ("team_statistics", "team_id"),
    ("standings", "team_id"),
    ("lineups", "team_id"),
    ("transfers", "from_team_id"),
    ("transfers", "to_team_id"),
    ("memberships", "team_id"),
)


async def main() -> None:
    require_confirmation_outside_development(__file__)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        now = datetime.now(timezone.utc)

        repointed_fixture_ids: set[str] = set()

        for canonical_name, duplicate_name in DUPLICATE_TEAM_PAIRS:
            canonical_id = (
                await session.execute(text("SELECT id FROM teams WHERE name = :n"), {"n": canonical_name})
            ).scalar()
            duplicate_id = (
                await session.execute(text("SELECT id FROM teams WHERE name = :n"), {"n": duplicate_name})
            ).scalar()
            if canonical_id is None or duplicate_id is None:
                print(f"skip {canonical_name}/{duplicate_name}: one side not found (already merged?)")
                continue

            print(f"\nmerging '{duplicate_name}' ({duplicate_id}) into '{canonical_name}' ({canonical_id})")

            if "fixtures" in (t for t, _ in TEAM_FK_COLUMNS):
                affected = (
                    await session.execute(
                        text(
                            "SELECT id FROM fixtures WHERE home_team_id = :d OR away_team_id = :d"
                        ),
                        {"d": duplicate_id},
                    )
                ).all()
                repointed_fixture_ids.update(str(uuid.UUID(row[0])) for row in affected)

            for table, column in TEAM_FK_COLUMNS:
                result = await session.execute(
                    text(f"UPDATE {table} SET {column} = :c WHERE {column} = :d"),
                    {"c": canonical_id, "d": duplicate_id},
                )
                if result.rowcount:
                    print(f"  {table}.{column}: repointed {result.rowcount} row(s)")

            # provider_ref_index / feature_values_offline / watchlist_entries store the entity id
            # as a DASHED string, unlike the raw-hex `teams.id` column (ADR-007).
            canonical_dashed = str(uuid.UUID(canonical_id))
            duplicate_dashed = str(uuid.UUID(duplicate_id))

            ref_result = await session.execute(
                text(
                    "UPDATE provider_ref_index SET entity_id = :c "
                    "WHERE entity_id = :d AND entity_kind = 'team'"
                ),
                {"c": canonical_dashed, "d": duplicate_dashed},
            )
            if ref_result.rowcount:
                print(f"  provider_ref_index (team refs): repointed {ref_result.rowcount} row(s)")

            feature_result = await session.execute(
                text(
                    "UPDATE feature_values_offline SET entity_id = :c "
                    "WHERE entity_id = :d AND entity_type = 'team'"
                ),
                {"c": canonical_dashed, "d": duplicate_dashed},
            )
            if feature_result.rowcount:
                print(f"  feature_values_offline (team-keyed): repointed {feature_result.rowcount} row(s)")

            watchlist_result = await session.execute(
                text(
                    "UPDATE watchlist_entries SET entity_ref = :c "
                    "WHERE entity_ref = :d AND entity_type = 'team'"
                ),
                {"c": canonical_dashed, "d": duplicate_dashed},
            )
            if watchlist_result.rowcount:
                print(f"  watchlist_entries: repointed {watchlist_result.rowcount} row(s)")

            # Safety check before deleting: confirm nothing still references the duplicate id
            # anywhere we know to look, so the delete never silently orphans a real row.
            remaining = 0
            for table, column in TEAM_FK_COLUMNS:
                count = (
                    await session.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {column} = :d"), {"d": duplicate_id})
                ).scalar()
                remaining += count
            if remaining:
                print(f"  ABORTING delete for {duplicate_name}: {remaining} reference(s) still remain")
                continue

            await session.execute(text("DELETE FROM teams WHERE id = :d"), {"d": duplicate_id})
            print(f"  deleted duplicate team row '{duplicate_name}'")

        await session.commit()

        if not repointed_fixture_ids:
            print("\nNo fixtures were repointed — nothing to recompute.")
            return

        print(f"\nRecomputing features for {len(repointed_fixture_ids)} repointed fixture(s)...")
        rows = (
            await session.execute(
                text(
                    "SELECT id, home_team_id, away_team_id, scheduled_at FROM fixtures WHERE id IN ({})".format(
                        ",".join(f"'{fid.replace('-', '')}'" for fid in repointed_fixture_ids)
                    )
                )
            )
        ).all()

        differential_calculators = build_football_form_differential_calculators(session)
        expected_goals_calculator = build_football_expected_goals_calculator(session)
        odds_provider = MockSportsDataProvider(provider_key="api_football", sport_code="football")
        odds_writer = build_football_odds_feature_writer(session)
        validator = DataValidationEngine()

        for i, (raw_fixture_id, home_team_id, away_team_id, scheduled_at) in enumerate(rows, start=1):
            fixture_id = str(uuid.UUID(raw_fixture_id))
            # Point-in-time leakage fix: each fixture's own kickoff is the cutoff for its rolling
            # form/expected-goals recomputation, never this script's shared start-of-run `now` —
            # same bug class `feature_as_of` closed in `reconcile_fixture` (commit db844e2), which
            # this script's direct calculator calls bypass entirely.
            cutoff = (
                datetime.fromisoformat(scheduled_at) if isinstance(scheduled_at, str) else scheduled_at
            ) or now
            for calculator in differential_calculators:
                await calculator.compute_and_write(
                    fixture_id, TeamId(uuid.UUID(home_team_id)), TeamId(uuid.UUID(away_team_id)), cutoff
                )
            await expected_goals_calculator.compute_and_write(
                fixture_id, TeamId(uuid.UUID(home_team_id)), TeamId(uuid.UUID(away_team_id)), cutoff
            )
            odds_ref = (
                await session.execute(
                    text(
                        "SELECT provider, external_id FROM provider_ref_index "
                        "WHERE REPLACE(entity_id,'-','') = :fid AND entity_kind = 'fixture'"
                    ),
                    {"fid": raw_fixture_id},
                )
            ).first()
            if odds_ref is not None:
                record = await odds_provider.fetch_odds(ProviderRef(provider=odds_ref[0], external_id=odds_ref[1]))
                if record is not None and validator.validate_odds(record).is_valid:
                    await odds_writer.compute_and_write(fixture_id, record, now)
            if i % 10 == 0 or i == len(rows):
                print(f"  ...{i}/{len(rows)} fixtures recomputed", flush=True)

        await session.commit()
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
