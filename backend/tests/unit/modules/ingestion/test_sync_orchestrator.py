from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.ingestion.application.data_quality_engine import IngestionQualityEngine
from modules.ingestion.application.data_validation_engine import DataValidationEngine
from modules.ingestion.application.entity_reconciliation_service import EntityReconciliationService
from modules.ingestion.application.sync_orchestrator import SportNotReconciledError, SyncOrchestrator
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
from modules.sports.domain.value_objects import ProviderRef, SeasonId, SportCode, TeamId
from modules.sports.infrastructure.persistence.models import Base as SportsBase
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyCountryRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyLineupRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyTeamStatisticsRepository,
    SqlAlchemyVenueRepository,
)
from modules.sports.ports.provider_gateway import ProviderCountryRecord, ProviderStandingRecord, ProviderTeamRecord

T0 = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


@dataclass
class FakeRouter:
    teams_by_call: list = field(default_factory=list)
    teams_to_return: list = field(default_factory=list)
    countries_to_return: list = field(default_factory=list)
    fixtures_to_return: list = field(default_factory=list)
    standings_to_return: list = field(default_factory=list)
    raise_on_fetch: Exception | None = None

    async def fetch_teams(self, sport_code, competition_ref, now, *, low_priority=False):
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
        team_statistics=SqlAlchemyTeamStatisticsRepository(session=session),
        lineups=SqlAlchemyLineupRepository(session=session),
        standings=SqlAlchemyStandingRepository(session=session),
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
