"""POST-M24 Phase 4 — HistoricalImportService tests. Real DB round-trips (in-memory SQLite),
mirroring test_entity_reconciliation_service.py's own fixture setup exactly, since this service's
entire job is delegating to that real reconciler.

Categories covered (Phase 4 master prompt's own list): team resolution hierarchy (match / create /
ambiguous-quarantine), competition/season scoping, idempotent re-import, DRY_RUN vs VALIDATE vs
IMPORT mode gating (zero writes for the first two), provenance (SyncTrigger.BACKFILL, never
VERIFIED_PRE_MATCH), score preservation (a historical row must never overwrite an existing
authoritative score), multi-source convergence (teams+date matching onto an existing fixture), and
CSV-source row-level validation.
"""

from __future__ import annotations

import csv
import os
import tempfile
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.alerts.infrastructure.persistence.models import Base as AlertsBase
from modules.ingestion.application.cross_provider_team_mapping_service import _normalize_name
from modules.ingestion.application.entity_reconciliation_service import EntityReconciliationService
from modules.ingestion.application.historical_import_service import HistoricalImportService
from modules.ingestion.domain.historical_import import ImportMode, QuarantineReason
from modules.ingestion.infrastructure.historical.csv_historical_source import (
    CsvColumnMapping,
    CsvHistoricalSource,
    OddsColumnMapping,
    StatisticsColumnMapping,
)
from modules.ingestion.infrastructure.persistence.models import Base as IngestionBase
from modules.ingestion.infrastructure.persistence.repositories import (
    SqlAlchemyProviderRefIndexRepository,
    SqlAlchemySyncRunRepository,
    SqlAlchemyTimelineEventRepository,
)
from modules.ingestion.ports.historical_source import HistoricalReadResult
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.infrastructure.persistence.models import Base as KGBase
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)
from modules.sports.domain.value_objects import SportCode
from modules.sports.infrastructure.persistence.models import (
    Base as SportsBase,
    FixtureModel,
    MarketLineModel,
    TeamModel,
)
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCoachingStaffRepository,
    SqlAlchemyCompetitionRepository,
    SqlAlchemyCountryRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyInjuryRepository,
    SqlAlchemyMarketLineRepository,
    SqlAlchemyMatchRepository,
    SqlAlchemyLineupRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyTeamStatisticsRepository,
    SqlAlchemyTransferRepository,
    SqlAlchemyVenueRepository,
)
from modules.watchlist.infrastructure.persistence.models import Base as WatchlistBase

