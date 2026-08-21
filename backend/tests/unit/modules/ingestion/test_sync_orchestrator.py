from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import uuid
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.ingestion.application.data_quality_engine import IngestionQualityEngine
from modules.ingestion.application.data_validation_engine import DataValidationEngine
from modules.ingestion.application.entity_reconciliation_service import EntityReconciliationService
from modules.ingestion.application.sync_orchestrator import (
    NoFixtureSourcePreferenceError,
    SportNotReconciledError,
    SyncOrchestrator,
)
from modules.ingestion.domain.entities import CompetitionFixtureSourcePreference, ProviderRefIndexEntry
from modules.ingestion.domain.value_objects import EntityKind, SyncStatus, SyncTrigger, TimelineEventType
from modules.ingestion.infrastructure.persistence.models import Base as IngestionBase
from modules.ingestion.infrastructure.persistence.repositories import (
    SqlAlchemyDataQualityReportRepository,
    SqlAlchemyProviderRefIndexRepository,
    SqlAlchemySyncCheckpointRepository,
    SqlAlchemySyncRunRepository,
    SqlAlchemyTimelineEventRepository,
)
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.infrastructure.persistence.models import Base as KGBase
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)
from modules.sports.domain.entities import Team
from modules.sports.domain.value_objects import FixtureId, ProviderRef, SeasonId, SportCode, TeamId
from modules.sports.infrastructure.persistence.models import Base as SportsBase
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCoachingStaffRepository,
    SqlAlchemyCompetitionRepository,
    SqlAlchemyCountryRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyInjuryRepository,
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
from modules.sports.infrastructure.providers.api_sports_adapter import ProviderErrorKind, ProviderRequestError
from modules.sports.ports.provider_gateway import (
    ProviderCoachRecord,
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderInjuryRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
    ProviderTransferRecord,
)

T0 = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


@dataclass
class FakeRouter:
    teams_by_call: list = field(default_factory=list)
    teams_to_return: list = field(default_factory=list)
    countries_to_return: list = field(default_factory=list)
    fixtures_to_return: list = field(default_factory=list)
    standings_to_return: list = field(default_factory=list)
    odds_to_return: object = None
    team_statistics_to_return: list = field(default_factory=list)
    players_to_return: list = field(default_factory=list)
    upcoming_fixtures_calls: list = field(default_factory=list)
    upcoming_fixtures_to_return: list = field(default_factory=list)
    completed_fixtures_calls: list = field(default_factory=list)
    completed_fixtures_to_return: list = field(default_factory=list)
    standings_alt_calls: list = field(default_factory=list)
    standings_alt_to_return: list = field(default_factory=list)
    lineups_to_return: list = field(default_factory=list)
    injuries_to_return: list = field(default_factory=list)
    transfers_to_return: list = field(default_factory=list)
    coach_to_return: object = None
    raise_on_fetch: Exception | None = None

    async def fetch_teams(self, sport_code, competition_ref, now, *, low_priority=False, season_label=None):
        self.teams_by_call.append((sport_code, competition_ref))
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.teams_to_return

    async def fetch_countries(self, sport_code, now, *, low_priority=False):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.countries_to_return

    async def fetch_fixtures(self, sport_code, competition_ref, season_label, now, *, low_priority=False):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.fixtures_to_return

    async def fetch_standings(self, sport_code, competition_ref, season_label, now, *, low_priority=False):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.standings_to_return

    async def fetch_odds(self, sport_code, fixture_ref, now, *, low_priority=True):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.odds_to_return

    async def fetch_team_statistics(self, sport_code, fixture_ref, now, *, low_priority=True):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.team_statistics_to_return

    async def fetch_players(self, sport_code, team_ref, now, *, low_priority=True, season_label=None):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.players_to_return

    async def fetch_upcoming_fixtures(self, sport_code, provider_key, competition_ref, season_label, now, *, low_priority=False):
        self.upcoming_fixtures_calls.append((sport_code, provider_key, competition_ref, season_label))
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.upcoming_fixtures_to_return

    async def fetch_completed_fixtures(self, sport_code, provider_key, competition_ref, season_label, now, *, low_priority=False):
        self.completed_fixtures_calls.append((sport_code, provider_key, competition_ref, season_label))
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.completed_fixtures_to_return

    async def fetch_standings_alt(self, sport_code, provider_key, competition_ref, season_label, now, *, low_priority=False):
        self.standings_alt_calls.append((sport_code, provider_key, competition_ref, season_label))
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.standings_alt_to_return

    async def fetch_lineups(self, sport_code, fixture_ref, now, *, low_priority=True):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.lineups_to_return

    async def fetch_injuries(self, sport_code, team_ref, now, *, low_priority=True, season_label=None):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.injuries_to_return

    async def fetch_transfers(self, sport_code, team_ref, now, *, low_priority=True):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.transfers_to_return

    async def fetch_coach(self, sport_code, team_ref, now, *, low_priority=True):
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        return self.coach_to_return


