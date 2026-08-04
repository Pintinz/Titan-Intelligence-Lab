"""One-off local dev helper: runs `FootballMarketSeeder` against dev.db, then seeds a placeholder
CHAMPION model for every market that doesn't have one yet.

Audit finding (2026-08-02): `FootballMarketSeeder` (and its basketball/baseball/table_tennis
siblings) — real, fully tested market-registry seeders — were never wired to any real invocation
path. `apps/api/composition.py`'s `build_football_market_seeder` had zero callers anywhere in the
codebase; the only market ever actually seeded into dev.db was the single ad-hoc
`football.match_result` row `seed_local_market.py` hand-rolls. This script is that missing
invocation — running `FootballMarketSeeder.seed()` for real, the same way the (passing) unit
tests already exercise it, just against the persistent local SQLite DB instead of a throwaway
test engine.

A market with no CHAMPION model can't generate a prediction at all —
`PredictionContextBuilder.build()` raises `NoChampionModelError` for it. `FootballMarketSeeder`
only registers markets, never models, so this script also registers a placeholder CHAMPION
(no `artifact_ref`, algorithm ``"heuristic_logistic_v1"`` — same shape `seed_local_market.py`
already uses for `football.match_result`) for every seeded market that doesn't have a champion
yet. `PredictionEngine._resolve_predictor` already falls back to the real generic formula
predictor (matched by the market's `market_kind`) whenever a champion has no real artifact, so
this placeholder is enough to make every seeded market genuinely generate real predictions today
— never a fabricated model, just the same honest v1 posture every other market already had.

A second audit fix, same run (2026-08-02): `required_features` used to point at a TEAM-keyed
feature `PredictionContextBuilder` could never resolve for a fixture-level request (see
market_seeding.py's module docstring) — now fixed to point at `FixtureFormDifferentialCalculator`'s
FIXTURE-keyed differential instead. This script also: (a) deletes the now-stale
feature_market_mappings rows still pointing at the old team-keyed feature key (re-seeding only
ever *adds* mappings, never removes one that's no longer in `required_features`), and (b)
backfills the differential feature for every football fixture already in dev.db, so existing
fixtures can generate real predictions immediately rather than only fixtures reconciled after
this fix ships (going forward, `EntityReconciliationService` computes it automatically).

A third audit fix, same run (2026-08-02): football.both_teams_to_score/correct_score/match_winner
additionally require odds-derived features (`football.market.overround`,
`football.market.implied_probability_home`/`_away`) that nothing ever populated — no odds
ingestion existed at all (see `modules.sports.ports.provider_gateway.ProviderOddsRecord`,
`SyncOrchestrator.sync_odds_for_fixture`). This script also backfills those three features for
every football fixture using the mock provider's deterministic odds (no real odds API key is
configured locally), so those three markets can generate real predictions too, not just the
other fifteen.

A fourth fix, discovered live-verifying the third: both backfill loops fed the raw `fixtures.id`
SQL column straight to `compute_and_write` — SQLite stores that column as undashed hex, but every
real read path (`PredictionContextBuilder`, the frontend's own fixture_id) keys the feature store
by the standard dashed `str(uuid.UUID(...))` form. Every prior backfilled row (this script's own
first two runs, before this fix) was written under an unreadable key — invisible to predictions,
never raising an error, just silently never resolving. Both loops now normalize to the dashed
form before writing.

A fifth fix (2026-08-02): `football.correct_score` used `WeightedLinearPredictor`, whose value is
a raw regression number — meaningless for a scoreline market. Now served by `PoissonScorePredictor`
(independent-Poisson scoreline model) over two new real features,
`football.fixture.expected_home_goals`/`expected_away_goals` (`FixtureExpectedGoalsCalculator`,
each side's own average goals scored across its last 10 completed matches, from real
`Fixture.home_score`/`away_score` history). This script backfills those two features for every
existing football fixture the same way it backfills the odds/differential features above.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/seed_football_markets.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import (
    build_football_expected_goals_calculator,
    build_football_form_differential_calculators,
    build_football_market_seeder,
    build_football_odds_feature_writer,
    build_model_registry_service,
    get_engine,
)
from modules.ingestion.application.data_validation_engine import DataValidationEngine
from modules.predictions.domain.value_objects import MarketStatus
from modules.predictions.football.market_seeding import MARKETS
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository
from modules.sports.domain.value_objects import ProviderRef, TeamId
from modules.sports.infrastructure.providers.mock_provider import MockSportsDataProvider

PLACEHOLDER_ALGORITHM = "heuristic_logistic_v1"
STALE_TEAM_KEYED_FEATURE = "football.team.form_shots_on_target_last5"

# 2026-08-03 audit fix: these eleven markets used to require the generic fixture-form stat diffs
# (same set as most other football markets) — now they require real expected-goals features
# instead (poisson_goals_threshold_predictor.py). Re-seeding only ever *adds* new mappings, never
# removes one that's no longer in a market's `required_features`, so the six old mappings are
# deleted here first — otherwise they'd linger as dead (though harmless) weight in the resolved
# feature snapshot, the same class of cleanup `STALE_TEAM_KEYED_FEATURE` above already does.
POISSON_THRESHOLD_MARKET_KEYS = (
    "football.total_goals_over_under",
    "football.total_goals_over_under_0_5",
    "football.total_goals_over_under_1_5",
    "football.total_goals_over_under_3_5",
    "football.total_goals_over_under_4_5",
    "football.home_team_total_goals",
    "football.away_team_total_goals",
    "football.home_clean_sheet",
    "football.away_clean_sheet",
    "football.home_win_to_nil",
    "football.away_win_to_nil",
)
STALE_STAT_DIFF_FEATURES = (
    "football.fixture.form_shots_on_target_diff_last5",
    "football.fixture.form_possession_pct_diff_last5",
    "football.fixture.form_shots_total_diff_last5",
    "football.fixture.form_corners_diff_last5",
    "football.fixture.form_fouls_diff_last5",
    "football.fixture.form_cards_yellow_diff_last5",
)


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        now = datetime.now(timezone.utc)

        deleted = await session.execute(
            text("DELETE FROM feature_market_mappings WHERE feature_key = :key"),
            {"key": STALE_TEAM_KEYED_FEATURE},
        )

        market_placeholders = ",".join(f":market_{i}" for i in range(len(POISSON_THRESHOLD_MARKET_KEYS)))
        feature_placeholders = ",".join(f":feature_{i}" for i in range(len(STALE_STAT_DIFF_FEATURES)))
        deleted_threshold_mappings = await session.execute(
            text(
                f"DELETE FROM feature_market_mappings WHERE feature_key IN ({feature_placeholders}) "
                f"AND market_id IN (SELECT id FROM prediction_markets WHERE market_key IN ({market_placeholders}))"
            ),
            {
                **{f"market_{i}": key for i, key in enumerate(POISSON_THRESHOLD_MARKET_KEYS)},
                **{f"feature_{i}": key for i, key in enumerate(STALE_STAT_DIFF_FEATURES)},
            },
        )

        seeder = build_football_market_seeder(session)
        await seeder.seed(now)

        markets_repo = SqlAlchemyMarketRepository(session=session)
        model_registry = build_model_registry_service(session)

        seeded_champions = 0
        for spec in MARKETS:
            market = await markets_repo.get_by_key(spec["market_key"])
            if market is None or market.status is not MarketStatus.PRODUCTION:
                continue
            if await model_registry.models.get_champion(market.id) is not None:
                continue

            model = await model_registry.register(
                market_id=market.id,
                model_key=f"{spec['market_key']}.heuristic",
                version=1,
                algorithm=PLACEHOLDER_ALGORITHM,
                now=now,
            )
            challenger = await model_registry.promote_to_challenger(model.id)
            await model_registry.promote_to_champion(challenger.id, approved_by="seed-script", now=now)
            seeded_champions += 1

        differential_calculators = build_football_form_differential_calculators(session)
        rows = (
            await session.execute(
                text(
                    "SELECT f.id, f.home_team_id, f.away_team_id FROM fixtures f "
                    "JOIN seasons se ON f.season_id = se.id "
                    "JOIN competitions c ON se.competition_id = c.id "
                    "JOIN sports s ON c.sport_id = s.id "
                    "WHERE s.code = 'football'"
                )
            )
        ).all()
        backfilled = 0
        for i, (raw_fixture_id, home_team_id, away_team_id) in enumerate(rows, start=1):
            # SQLite stores the UUID column as raw undashed hex (`f.id`), but every real read
            # path (PredictionContextBuilder, the frontend's own fixture_id in its API calls)
            # keys the feature store by the standard dashed `str(uuid.UUID(...))` form — writing
            # under the raw column value silently wrote invisible, unreadable rows.
            fixture_id = str(UUID(raw_fixture_id))
            # 2026-08-03: one calculator per stat (shots_on_target plus the newly-wired
            # possession/shots_total/corners/fouls/cards) — every one gets its own feature row.
            any_written = False
            for calculator in differential_calculators:
                written = await calculator.compute_and_write(
                    fixture_id, TeamId(UUID(home_team_id)), TeamId(UUID(away_team_id)), now
                )
                any_written = any_written or written is not None
            if any_written:
                backfilled += 1
            if i % 25 == 0 or i == len(rows):
                print(f"...{i}/{len(rows)} fixtures processed ({backfilled} written)", flush=True)

        expected_goals_calculator = build_football_expected_goals_calculator(session)
        expected_goals_backfilled = 0
        for i, (raw_fixture_id, home_team_id, away_team_id) in enumerate(rows, start=1):
            fixture_id = str(UUID(raw_fixture_id))
            home_value, away_value = await expected_goals_calculator.compute_and_write(
                fixture_id, TeamId(UUID(home_team_id)), TeamId(UUID(away_team_id)), now
            )
            if home_value is not None and away_value is not None:
                expected_goals_backfilled += 1
            if i % 25 == 0 or i == len(rows):
                print(f"...expected-goals {i}/{len(rows)} fixtures processed ({expected_goals_backfilled} written)", flush=True)

        odds_provider = MockSportsDataProvider(provider_key="api_football", sport_code="football")
        odds_writer = build_football_odds_feature_writer(session)
        validator = DataValidationEngine()
        odds_rows = (
            await session.execute(
                text(
                    "SELECT f.id, pri.provider, pri.external_id FROM fixtures f "
                    "JOIN seasons se ON f.season_id = se.id "
                    "JOIN competitions c ON se.competition_id = c.id "
                    "JOIN sports s ON c.sport_id = s.id "
                    "JOIN provider_ref_index pri ON REPLACE(pri.entity_id, '-', '') = f.id AND pri.entity_kind = 'fixture' "
                    "WHERE s.code = 'football'"
                )
            )
        ).all()
        odds_backfilled = 0
        for i, (raw_fixture_id, provider, external_id) in enumerate(odds_rows, start=1):
            fixture_id = str(UUID(raw_fixture_id))
            record = await odds_provider.fetch_odds(ProviderRef(provider=provider, external_id=external_id))
            if record is not None and validator.validate_odds(record).is_valid:
                written = await odds_writer.compute_and_write(fixture_id, record, now)
                if written:
                    odds_backfilled += 1
            if i % 25 == 0 or i == len(odds_rows):
                print(f"...odds {i}/{len(odds_rows)} fixtures processed ({odds_backfilled} written)", flush=True)

        await session.commit()
        print(
            f"Seeded football's real production market catalog ({len(MARKETS)} markets), "
            f"{seeded_champions} placeholder champions, removed {deleted.rowcount} stale feature "
            f"mappings + {deleted_threshold_mappings.rowcount} stale stat-diff mappings from the "
            f"eleven Poisson-threshold markets, backfilled the form differential for "
            f"{backfilled}/{len(rows)} fixtures, backfilled odds-derived features for "
            f"{odds_backfilled}/{len(odds_rows)} fixtures, and backfilled expected-goals features "
            f"for {expected_goals_backfilled}/{len(rows)} fixtures."
        )


if __name__ == "__main__":
    asyncio.run(main())