T0 = datetime(2026, 8, 15, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={
            "schema_translate_map": {
                "sports": None, "ingestion": None, "knowledge_graph": None, "watchlist": None, "alerts": None,
            }
        },
    )
    async with engine.begin() as conn:
        await conn.run_sync(SportsBase.metadata.create_all)
        await conn.run_sync(IngestionBase.metadata.create_all)
        await conn.run_sync(KGBase.metadata.create_all)
        await conn.run_sync(WatchlistBase.metadata.create_all)
        await conn.run_sync(AlertsBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def reconciler(session):
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    return EntityReconciliationService(
        sports=SqlAlchemySportRepository(session=session),
        countries=SqlAlchemyCountryRepository(session=session),
        competitions=SqlAlchemyCompetitionRepository(session=session),
        seasons=SqlAlchemySeasonRepository(session=session),
        venues=SqlAlchemyVenueRepository(session=session),
        teams=SqlAlchemyTeamRepository(session=session),
        players=SqlAlchemyPlayerRepository(session=session),
        fixtures=SqlAlchemyFixtureRepository(session=session),
        matches=SqlAlchemyMatchRepository(session=session),
        team_statistics=SqlAlchemyTeamStatisticsRepository(session=session),
        lineups=SqlAlchemyLineupRepository(session=session),
        standings=SqlAlchemyStandingRepository(session=session),
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        coaching_staff=SqlAlchemyCoachingStaffRepository(session=session),
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
    )


@pytest.fixture
def service(reconciler, session):
    return HistoricalImportService(reconciler=reconciler, sync_runs=SqlAlchemySyncRunRepository(session=session))


@pytest.fixture
def service_with_market_lines(reconciler, session):
    """POST-M24 Phase 12 — real `market_lines` wiring, distinct from `service` above (which stays
    `market_lines=None`, exactly Phase 4's original shape) so every pre-existing test keeps
    exercising the "no odds repository configured" path unchanged."""
    return HistoricalImportService(
        reconciler=reconciler, sync_runs=SqlAlchemySyncRunRepository(session=session),
        market_lines=SqlAlchemyMarketLineRepository(session=session),
    )


@pytest_asyncio.fixture
async def football_sport(reconciler):
    sport, _ = await reconciler.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    return sport


def _write_csv(rows: list[dict], headers: list[str]) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _source(source_key: str = "kaggle_test_football") -> CsvHistoricalSource:
    return CsvHistoricalSource(
        source_key=source_key,
        sport=SportCode.FOOTBALL,
        columns=CsvColumnMapping(date="date", home_team="home_team", away_team="away_team", home_score="home_score", away_score="away_score"),
        default_competition_ref="int_friendlies",
        default_competition_name="International Friendlies",
    )


def _source_with_odds(source_key: str = "web_test_football") -> CsvHistoricalSource:
    """POST-M24 Phase 12 — same shape as `_source()`, plus a real `OddsColumnMapping` matching
    football-data.co.uk's own real column names (B365H/D/A, B365>2.5/<2.5), confirmed live against
    the actual downloaded CSV this phase."""
    return CsvHistoricalSource(
        source_key=source_key,
        sport=SportCode.FOOTBALL,
        columns=CsvColumnMapping(
            date="date", home_team="home_team", away_team="away_team", home_score="home_score", away_score="away_score",
            odds=(
                OddsColumnMapping(
                    bookmaker="Bet365",
                    moneyline_home="B365H", moneyline_draw="B365D", moneyline_away="B365A",
                    total_line=2.5, total_over="B365>2.5", total_under="B365<2.5",
                ),
            ),
        ),
        default_competition_ref="int_friendlies",
        default_competition_name="International Friendlies",
    )


# -- CsvHistoricalSource: row-level validation -------------------------------------------------


def test_csv_source_parses_valid_rows():
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    result = _source().read_records(path)
    assert len(result.records) == 1
    assert result.records[0].home_team_name == "Brazil"
    assert result.records[0].home_score == 1
    assert result.rejected == ()


def test_csv_source_rejects_row_missing_team_name():
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    result = _source().read_records(path)
    assert result.records == ()
    assert len(result.rejected) == 1
    assert result.rejected[0].reason.value == "unparseable_row"


def test_csv_source_rejects_row_with_unparseable_date():
    path = _write_csv(
        [{"date": "not-a-date", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    result = _source().read_records(path)
    assert result.records == ()
    assert len(result.rejected) == 1


def test_csv_source_handles_missing_scores_as_scheduled():
    path = _write_csv(
        [{"date": "2027-01-01", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "", "away_score": ""}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    result = _source().read_records(path)
    assert result.records[0].home_score is None
    assert result.records[0].away_score is None


def _source_with_statistics(source_key: str = "web_test_football_stats") -> CsvHistoricalSource:
    """Matches football-data.co.uk's real column names (HS/AS/HST/AST/HC/AC/HF/AF/HY/AY),
    confirmed live against the actual downloaded E1/E2/E3 CSVs."""
    return CsvHistoricalSource(
        source_key=source_key,
        sport=SportCode.FOOTBALL,
        columns=CsvColumnMapping(
            date="date", home_team="home_team", away_team="away_team", home_score="home_score", away_score="away_score",
            statistics=StatisticsColumnMapping(
                home_shots_on_target="HST", away_shots_on_target="AST",
                home_shots_total="HS", away_shots_total="AS",
                home_corners="HC", away_corners="AC",
                home_fouls="HF", away_fouls="AF",
                home_cards_yellow="HY", away_cards_yellow="AY",
            ),
        ),
        default_competition_ref="int_friendlies",
        default_competition_name="International Friendlies",
    )


def test_csv_source_parses_real_match_statistics_when_mapped():
    path = _write_csv(
        [{
            "date": "2027-01-01", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2",
            "HST": "5", "AST": "3", "HS": "12", "AS": "9", "HC": "6", "AC": "4", "HF": "10", "AF": "14", "HY": "2", "AY": "1",
        }],
        ["date", "home_team", "away_team", "home_score", "away_score", "HST", "AST", "HS", "AS", "HC", "AC", "HF", "AF", "HY", "AY"],
    )
    record = _source_with_statistics().read_records(path).records[0]
    assert record.home_statistics.stat_set == {
        "shots_on_target": 5, "shots_total": 12, "corners": 6, "fouls": 10, "cards_yellow": 2,
    }
    assert record.away_statistics.stat_set == {
        "shots_on_target": 3, "shots_total": 9, "corners": 4, "fouls": 14, "cards_yellow": 1,
    }


def test_csv_source_omits_statistics_columns_the_source_leaves_blank_without_fabricating():
    path = _write_csv(
        [{
            "date": "2027-01-01", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2",
            "HST": "5", "AST": "", "HS": "", "AS": "", "HC": "", "AC": "", "HF": "", "AF": "", "HY": "", "AY": "",
        }],
        ["date", "home_team", "away_team", "home_score", "away_score", "HST", "AST", "HS", "AS", "HC", "AC", "HF", "AF", "HY", "AY"],
    )
    record = _source_with_statistics().read_records(path).records[0]
    assert record.home_statistics.stat_set == {"shots_on_target": 5}
    assert record.away_statistics is None  # every away column was blank — never a fabricated stat_set


def test_source_without_statistics_columns_configured_produces_no_statistics():
    path = _write_csv(
        [{"date": "2027-01-01", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    record = _source().read_records(path).records[0]
    assert record.home_statistics is None
    assert record.away_statistics is None


# -- Team resolution hierarchy -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_teams_are_created_when_no_existing_match(service, football_sport):
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    report = await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)
    assert report.teams_created == 2
    assert report.teams_matched == 0
    assert report.fixtures_created == 1


@pytest.mark.asyncio
async def test_existing_team_is_matched_by_exact_normalized_name(service, reconciler, football_sport):
    from modules.sports.ports.provider_gateway import ProviderTeamRecord
    from modules.sports.domain.value_objects import ProviderRef

    await reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("api_football", "1"), name="Chelsea FC", short_name="CHE", country="England"),
        football_sport.id, T0,
    )
    path = _write_csv(
        [{"date": "2020-01-01", "home_team": "Chelsea", "away_team": "New Historical FC", "home_score": "2", "away_score": "0"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    report = await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)
    assert report.teams_matched == 1  # "Chelsea" normalizes onto existing "Chelsea FC"
    assert report.teams_created == 1  # "New Historical FC" is genuinely new


@pytest.mark.asyncio
async def test_ambiguous_team_name_is_quarantined_not_guessed(service, reconciler, football_sport, session):
    """Two existing teams normalize to the same name ('united') — the record referencing that
    name must be quarantined, never silently matched to either one."""
    from modules.sports.ports.provider_gateway import ProviderTeamRecord
    from modules.sports.domain.value_objects import ProviderRef

    await reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("api_football", "1"), name="United FC", short_name="U1", country=None),
        football_sport.id, T0,
    )
    await reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("football_data_org", "2"), name="United", short_name="U2", country=None),
        football_sport.id, T0,
    )
    path = _write_csv(
        [{"date": "2020-01-01", "home_team": "United", "away_team": "Real Historical Town", "home_score": "1", "away_score": "1"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    report = await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)
    assert report.quarantined_count == 1
    assert report.quarantined[0].reason is QuarantineReason.AMBIGUOUS_TEAM
    assert report.fixtures_created == 0

    fixture_count = (await session.execute(select(FixtureModel))).scalars().all()
    assert len(fixture_count) == 0  # quarantined record never reached fixture reconciliation


# -- Mode gating: DRY_RUN / VALIDATE never write --------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ImportMode.DRY_RUN, ImportMode.VALIDATE])
async def test_dry_run_and_validate_never_write_to_the_database(service, football_sport, session, mode):
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    report = await service.import_file(_source(), path, SportCode.FOOTBALL, mode, T0)
    assert report.fixtures_created == 1  # honest "would create" count, computed read-only
    assert report.teams_created == 2

    teams = (await session.execute(select(TeamModel))).scalars().all()
    fixtures = (await session.execute(select(FixtureModel))).scalars().all()
    assert teams == []
    assert fixtures == []


@pytest.mark.asyncio
async def test_import_mode_actually_persists(service, football_sport, session):
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)
    teams = (await session.execute(select(TeamModel))).scalars().all()
    fixtures = (await session.execute(select(FixtureModel))).scalars().all()
    assert len(teams) == 2
    assert len(fixtures) == 1
    assert fixtures[0].home_score == 1
    assert fixtures[0].away_score == 2


@pytest.mark.asyncio
async def test_import_writes_real_team_statistics_against_the_resolved_match(service, reconciler, football_sport, session):
    """The extension behind fixing 'teams without recent form' (Coventry/Hull/Sunderland-class
    gap): a source that reports real per-side match statistics must reach `TeamStatistics` via
    the *same* `get_or_create_match`/`reconcile_team_statistics` pair the live provider stats
    sync already uses — not a second write path."""
    path = _write_csv(
        [{
            "date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2",
            "HST": "5", "AST": "3", "HS": "12", "AS": "9", "HC": "6", "AC": "4", "HF": "10", "AF": "14", "HY": "2", "AY": "1",
        }],
        ["date", "home_team", "away_team", "home_score", "away_score", "HST", "AST", "HS", "AS", "HC", "AC", "HF", "AF", "HY", "AY"],
    )
    report = await service.import_file(_source_with_statistics(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)

    assert report.statistics_recorded == 2
    fixtures = (await session.execute(select(FixtureModel))).scalars().all()
    from modules.sports.domain.value_objects import FixtureId

    match = await reconciler.matches.get_by_fixture(FixtureId(fixtures[0].id))
    assert match is not None
    assert match.started_at is not None  # never NULL — the exact bug the reconciler's own docstring warns about

    stats = await reconciler.team_statistics.list_by_match(match.id)
    assert len(stats) == 2
    by_team_id = {str(s.team_id.value): s.stat_set for s in stats}
    assert {"shots_on_target": 5, "shots_total": 12, "corners": 6, "fouls": 10, "cards_yellow": 2} in by_team_id.values()
    assert {"shots_on_target": 3, "shots_total": 9, "corners": 4, "fouls": 14, "cards_yellow": 1} in by_team_id.values()


@pytest.mark.asyncio
async def test_import_skips_statistics_for_a_fixture_with_no_final_score(service, reconciler, football_sport, session):
    path = _write_csv(
        [{
            "date": "2027-01-01", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "", "away_score": "",
            "HST": "5", "AST": "3", "HS": "", "AS": "", "HC": "", "AC": "", "HF": "", "AF": "", "HY": "", "AY": "",
        }],
        ["date", "home_team", "away_team", "home_score", "away_score", "HST", "AST", "HS", "AS", "HC", "AC", "HF", "AF", "HY", "AY"],
    )
    report = await service.import_file(_source_with_statistics(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)
    assert report.statistics_recorded == 0


@pytest.mark.asyncio
async def test_dry_run_never_writes_statistics(service, football_sport, session):
    path = _write_csv(
        [{
            "date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2",
            "HST": "5", "AST": "3", "HS": "12", "AS": "9", "HC": "6", "AC": "4", "HF": "10", "AF": "14", "HY": "2", "AY": "1",
        }],
        ["date", "home_team", "away_team", "home_score", "away_score", "HST", "AST", "HS", "AS", "HC", "AC", "HF", "AF", "HY", "AY"],
    )
    report = await service.import_file(_source_with_statistics(), path, SportCode.FOOTBALL, ImportMode.DRY_RUN, T0)
    assert report.statistics_recorded == 0
    fixtures = (await session.execute(select(FixtureModel))).scalars().all()
    assert fixtures == []


# -- Idempotency ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reimporting_the_same_file_is_idempotent(service, football_sport, session):
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    first = await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)
    second = await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)

    assert first.fixtures_created == 1
    assert second.fixtures_created == 0
    assert second.fixtures_updated == 1  # same source_record_id -> resolves to the same fixture

    fixtures = (await session.execute(select(FixtureModel))).scalars().all()
    teams = (await session.execute(select(TeamModel))).scalars().all()
    assert len(fixtures) == 1  # no duplicate created on re-import
    assert len(teams) == 2  # no duplicate teams created either


# -- Score preservation / multi-source convergence -----------------------------------------------


@pytest.mark.asyncio
async def test_historical_import_never_overwrites_an_existing_authoritative_score(service, reconciler, football_sport, session):
    """A live-provider fixture already has a real, verified score. A historical row for the same
    two teams on the same date must converge onto that fixture (teams+date matching) but must
    never overwrite its score — `preserve_existing_score=True` is the exact mechanism reused."""
    from modules.sports.ports.provider_gateway import ProviderTeamRecord, ProviderFixtureRecord
    from modules.sports.domain.value_objects import ProviderRef

    home, _ = await reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("api_football", "10"), name="Brazil", short_name="BRA", country=None),
        football_sport.id, T0,
    )
    away, _ = await reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("api_football", "11"), name="Uruguay", short_name="URU", country=None),
        football_sport.id, T0,
    )
    competition, _ = await reconciler.reconcile_competition("39", "api_football", football_sport.id, T0, name="World Cup")
    season, _ = await reconciler.reconcile_season("39", "1950", "api_football", competition.id, T0)
    await reconciler.reconcile_fixture(
        ProviderFixtureRecord(
            external_ref=ProviderRef("api_football", "999"), home_team_ref=ProviderRef("api_football", "10"),
            away_team_ref=ProviderRef("api_football", "11"), scheduled_at=datetime(1950, 6, 24, tzinfo=timezone.utc),
            competition_ref="39", season_label="1950", status="FT", home_score=9, away_score=9,
        ),
        season.id, T0,
    )

    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    report = await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)

    assert report.fixtures_updated == 1
    assert report.fixtures_created == 0
    fixtures = (await session.execute(select(FixtureModel))).scalars().all()
    assert len(fixtures) == 1  # converged onto the existing fixture, no duplicate
    assert fixtures[0].home_score == 9  # the real 9-9 score was never overwritten by the historical 1-2 row
    assert fixtures[0].away_score == 9