@dataclass
class FakeLock:
    held: set = field(default_factory=set)

    async def acquire(self, key, ttl_seconds):
        if key in self.held:
            return False
        self.held.add(key)
        return True

    async def release(self, key):
        self.held.discard(key)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"sports": None, "ingestion": None, "knowledge_graph": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SportsBase.metadata.create_all)
        await conn.run_sync(IngestionBase.metadata.create_all)
        await conn.run_sync(KGBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s

    await engine.dispose()


@pytest.fixture
def router():
    return FakeRouter()


@pytest.fixture
def lock():
    return FakeLock()


@dataclass
class FakeOddsFeatureWriter:
    calls: list = field(default_factory=list)

    async def compute_and_write(self, fixture_id, odds, now):
        self.calls.append((fixture_id, odds, now))
        return ("football.market.overround",)


@pytest.fixture
def odds_writer():
    return FakeOddsFeatureWriter()


@pytest.fixture
def orchestrator_with_odds_writer(session, router, lock, odds_writer):
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    reconciler = EntityReconciliationService(
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
    return SyncOrchestrator(
        router=router,
        validator=DataValidationEngine(),
        quality=IngestionQualityEngine(
            sync_runs=SqlAlchemySyncRunRepository(session=session),
            reports=SqlAlchemyDataQualityReportRepository(session=session),
        ),
        reconciler=reconciler,
        sports=SqlAlchemySportRepository(session=session),
        checkpoints=SqlAlchemySyncCheckpointRepository(session=session),
        sync_runs=SqlAlchemySyncRunRepository(session=session),
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        lock=lock,
        odds_feature_writers={"football": odds_writer},
    )


@pytest.fixture
def orchestrator(session, router, lock):
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    reconciler = EntityReconciliationService(
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
    return SyncOrchestrator(
        router=router,
        validator=DataValidationEngine(),
        quality=IngestionQualityEngine(
            sync_runs=SqlAlchemySyncRunRepository(session=session),
            reports=SqlAlchemyDataQualityReportRepository(session=session),
        ),
        reconciler=reconciler,
        sports=SqlAlchemySportRepository(session=session),
        checkpoints=SqlAlchemySyncCheckpointRepository(session=session),
        sync_runs=SqlAlchemySyncRunRepository(session=session),
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        lock=lock,
    )


@dataclass
class FakeFixtureSourceRepo:
    store: dict = field(default_factory=dict)

    async def get_by_competition(self, competition_id):
        return self.store.get(competition_id)

    async def upsert(self, preference):
        self.store[preference.competition_id] = preference
        return preference

    async def delete(self, competition_id):
        self.store.pop(competition_id, None)

    async def list_all(self):
        return list(self.store.values())


@pytest.fixture
def fixture_source_preferences():
    return FakeFixtureSourceRepo()


@pytest.fixture
def orchestrator_with_fixture_source(session, router, lock, fixture_source_preferences):
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    reconciler = EntityReconciliationService(
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
    return SyncOrchestrator(
        router=router,
        validator=DataValidationEngine(),
        quality=IngestionQualityEngine(
            sync_runs=SqlAlchemySyncRunRepository(session=session),
            reports=SqlAlchemyDataQualityReportRepository(session=session),
        ),
        reconciler=reconciler,
        sports=SqlAlchemySportRepository(session=session),
        checkpoints=SqlAlchemySyncCheckpointRepository(session=session),
        sync_runs=SqlAlchemySyncRunRepository(session=session),
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        lock=lock,
        fixture_source_preferences=fixture_source_preferences,
    )


@pytest.mark.asyncio
async def test_sync_upcoming_fixtures_raises_when_orchestrator_not_wired_with_repository(orchestrator):
    with pytest.raises(NoFixtureSourcePreferenceError):
        await orchestrator.sync_upcoming_fixtures("football", "comp-1", "2026", SeasonId(uuid4()), T0)


@pytest.mark.asyncio
async def test_sync_upcoming_fixtures_raises_when_no_preference_configured(orchestrator_with_fixture_source):
    with pytest.raises(NoFixtureSourcePreferenceError):
        await orchestrator_with_fixture_source.sync_upcoming_fixtures("football", "comp-1", "2026", SeasonId(uuid4()), T0)


@pytest.mark.asyncio
async def test_sync_upcoming_fixtures_uses_preference_to_resolve_provider_and_reconciles(
    orchestrator_with_fixture_source, session, router, fixture_source_preferences
):
    home = await _seed_team(orchestrator_with_fixture_source, session, "t1")
    away, _ = await orchestrator_with_fixture_source.reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t2"), name="Chelsea", short_name="CHE", country="England"),
        home.sport_id, T0,
    )
    await session.commit()
    # Simulate a confirmed cross-provider team mapping (CrossProviderTeamMappingService.confirm_mappings).
    await orchestrator_with_fixture_source.reconciler.ref_index.upsert(
        ProviderRefIndexEntry("football_data_org", "fd-t1", EntityKind.TEAM, str(home.id.value))
    )
    await orchestrator_with_fixture_source.reconciler.ref_index.upsert(
        ProviderRefIndexEntry("football_data_org", "fd-t2", EntityKind.TEAM, str(away.id.value))
    )
    await session.commit()

    fixture_source_preferences.store["comp-1"] = CompetitionFixtureSourcePreference(
        competition_id="comp-1", preferred_provider_key="football_data_org", provider_competition_ref="PL",
    )
    router.upcoming_fixtures_to_return = [
        ProviderFixtureRecord(
            external_ref=ProviderRef("football_data_org", "fd-fx1"),
            home_team_ref=ProviderRef("football_data_org", "fd-t1"),
            away_team_ref=ProviderRef("football_data_org", "fd-t2"),
            scheduled_at=T0, competition_ref="PL", season_label="2026",
        )
    ]

    run = await orchestrator_with_fixture_source.sync_upcoming_fixtures("football", "comp-1", "2026", SeasonId(uuid4()), T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_created == 1
    assert router.upcoming_fixtures_calls == [("football", "football_data_org", "PL", "2026")]


@pytest.mark.asyncio
async def test_sync_upcoming_fixtures_uses_a_scope_key_distinct_from_sync_fixtures(
    orchestrator_with_fixture_source, session, router, fixture_source_preferences
):
    """Different checkpoint/lock scope than the default sync_fixtures for the same competition —
    otherwise the two sync paths would incorrectly skip/block each other via the incremental-skip
    or distributed-lock machinery `_run_sync` shares between every sync_* method."""
    await _seed_sport(orchestrator_with_fixture_source, session)
    fixture_source_preferences.store["comp-1"] = CompetitionFixtureSourcePreference(
        competition_id="comp-1", preferred_provider_key="football_data_org", provider_competition_ref="PL",
    )
    router.fixtures_to_return = []
    router.upcoming_fixtures_to_return = []

    default_run = await orchestrator_with_fixture_source.sync_fixtures("football", "comp-1", "2026", SeasonId(uuid4()), T0)
    await session.commit()
    upcoming_run = await orchestrator_with_fixture_source.sync_upcoming_fixtures(
        "football", "comp-1", "2026", SeasonId(uuid4()), T0
    )
    await session.commit()

    assert default_run is not None
    assert upcoming_run is not None  # not skipped by sync_fixtures' checkpoint for the same competition


@pytest.mark.asyncio
async def test_sync_completed_fixtures_raises_when_orchestrator_not_wired_with_repository(orchestrator):
    with pytest.raises(NoFixtureSourcePreferenceError):
        await orchestrator.sync_completed_fixtures("football", "comp-1", "2026", SeasonId(uuid4()), T0)


@pytest.mark.asyncio
async def test_sync_completed_fixtures_raises_when_no_preference_configured(orchestrator_with_fixture_source):
    with pytest.raises(NoFixtureSourcePreferenceError):
        await orchestrator_with_fixture_source.sync_completed_fixtures("football", "comp-1", "2026", SeasonId(uuid4()), T0)


@pytest.mark.asyncio
async def test_sync_completed_fixtures_updates_a_previously_upcoming_fixture_with_its_final_score(
    orchestrator_with_fixture_source, session, router, fixture_source_preferences
):
    """The core value of this sync path: a fixture `sync_upcoming_fixtures` created while
    SCHEDULED gets its final score and COMPLETED status once football-data.org reports it
    FINISHED — without this, such a fixture (which api-football never sees, since it wasn't the
    provider that scheduled it) would sit at SCHEDULED forever."""
    home = await _seed_team(orchestrator_with_fixture_source, session, "t1")
    away, _ = await orchestrator_with_fixture_source.reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t2"), name="Chelsea", short_name="CHE", country="England"),
        home.sport_id, T0,
    )
    await session.commit()
    await orchestrator_with_fixture_source.reconciler.ref_index.upsert(
        ProviderRefIndexEntry("football_data_org", "fd-t1", EntityKind.TEAM, str(home.id.value))
    )
    await orchestrator_with_fixture_source.reconciler.ref_index.upsert(
        ProviderRefIndexEntry("football_data_org", "fd-t2", EntityKind.TEAM, str(away.id.value))
    )
    await session.commit()

    fixture_source_preferences.store["comp-1"] = CompetitionFixtureSourcePreference(
        competition_id="comp-1", preferred_provider_key="football_data_org", provider_competition_ref="PL",
    )
    router.upcoming_fixtures_to_return = [
        ProviderFixtureRecord(
            external_ref=ProviderRef("football_data_org", "fd-fx1"),
            home_team_ref=ProviderRef("football_data_org", "fd-t1"),
            away_team_ref=ProviderRef("football_data_org", "fd-t2"),
            scheduled_at=T0, competition_ref="PL", season_label="2026", status="SCHEDULED",
        )
    ]
    upcoming_run = await orchestrator_with_fixture_source.sync_upcoming_fixtures("football", "comp-1", "2026", SeasonId(uuid4()), T0)
    await session.commit()
    assert upcoming_run.records_created == 1

    router.completed_fixtures_to_return = [
        ProviderFixtureRecord(
            external_ref=ProviderRef("football_data_org", "fd-fx1"),
            home_team_ref=ProviderRef("football_data_org", "fd-t1"),
            away_team_ref=ProviderRef("football_data_org", "fd-t2"),
            scheduled_at=T0, competition_ref="PL", season_label="2026", status="FINISHED",
            home_score=2, away_score=1,
        )
    ]
    completed_run = await orchestrator_with_fixture_source.sync_completed_fixtures(
        "football", "comp-1", "2026", SeasonId(uuid4()), T0 + timedelta(hours=2),
    )
    await session.commit()

    assert completed_run.status is SyncStatus.SUCCEEDED
    assert completed_run.records_updated == 1
    assert router.completed_fixtures_calls == [("football", "football_data_org", "PL", "2026")]
    fixture_id = await orchestrator_with_fixture_source.reconciler.ref_index.get("football_data_org", "fd-fx1", EntityKind.FIXTURE)
    saved = await orchestrator_with_fixture_source.reconciler.fixtures.get(FixtureId(uuid.UUID(fixture_id)))
    assert saved.home_score == 2
    assert saved.away_score == 1
    assert saved.status.value == "completed"


async def _seed_sport(orchestrator, session):
    await orchestrator.reconciler.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()


@pytest.mark.asyncio
async def test_sync_teams_requires_reconciled_sport(orchestrator):
    with pytest.raises(SportNotReconciledError):
        await orchestrator.sync_teams("football", "39", T0)


@pytest.mark.asyncio
async def test_sync_teams_reconciles_valid_records(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = [
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t1"), name="Arsenal", short_name="ARS", country="England"),
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t2"), name="Chelsea", short_name="CHE", country="England"),
    ]

    run = await orchestrator.sync_teams("football", "39", T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_fetched == 2
    assert run.records_created == 2
    assert run.records_rejected == 0


@pytest.mark.asyncio
async def test_sync_teams_rejects_invalid_records(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = [
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t1"), name="Arsenal", short_name="ARS", country="England"),
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t2"), name="", short_name="CHE", country="England"),
    ]

    run = await orchestrator.sync_teams("football", "39", T0)
    await session.commit()

    assert run.status is SyncStatus.PARTIAL  # 1 of 2 rejected
    assert run.records_created == 1
    assert run.records_rejected == 1
    assert run.validation_failures == 1


@pytest.mark.asyncio
async def test_sync_teams_all_rejected_gives_partial_status(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = [
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t1"), name="", short_name="ARS", country="England"),
    ]

    run = await orchestrator.sync_teams("football", "39", T0)
    await session.commit()

    assert run.status is SyncStatus.PARTIAL


@pytest.mark.asyncio
async def test_sync_teams_generates_quality_report(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = [
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t1"), name="Arsenal", short_name="ARS", country="England"),
    ]

    await orchestrator.sync_teams("football", "39", T0)
    await session.commit()

    report = await orchestrator.quality.get_latest("football", EntityKind.TEAM)
    assert report is not None
    assert report.sample_size == 1


@pytest.mark.asyncio
async def test_sync_teams_updates_checkpoint(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = []

    await orchestrator.sync_teams("football", "39", T0)
    await session.commit()

    checkpoint = await orchestrator.checkpoints.get("football", EntityKind.TEAM, "39")
    assert checkpoint is not None
    assert checkpoint.last_success_at is not None
    assert checkpoint.consecutive_failures == 0


@pytest.mark.asyncio
async def test_incremental_sync_skips_within_min_interval(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = []

    first = await orchestrator.sync_teams("football", "39", T0)
    await session.commit()
    second = await orchestrator.sync_teams("football", "39", T0 + timedelta(seconds=10))
    await session.commit()

    assert first is not None
    assert second is None  # skipped — well within DEFAULT_MIN_SYNC_INTERVAL_SECONDS
    assert len(router.teams_by_call) == 1


@pytest.mark.asyncio
async def test_force_bypasses_incremental_skip(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = []

    await orchestrator.sync_teams("football", "39", T0)
    await session.commit()
    forced = await orchestrator.sync_teams("football", "39", T0 + timedelta(seconds=10), force=True)
    await session.commit()

    assert forced is not None
    assert len(router.teams_by_call) == 2


@pytest.mark.asyncio
async def test_sync_after_interval_elapses_runs_again(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = []

    await orchestrator.sync_teams("football", "39", T0)
    await session.commit()
    later = await orchestrator.sync_teams("football", "39", T0 + timedelta(minutes=10), force=False)
    await session.commit()

    assert later is not None


@pytest.mark.asyncio
async def test_live_trigger_bypasses_incremental_skip(orchestrator, session, router):
    season_id = SeasonId(uuid4())

    first = await orchestrator.sync_fixtures("football", "39", "2026", season_id, T0)
    await session.commit()
    live = await orchestrator.sync_live_fixtures("football", "39", "2026", season_id, T0 + timedelta(seconds=5))
    await session.commit()

    assert first is not None and first.status is SyncStatus.SUCCEEDED
    assert live is not None and live.status is SyncStatus.SUCCEEDED  # LIVE trigger never skipped
    assert live.trigger is SyncTrigger.LIVE


@pytest.mark.asyncio
async def test_locked_scope_prevents_concurrent_sync(orchestrator, session, lock, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = []
    lock.held.add("sync:football:team:39")

    run = await orchestrator.sync_teams("football", "39", T0)

    assert run is None


@pytest.mark.asyncio
async def test_lock_is_released_after_sync_completes(orchestrator, session, lock, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = []

    await orchestrator.sync_teams("football", "39", T0)

    assert "sync:football:team:39" not in lock.held


@pytest.mark.asyncio
async def test_fetch_failure_marks_run_failed_and_increments_checkpoint_failures(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.raise_on_fetch = RuntimeError("provider unreachable")

    run = await orchestrator.sync_teams("football", "39", T0)
    await session.commit()

    assert run.status is SyncStatus.FAILED
    assert run.error_message == "provider unreachable"

    checkpoint = await orchestrator.checkpoints.get("football", EntityKind.TEAM, "39")
    assert checkpoint.consecutive_failures == 1


@pytest.mark.asyncio
async def test_lock_released_even_on_fetch_failure(orchestrator, session, lock, router):
    await _seed_sport(orchestrator, session)
    router.raise_on_fetch = RuntimeError("boom")

    await orchestrator.sync_teams("football", "39", T0)

    assert "sync:football:team:39" not in lock.held


@pytest.mark.asyncio
async def test_retry_after_failure_resets_consecutive_failures_on_success(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.raise_on_fetch = RuntimeError("boom")
    await orchestrator.sync_teams("football", "39", T0, force=True)
    await session.commit()

    router.raise_on_fetch = None
    router.teams_to_return = []
    await orchestrator.sync_teams("football", "39", T0 + timedelta(minutes=10), trigger=SyncTrigger.RETRY, force=True)
    await session.commit()

    checkpoint = await orchestrator.checkpoints.get("football", EntityKind.TEAM, "39")
    assert checkpoint.consecutive_failures == 0


@pytest.mark.asyncio
async def test_sync_countries_uses_long_interval(orchestrator, session, router):
    router.countries_to_return = [ProviderCountryRecord(code="GB", name="United Kingdom")]

    first = await orchestrator.sync_countries("football", T0)
    await session.commit()
    second = await orchestrator.sync_countries("football", T0 + timedelta(hours=1))
    await session.commit()

    assert first is not None
    assert second is None  # well within the 24h countries interval


@pytest.mark.asyncio
async def test_sync_emits_timeline_events(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    router.teams_to_return = []

    await orchestrator.sync_teams("football", "39", T0)
    await session.commit()

    events = await orchestrator.timeline.list_recent(entity_kind=EntityKind.TEAM, entity_id="39")
    event_types = {e.event_type for e in events}
    assert TimelineEventType.SYNC_STARTED in event_types
    assert TimelineEventType.SYNC_COMPLETED in event_types


@pytest.mark.asyncio
async def test_sync_standings_reconciles_valid_records(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    sport = await orchestrator.sports.get_by_code(SportCode.FOOTBALL)
    team_repo = SqlAlchemyTeamRepository(session=session)

    team = await team_repo.upsert(Team(id=TeamId(uuid4()), sport_id=sport.id, name="Arsenal", short_name="ARS", country="England"))
    await orchestrator.reconciler._record_ref("mock", "t1", EntityKind.TEAM, str(team.id.value))
    await session.commit()

    season_id = SeasonId(uuid4())
    router.standings_to_return = [
        ProviderStandingRecord(team_ref=ProviderRef("mock", "t1"), rank=1, points=45.0, record={"won": 14}),
    ]

    run = await orchestrator.sync_standings("football", "39", "2026", season_id, T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_created == 1


@pytest.mark.asyncio
async def test_sync_standings_rejects_records_for_unreconciled_teams(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    season_id = SeasonId(uuid4())
    router.standings_to_return = [
        ProviderStandingRecord(team_ref=ProviderRef("mock", "unknown"), rank=1, points=45.0, record={}),
    ]

    run = await orchestrator.sync_standings("football", "39", "2026", season_id, T0)
    await session.commit()

    assert run.status is SyncStatus.PARTIAL
    assert run.records_rejected == 1


@pytest.mark.asyncio
async def test_sync_standings_alt_raises_when_orchestrator_not_wired_with_repository(orchestrator):
    with pytest.raises(NoFixtureSourcePreferenceError):
        await orchestrator.sync_standings_alt("football", "comp-1", "2026", SeasonId(uuid4()), T0)


@pytest.mark.asyncio
async def test_sync_standings_alt_raises_when_no_preference_configured(orchestrator_with_fixture_source):
    with pytest.raises(NoFixtureSourcePreferenceError):
        await orchestrator_with_fixture_source.sync_standings_alt("football", "comp-1", "2026", SeasonId(uuid4()), T0)


@pytest.mark.asyncio
async def test_sync_standings_alt_uses_preference_to_resolve_provider_and_reconciles(
    orchestrator_with_fixture_source, session, router, fixture_source_preferences
):
    home = await _seed_team(orchestrator_with_fixture_source, session, "t1")
    await orchestrator_with_fixture_source.reconciler.ref_index.upsert(
        ProviderRefIndexEntry("football_data_org", "fd-t1", EntityKind.TEAM, str(home.id.value))
    )
    await session.commit()

    fixture_source_preferences.store["comp-1"] = CompetitionFixtureSourcePreference(
        competition_id="comp-1", preferred_provider_key="football_data_org", provider_competition_ref="PL",
    )
    router.standings_alt_to_return = [
        ProviderStandingRecord(team_ref=ProviderRef("football_data_org", "fd-t1"), rank=1, points=85.0, record={"won": 27}),
    ]

    run = await orchestrator_with_fixture_source.sync_standings_alt("football", "comp-1", "2026", SeasonId(uuid4()), T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_created == 1
    assert router.standings_alt_calls == [("football", "football_data_org", "PL", "2026")]


@pytest.mark.asyncio
async def test_sync_standings_alt_rejects_records_for_unreconciled_teams(
    orchestrator_with_fixture_source, session, fixture_source_preferences, router
):
    await _seed_sport(orchestrator_with_fixture_source, session)
    fixture_source_preferences.store["comp-1"] = CompetitionFixtureSourcePreference(
        competition_id="comp-1", preferred_provider_key="football_data_org", provider_competition_ref="PL",
    )
    router.standings_alt_to_return = [
        ProviderStandingRecord(team_ref=ProviderRef("football_data_org", "unknown"), rank=1, points=45.0, record={}),
    ]

    run = await orchestrator_with_fixture_source.sync_standings_alt("football", "comp-1", "2026", SeasonId(uuid4()), T0)
    await session.commit()

    assert run.status is SyncStatus.PARTIAL
    assert run.records_rejected == 1


@pytest.mark.asyncio
async def test_sync_fixtures_rejects_records_referencing_unreconciled_teams(orchestrator, session, router):
    await _seed_sport(orchestrator, session)
    season_id = SeasonId(uuid4())
    router.fixtures_to_return = [
        ProviderFixtureRecord(
            external_ref=ProviderRef("mock", "f1"),
            home_team_ref=ProviderRef("mock", "unknown-home"),
            away_team_ref=ProviderRef("mock", "unknown-away"),
            scheduled_at=T0,
            competition_ref="39",
            season_label="2026",
        ),
    ]

    run = await orchestrator.sync_fixtures("football", "39", "2026", season_id, T0)
    await session.commit()

    assert run.status is SyncStatus.PARTIAL
    assert run.records_rejected == 1


@pytest.mark.asyncio
async def test_sync_fixtures_scope_key_isolates_by_season_never_sharing_a_checkpoint(orchestrator, session, router):
    """POST-M24 Phase 7 — real season isolation: `_run_sync`'s checkpoint/lock is keyed by
    `(sport_code, entity_kind, scope_key)` where `scope_key = f"{competition_ref}:{season_label}"`.
    Syncing one season for a competition must never be treated as "already synced" (or otherwise
    interfere with) a different season on the exact same competition — a real basketball/baseball
    NBA/MLB scenario this phase hit directly (2024 vs. 2026 for the same league)."""
    await _seed_sport(orchestrator, session)
    season_2024, season_2026 = SeasonId(uuid4()), SeasonId(uuid4())

    run_2024 = await orchestrator.sync_fixtures("football", "39", "2024", season_2024, T0)
    await session.commit()
    run_2026 = await orchestrator.sync_fixtures("football", "39", "2026", season_2026, T0)
    await session.commit()

    assert run_2024 is not None and run_2026 is not None
    assert run_2024.scope_key == "39:2024"
    assert run_2026.scope_key == "39:2026"
    assert run_2024.scope_key != run_2026.scope_key


@pytest.mark.asyncio
async def test_sync_fixtures_surfaces_a_real_provider_rejection_as_a_failed_run(orchestrator, session, router):
    """POST-M24 Phase 7 — the exact real behavior this phase's live current-season sync attempt
    hit: the provider's own plan-tier rejection ("Free plans do not have access to this season")
    must surface as a real FAILED SyncRun with the genuine error message preserved, never silently
    swallowed or misreported as a successful empty result."""
    await _seed_sport(orchestrator, session)
    router.raise_on_fetch = ProviderRequestError(
        "api_basketball request to /games rejected by provider: "
        "{'plan': 'Free plans do not have access to this season, try from 2022 to 2024.'}",
        kind=ProviderErrorKind.PERMANENT,
    )

    run = await orchestrator.sync_fixtures("basketball", "12", "2026-2027", SeasonId(uuid4()), T0)
    await session.commit()

    assert run is not None
    assert run.status is SyncStatus.FAILED
    assert "Free plans do not have access to this season" in run.error_message
    assert run.records_fetched == 0
    assert run.records_created == 0


@pytest.mark.asyncio
async def test_sync_odds_writes_features_when_a_writer_is_registered(orchestrator_with_odds_writer, router, odds_writer):
    fixture_ref = ProviderRef("mock", "fx1")
    router.odds_to_return = ProviderOddsRecord(fixture_ref=fixture_ref, home_win=2.1, draw=3.4, away_win=3.6)

    run = await orchestrator_with_odds_writer.sync_odds_for_fixture("football", fixture_ref, "fixture-id-1", T0)

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_fetched == 1
    assert len(odds_writer.calls) == 1
    assert odds_writer.calls[0][0] == "fixture-id-1"


@pytest.mark.asyncio
async def test_sync_odds_rejects_invalid_record_and_skips_writer(orchestrator_with_odds_writer, router, odds_writer):
    fixture_ref = ProviderRef("mock", "fx1")
    router.odds_to_return = ProviderOddsRecord(fixture_ref=fixture_ref, home_win=1.0, draw=3.4, away_win=3.6)  # <=1.0 is invalid

    run = await orchestrator_with_odds_writer.sync_odds_for_fixture("football", fixture_ref, "fixture-id-1", T0)

    assert run.status is SyncStatus.PARTIAL
    assert run.records_rejected == 1
    assert odds_writer.calls == []


@pytest.mark.asyncio
async def test_sync_odds_no_line_available_yet_succeeds_with_zero_records(orchestrator_with_odds_writer, router, odds_writer):
    fixture_ref = ProviderRef("mock", "fx1")
    router.odds_to_return = None

    run = await orchestrator_with_odds_writer.sync_odds_for_fixture("football", fixture_ref, "fixture-id-1", T0)

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_fetched == 0
    assert odds_writer.calls == []


@pytest.mark.asyncio
async def test_sync_odds_skips_write_silently_when_no_writer_registered_for_sport(orchestrator, router):
    """`orchestrator` (no odds_feature_writers) exercises the default empty-dict field — this
    must not crash, matching EntityReconciliationService's form_differential_calculators
    posture for an unregistered sport."""
    fixture_ref = ProviderRef("mock", "fx1")
    router.odds_to_return = ProviderOddsRecord(fixture_ref=fixture_ref, home_win=2.1, draw=3.4, away_win=3.6)

    run = await orchestrator.sync_odds_for_fixture("football", fixture_ref, "fixture-id-1", T0)

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_created == 1


async def _seed_team(orchestrator, session, external_id="t1"):
    sport, _ = await orchestrator.reconciler.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    team, _ = await orchestrator.reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("mock", external_id), name="Arsenal", short_name="ARS", country="England"),
        sport.id, T0,
    )
    await session.commit()
    return team


_FIXTURE_ID = str(uuid4())


@pytest.mark.asyncio
async def test_sync_team_statistics_creates_match_and_statistics(orchestrator, session, router):
    await _seed_team(orchestrator, session)
    fixture_ref = ProviderRef("mock", "fx1")
    router.team_statistics_to_return = [
        ProviderTeamStatisticsRecord(fixture_ref=fixture_ref, team_ref=ProviderRef("mock", "t1"), stat_set={"possession_pct": 55.0}),
    ]

    run = await orchestrator.sync_team_statistics_for_fixture("football", fixture_ref, _FIXTURE_ID, T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_fetched == 1
    assert run.records_created == 1
    match = await orchestrator.reconciler.matches.get_by_fixture(FixtureId(uuid.UUID(_FIXTURE_ID)))
    assert match is not None


@pytest.mark.asyncio
async def test_sync_team_statistics_rejects_invalid_record(orchestrator, session, router):
    await _seed_team(orchestrator, session)
    fixture_ref = ProviderRef("mock", "fx1")
    router.team_statistics_to_return = [
        ProviderTeamStatisticsRecord(fixture_ref=fixture_ref, team_ref=ProviderRef("mock", "t1"), stat_set={}),
    ]

    run = await orchestrator.sync_team_statistics_for_fixture("football", fixture_ref, _FIXTURE_ID, T0)

    assert run.status is SyncStatus.PARTIAL
    assert run.records_rejected == 1


@pytest.mark.asyncio
async def test_sync_team_statistics_rejects_when_team_not_reconciled(orchestrator, session, router):
    await orchestrator.reconciler.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    fixture_ref = ProviderRef("mock", "fx1")
    router.team_statistics_to_return = [
        ProviderTeamStatisticsRecord(fixture_ref=fixture_ref, team_ref=ProviderRef("mock", "unknown-team"), stat_set={"possession_pct": 55.0}),
    ]

    run = await orchestrator.sync_team_statistics_for_fixture("football", fixture_ref, _FIXTURE_ID, T0)

    assert run.status is SyncStatus.PARTIAL
    assert run.records_rejected == 1


@pytest.mark.asyncio
async def test_sync_players_creates_roster_linked_to_team(orchestrator, session, router):
    team = await _seed_team(orchestrator, session)
    team_ref = ProviderRef("mock", "t1")
    router.players_to_return = [
        ProviderPlayerRecord(
            external_ref=ProviderRef("mock", "p1"), team_ref=team_ref, name="Bruno Fernandes",
            date_of_birth=datetime(1994, 9, 8, tzinfo=timezone.utc), position="Midfielder",
        ),
        ProviderPlayerRecord(
            external_ref=ProviderRef("mock", "p2"), team_ref=team_ref, name="Andre Onana",
            date_of_birth=datetime(1996, 4, 2, tzinfo=timezone.utc), position="Goalkeeper",
        ),
    ]

    run = await orchestrator.sync_players("football", team_ref, T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_fetched == 2
    assert run.records_created == 2
    players = await orchestrator.reconciler.players.list_by_sport(team.sport_id, limit=10)
    assert {p.name for p in players} == {"Bruno Fernandes", "Andre Onana"}
    assert all(p.team_id == team.id for p in players)


@pytest.mark.asyncio
async def test_sync_players_rejects_invalid_record(orchestrator, session, router):
    team = await _seed_team(orchestrator, session)
    team_ref = ProviderRef("mock", "t1")
    router.players_to_return = [
        ProviderPlayerRecord(external_ref=ProviderRef("mock", "p1"), team_ref=team_ref, name="   ", date_of_birth=None, position=None),
    ]

    run = await orchestrator.sync_players("football", team_ref, T0)

    assert run.status is SyncStatus.PARTIAL
    assert run.records_rejected == 1


@pytest.mark.asyncio
async def test_sync_players_re_run_updates_existing_roster_instead_of_duplicating(orchestrator, session, router):
    team = await _seed_team(orchestrator, session)
    team_ref = ProviderRef("mock", "t1")
    router.players_to_return = [
        ProviderPlayerRecord(external_ref=ProviderRef("mock", "p1"), team_ref=team_ref, name="Bruno Fernandes", date_of_birth=None, position="Midfielder"),
    ]
    await orchestrator.sync_players("football", team_ref, T0)
    await session.commit()

    router.players_to_return = [
        ProviderPlayerRecord(external_ref=ProviderRef("mock", "p1"), team_ref=team_ref, name="Bruno Fernandes", date_of_birth=None, position="Midfielder"),
    ]
    run = await orchestrator.sync_players("football", team_ref, T0 + timedelta(days=1), force=True)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_updated == 1
    players = await orchestrator.reconciler.players.list_by_sport(team.sport_id, limit=10)
    assert len(players) == 1


@pytest.mark.asyncio
async def test_sync_lineups_creates_match_and_lineup(orchestrator, session, router):
    team = await _seed_team(orchestrator, session)
    fixture_ref = ProviderRef("mock", "fx-lineup")
    router.players_to_return = [
        ProviderPlayerRecord(external_ref=ProviderRef("mock", "p1"), team_ref=ProviderRef("mock", "t1"), name="Bruno Fernandes", date_of_birth=None, position="Midfielder"),
    ]
    await orchestrator.sync_players("football", ProviderRef("mock", "t1"), T0)
    await session.commit()

    router.lineups_to_return = [
        ProviderLineupRecord(
            fixture_ref=fixture_ref, team_ref=ProviderRef("mock", "t1"), formation="4-3-3",
            slots=(ProviderLineupSlotRecord(player_ref=ProviderRef("mock", "p1"), role="starter", position="MF", shirt_number=8),),
        ),
    ]

    fixture_id = str(uuid4())
    run = await orchestrator.sync_lineups("football", fixture_ref, fixture_id, T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_created == 1
    match = await orchestrator.reconciler.matches.get_by_fixture(FixtureId(uuid.UUID(fixture_id)))
    lineup = await orchestrator.reconciler.lineups.get_for_match_team(match.id, team.id)
    assert lineup is not None
    assert lineup.formation == "4-3-3"
    assert len(lineup.slots) == 1


@pytest.mark.asyncio
async def test_sync_lineups_rejects_empty_record(orchestrator, session, router):
    await _seed_team(orchestrator, session)
    fixture_ref = ProviderRef("mock", "fx-lineup-empty")
    router.lineups_to_return = [
        ProviderLineupRecord(fixture_ref=fixture_ref, team_ref=ProviderRef("mock", "t1"), formation=None, slots=()),
    ]

    run = await orchestrator.sync_lineups("football", fixture_ref, str(uuid4()), T0)

    assert run.status is SyncStatus.PARTIAL
    assert run.records_rejected == 1


@pytest.mark.asyncio
async def test_sync_injuries_requires_reconciled_team(orchestrator, router):
    """Squad-intelligence syncs reject a record whose team hasn't been reconciled yet, same
    "relationship" rejection posture as sync_team_statistics_for_fixture."""
    team_ref = ProviderRef("mock", "unknown-team")
    router.injuries_to_return = [
        ProviderInjuryRecord(player_ref=ProviderRef("mock", "p1"), team_ref=team_ref, status="Missing Fixture", reason="Hamstring"),
    ]

    run = await orchestrator.sync_injuries("football", team_ref, T0)

    assert run.status is SyncStatus.PARTIAL
    assert run.records_rejected == 1


@pytest.mark.asyncio
async def test_sync_injuries_creates_real_records(orchestrator, session, router):
    await _seed_team(orchestrator, session)
    team_ref = ProviderRef("mock", "t1")
    router.players_to_return = [
        ProviderPlayerRecord(external_ref=ProviderRef("mock", "p1"), team_ref=team_ref, name="Bruno Fernandes", date_of_birth=None, position="Midfielder"),
    ]
    await orchestrator.sync_players("football", team_ref, T0)
    await session.commit()

    router.injuries_to_return = [
        ProviderInjuryRecord(player_ref=ProviderRef("mock", "p1"), team_ref=team_ref, status="Missing Fixture", reason="Hamstring"),
    ]
    run = await orchestrator.sync_injuries("football", team_ref, T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_created == 1


@pytest.mark.asyncio
async def test_sync_transfers_creates_real_records(orchestrator, session, router):
    await _seed_team(orchestrator, session)
    team_ref = ProviderRef("mock", "t1")
    router.players_to_return = [
        ProviderPlayerRecord(external_ref=ProviderRef("mock", "p1"), team_ref=team_ref, name="Bruno Fernandes", date_of_birth=None, position="Midfielder"),
    ]
    await orchestrator.sync_players("football", team_ref, T0)
    await session.commit()

    router.transfers_to_return = [
        ProviderTransferRecord(
            player_ref=ProviderRef("mock", "p1"), from_team_ref=None, to_team_ref=team_ref,
            effective_date=T0, transfer_type="Free",
        ),
    ]
    run = await orchestrator.sync_transfers("football", team_ref, T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_created == 1


@pytest.mark.asyncio
async def test_sync_coaching_staff_creates_real_record(orchestrator, session, router):
    await _seed_team(orchestrator, session)
    team_ref = ProviderRef("mock", "t1")
    router.coach_to_return = ProviderCoachRecord(team_ref=team_ref, person_name="Mikel Arteta")

    run = await orchestrator.sync_coaching_staff("football", team_ref, T0)
    await session.commit()

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_fetched == 1
    assert run.records_created == 1


@pytest.mark.asyncio
async def test_sync_coaching_staff_honest_zero_when_provider_has_no_record(orchestrator, session, router):
    await _seed_team(orchestrator, session)
    team_ref = ProviderRef("mock", "t1")
    router.coach_to_return = None

    run = await orchestrator.sync_coaching_staff("football", team_ref, T0)

    assert run.status is SyncStatus.SUCCEEDED
    assert run.records_fetched == 0


@pytest.mark.asyncio
async def test_sync_upcoming_structured_intelligence_end_to_end(orchestrator, session, router):
    """Milestone 5 requirement 14: verify the full chain end-to-end — Celery Beat's task calls
    exactly this method (see `sync_upcoming_structured_intelligence_task`'s own docstring) with
    `trigger` left at its default, so this test exercises the real default, not an override, all
    the way down to persisted `SyncRun` rows. Proves: (1) a fixture within the structured-intel
    window gets both teams' injuries+transfers+coaching-staff synced exactly once each (deduped),
    (2) its lineups sync only fires because it's also within the kickoff-proximity window, (3)
    every resulting SyncRun carries `SyncTrigger.LIVE_SCHEDULED` — the one trigger
    `classify_availability` ever honors."""
    sport, _ = await orchestrator.reconciler.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    home, _ = await orchestrator.reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t1"), name="Arsenal", short_name="ARS", country="England"),
        sport.id, T0,
    )
    away, _ = await orchestrator.reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t2"), name="Chelsea", short_name="CHE", country="England"),
        sport.id, T0,
    )
    await session.commit()

    season_id = SeasonId(uuid4())
    kickoff = T0 + timedelta(minutes=30)  # within both the 72h structured-intel window and the 90min lineup window
    fixture, _ = await orchestrator.reconciler.reconcile_fixture(
        ProviderFixtureRecord(
            external_ref=ProviderRef("mock", "fx1"), home_team_ref=ProviderRef("mock", "t1"),
            away_team_ref=ProviderRef("mock", "t2"), scheduled_at=kickoff, competition_ref="39", season_label="2026",
            status="NS",
        ),
        season_id, T0, sport_code="football",
    )
    await session.commit()

    router.lineups_to_return = []
    router.injuries_to_return = []
    router.transfers_to_return = []
    router.coach_to_return = None

    runs = await orchestrator.sync_upcoming_structured_intelligence("football", season_id, T0)
    await session.commit()

    # 2 teams x (injuries + transfers + coaching staff) + 1 lineup sync for the one fixture = 7 SyncRuns
    assert len(runs) == 7
    assert all(r.trigger is SyncTrigger.LIVE_SCHEDULED for r in runs)
    assert sum(1 for r in runs if r.entity_kind is EntityKind.LINEUP) == 1
    assert sum(1 for r in runs if r.entity_kind is EntityKind.INJURY) == 2
    assert sum(1 for r in runs if r.entity_kind is EntityKind.TRANSFER) == 2
    assert sum(1 for r in runs if r.entity_kind is EntityKind.COACHING_STAFF) == 2


@pytest.mark.asyncio
async def test_sync_upcoming_structured_intelligence_skips_lineups_outside_kickoff_window(orchestrator, session, router):
    """A fixture within the broader structured-intel window but NOT yet within the narrower
    lineup pre-match window still gets injuries/transfers/coaching-staff synced (not fixture-bound,
    per spec §7) but no lineup sync attempt at all — the provider itself won't have lineups that
    early."""
    sport, _ = await orchestrator.reconciler.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    await orchestrator.reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t1"), name="Arsenal", short_name="ARS", country="England"),
        sport.id, T0,
    )
    await orchestrator.reconciler.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("mock", "t2"), name="Chelsea", short_name="CHE", country="England"),
        sport.id, T0,
    )
    await session.commit()

    season_id = SeasonId(uuid4())
    kickoff = T0 + timedelta(hours=10)  # within 72h structured-intel window, outside the 90min lineup window
    await orchestrator.reconciler.reconcile_fixture(
        ProviderFixtureRecord(
            external_ref=ProviderRef("mock", "fx1"), home_team_ref=ProviderRef("mock", "t1"),
            away_team_ref=ProviderRef("mock", "t2"), scheduled_at=kickoff, competition_ref="39", season_label="2026",
            status="NS",
        ),
        season_id, T0, sport_code="football",
    )
    await session.commit()

    runs = await orchestrator.sync_upcoming_structured_intelligence("football", season_id, T0)
    await session.commit()

    assert len(runs) == 6  # 2 teams x (injuries + transfers + coaching staff), no lineup run
    assert all(r.entity_kind is not EntityKind.LINEUP for r in runs)