# -- Provenance --------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_records_a_sync_run_tagged_backfill(service, football_sport, session):
    from modules.ingestion.infrastructure.persistence.repositories import SqlAlchemySyncRunRepository

    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)
    runs = await SqlAlchemySyncRunRepository(session=session).list_recent(sport_code="football")
    backfill_runs = [r for r in runs if r.scope_key.startswith("historical:")]
    assert len(backfill_runs) == 1
    assert backfill_runs[0].trigger.value == "backfill"


@pytest.mark.asyncio
async def test_dry_run_creates_no_sync_run(service, football_sport, session):
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.DRY_RUN, T0)
    runs = await SqlAlchemySyncRunRepository(session=session).list_recent(sport_code="football")
    assert runs == []


@pytest.mark.asyncio
async def test_historical_fixture_never_becomes_verified_pre_match(service, football_sport, session):
    """Historical import writes fixture identity + score only — it never touches
    availability_classification/VERIFIED_PRE_MATCH, which is scoped to structured-intelligence
    entities (Lineup/Injury/Transfer/Suspension) that this service never writes at all."""
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    await service.import_file(_source(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)
    fixtures = (await session.execute(select(FixtureModel))).scalars().all()
    assert not hasattr(fixtures[0], "availability_classification")


# -- Sport must already exist -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_raises_if_sport_was_never_reconciled(service):
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    with pytest.raises(ValueError):
        await service.import_file(_source(), path, SportCode.BASKETBALL, ImportMode.IMPORT, T0)


# -- POST-M24 Phase 12: real historical odds import ----------------------------------------------

_ODDS_HEADERS = ["date", "home_team", "away_team", "home_score", "away_score", "B365H", "B365D", "B365A", "B365>2.5", "B365<2.5"]
_ODDS_ROW = {
    "date": "2020-01-01", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2",
    "B365H": "2.10", "B365D": "3.40", "B365A": "3.20", "B365>2.5": "1.90", "B365<2.5": "1.95",
}


def test_csv_source_extracts_real_moneyline_and_total_odds():
    path = _write_csv([_ODDS_ROW], _ODDS_HEADERS)
    result = _source_with_odds().read_records(path)
    assert len(result.records) == 1
    quotes = {(q.market_type, q.selection): q.price for q in result.records[0].odds}
    assert quotes[("moneyline", "HOME")] == 2.10
    assert quotes[("moneyline", "DRAW")] == 3.40
    assert quotes[("moneyline", "AWAY")] == 3.20
    assert quotes[("total", "OVER")] == 1.90
    assert quotes[("total", "UNDER")] == 1.95
    total_quote = next(q for q in result.records[0].odds if q.market_type == "total" and q.selection == "OVER")
    assert total_quote.line == 2.5


def test_csv_source_skips_blank_odds_columns_without_fabricating():
    row = dict(_ODDS_ROW)
    row["B365D"] = ""  # a real source sometimes omits a column for a given match — never guessed
    path = _write_csv([row], _ODDS_HEADERS)
    result = _source_with_odds().read_records(path)
    selections = {q.selection for q in result.records[0].odds}
    assert "DRAW" not in selections
    assert "HOME" in selections and "AWAY" in selections


def test_csv_source_rejects_a_price_of_one_or_less_as_not_a_real_quote():
    """A real decimal sportsbook price is always > 1.0 — a stray '1' or '0' some sources use for
    'no line' must never be recorded as a real quote."""
    row = dict(_ODDS_ROW)
    row["B365H"] = "1.0"
    path = _write_csv([row], _ODDS_HEADERS)
    result = _source_with_odds().read_records(path)
    assert "HOME" not in {q.selection for q in result.records[0].odds if q.market_type == "moneyline"}


def test_source_without_odds_columns_configured_produces_no_quotes():
    path = _write_csv(
        [{"date": "1950-06-24", "home_team": "Brazil", "away_team": "Uruguay", "home_score": "1", "away_score": "2"}],
        ["date", "home_team", "away_team", "home_score", "away_score"],
    )
    result = _source().read_records(path)
    assert result.records[0].odds == ()


@pytest.mark.asyncio
async def test_import_writes_real_odds_against_the_resolved_fixture(service_with_market_lines, football_sport, session):
    path = _write_csv([_ODDS_ROW], _ODDS_HEADERS)
    report = await service_with_market_lines.import_file(
        _source_with_odds(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0
    )
    assert report.odds_quotes_recorded == 5  # 3 moneyline + 2 total — every column in _ODDS_ROW is real

    fixture = (await session.execute(select(FixtureModel))).scalars().one()
    lines = (await session.execute(select(MarketLineModel).where(MarketLineModel.fixture_id == fixture.id))).scalars().all()
    assert len(lines) == 5
    assert all(line.bookmaker == "Bet365" for line in lines)
    assert all(line.provider.startswith("historical:") for line in lines)
    home_line = next(line for line in lines if line.market_type == "moneyline" and line.selection == "HOME")
    assert home_line.price == 2.10
    assert home_line.observed_at is None  # source reports no separate quote timestamp — never guessed


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ImportMode.DRY_RUN, ImportMode.VALIDATE])
async def test_dry_run_and_validate_never_write_odds(service_with_market_lines, football_sport, session, mode):
    path = _write_csv([_ODDS_ROW], _ODDS_HEADERS)
    report = await service_with_market_lines.import_file(_source_with_odds(), path, SportCode.FOOTBALL, mode, T0)
    assert report.odds_quotes_recorded == 5  # honest "would record" count, same convention as fixtures_created

    lines = (await session.execute(select(MarketLineModel))).scalars().all()
    assert lines == []


@pytest.mark.asyncio
async def test_odds_are_silently_skipped_when_no_market_line_repository_is_configured(service, football_sport, session):
    """`service` (the pre-existing Phase 4 fixture) never wires `market_lines` — real odds present
    on the record must not raise or block the fixture import, only skip the odds write."""
    path = _write_csv([_ODDS_ROW], _ODDS_HEADERS)
    report = await service.import_file(_source_with_odds(), path, SportCode.FOOTBALL, ImportMode.IMPORT, T0)
    assert report.fixtures_created == 1
    assert report.odds_quotes_recorded == 0

    lines = (await session.execute(select(MarketLineModel))).scalars().all()
    assert lines == []
