from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.alerts.application.alert_service import AlertService
from modules.alerts.domain.value_objects import AlertType
from modules.alerts.infrastructure.persistence.models import Base as AlertsBase
from modules.alerts.infrastructure.persistence.repositories import SqlAlchemyAlertEventRepository
from modules.identity.domain.value_objects import UserId
from modules.ingestion.application.entity_reconciliation_service import (
    EntityReconciliationService,
    ReconciliationDependencyError,
)
from modules.ingestion.domain.entities import ProviderRefIndexEntry
from modules.ingestion.domain.value_objects import EntityKind, TimelineEventType
from modules.ingestion.infrastructure.persistence.models import Base as IngestionBase
from modules.ingestion.infrastructure.persistence.repositories import (
    SqlAlchemyProviderRefIndexRepository,
    SqlAlchemyTimelineEventRepository,
)
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base as KGBase
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)
from modules.sports.domain.value_objects import FixtureId, FixtureStatus, MatchId, ProviderRef, SeasonId, SportCode
from modules.sports.infrastructure.persistence.models import Base as SportsBase
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyCountryRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyMatchRepository,
    SqlAlchemyLineupRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyTeamStatisticsRepository,
    SqlAlchemyVenueRepository,
)
from modules.sports.ports.provider_gateway import (
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
)
from modules.watchlist.domain.entities import WatchlistEntry
from modules.watchlist.domain.value_objects import WatchlistEntityType, WatchlistEntryId
from modules.watchlist.infrastructure.persistence.models import Base as WatchlistBase
from modules.watchlist.infrastructure.persistence.repositories import SqlAlchemyWatchlistRepository

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


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
def service(session):
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
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
    )


class _RecordingOutcomeResolver:
    """Stub standing in for `OutcomeResolutionService` — this test file verifies only the
    *trigger condition* (fixture reaches COMPLETED with a final score), not the resolver's own
    per-market logic, which `tests/unit/modules/predictions/test_outcome_resolution_service.py`
    already covers directly."""

    def __init__(self):
        self.calls = []

    async def resolve_for_fixture(self, fixture_id, home_score, away_score, now):
        self.calls.append((fixture_id, home_score, away_score, now))
        return []


@pytest.fixture
def service_with_outcome_resolver(session):
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    resolver = _RecordingOutcomeResolver()
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
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        outcome_resolver=resolver,
    ), resolver


class _RecordingFormDifferentialCalculator:
    """Stub standing in for `FixtureFormDifferentialCalculator` — verifies only the *wiring*
    (called with the right args, for the right sport), not its own computation, which
    `test_windowed_feature_engineering_service.py` already covers directly."""

    def __init__(self):
        self.calls = []

    async def compute_and_write(self, fixture_id, home_team_id, away_team_id, now):
        self.calls.append((fixture_id, home_team_id, away_team_id, now))
        return 0.0


@pytest.fixture
def service_with_form_differential(session):
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    calculator = _RecordingFormDifferentialCalculator()
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
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        form_differential_calculators={"football": (calculator,)},
    ), calculator


@pytest.fixture
def service_with_alerts(session):
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    alerts = AlertService(
        events=SqlAlchemyAlertEventRepository(session=session),
        watchlist=SqlAlchemyWatchlistRepository(session=session),
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
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        alerts=alerts,
    ), alerts


class TestReconcileSeasonDateDerivation:
    """Regression coverage for the football-data.org integration bug: a brand-new season used to
    be stamped with `date_range.start=now` (reconciliation time), so `_pick_current_season`
    (apps/api/routers/sports_router.py, orders seasons by `date_range.start`) picked whichever
    season happened to be *touched* most recently rather than the actually-current one — an old
    season re-synced today looked more "current" than a newer season synced yesterday. Real
    incident: syncing football-data.org's "2025" Premier League season made "2022" look current
    because it had been re-reconciled more recently in wall-clock time."""

    @pytest.mark.asyncio
    async def test_bare_year_label_derives_august_first_start(self, service, session):
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)

        season, created = await service.reconcile_season("39", "2025", "mock_football", competition.id, T0)
        await session.commit()

        assert created
        assert season.date_range.start == datetime(2025, 8, 1, tzinfo=T0.tzinfo)

    @pytest.mark.asyncio
    async def test_non_numeric_label_falls_back_to_now(self, service, session):
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)

        season, _ = await service.reconcile_season("39", "2025-26", "mock_football", competition.id, T0)
        await session.commit()

        assert season.date_range.start == T0

    @pytest.mark.asyncio
    async def test_reconciling_twice_does_not_move_an_existing_seasons_start(self, service, session):
        """The derived start is only ever computed for a brand-new season — re-reconciling an
        already-known season (e.g. a later sync picking up its latest label/name) must not shift
        its date_range, since that's exactly the "touched more recently" bug this guards against."""
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)

        first, _ = await service.reconcile_season("39", "2025", "mock_football", competition.id, T0)
        await session.commit()

        later = T0 + timedelta(days=30)
        second, was_created = await service.reconcile_season("39", "2025", "mock_football", competition.id, later)
        await session.commit()

        assert not was_created
        assert second.id == first.id
        # .replace(tzinfo=None): SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md
        # ADR-007) — `second` came from a genuine re-fetch of the existing row, `first` didn't,
        # so a bare equality would spuriously fail on tzinfo alone rather than the actual value
        # this test cares about: that re-reconciling didn't shift the timestamp.
        assert second.date_range.start.replace(tzinfo=None) == datetime(2025, 8, 1)
        assert first.date_range.start.replace(tzinfo=None) == datetime(2025, 8, 1)

    @pytest.mark.asyncio
    async def test_seasons_now_order_chronologically_not_by_reconciliation_order(self, service, session):
        """The actual bug scenario: reconcile an OLDER season (by label) AFTER a NEWER one, and
        confirm the newer season's derived start still sorts after the older one's — the defect
        this fix closes was exactly this ordering being backwards when both used `now`."""
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)

        newer, _ = await service.reconcile_season("39", "2025", "mock_football", competition.id, T0)
        await session.commit()
        older, _ = await service.reconcile_season("39", "2022", "mock_football", competition.id, T0 + timedelta(days=1))
        await session.commit()

        assert newer.date_range.start > older.date_range.start


def _team_record(external_id="t1", name="Arsenal") -> ProviderTeamRecord:
    return ProviderTeamRecord(
        external_ref=ProviderRef(provider="mock_football", external_id=external_id),
        name=name, short_name="ARS", country="England", venue_name="Emirates Stadium",
    )


@pytest.mark.asyncio
async def test_reconcile_sport_creates_then_updates(service, session):
    created, was_created = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    assert was_created
    assert created.version == 1

    updated, was_created_again = await service.reconcile_sport(SportCode.FOOTBALL, "Association Football", T0)
    await session.commit()

    assert not was_created_again
    assert updated.id == created.id
    assert updated.version == 2
    assert updated.name == "Association Football"


@pytest.mark.asyncio
async def test_reconcile_sport_emits_timeline_event(service, session):
    await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()

    events = await service.timeline.list_recent(entity_kind=EntityKind.SPORT)
    assert len(events) == 1
    assert events[0].payload["created"] is True


@pytest.mark.asyncio
async def test_reconcile_country_idempotent_by_code(service, session):
    first, created1 = await service.reconcile_country(ProviderCountryRecord(code="GB", name="UK"), T0)
    await session.commit()
    second, created2 = await service.reconcile_country(ProviderCountryRecord(code="GB", name="United Kingdom"), T0)
    await session.commit()

    assert created1 and not created2
    assert first.id == second.id
    assert second.name == "United Kingdom"
    assert second.version == 2


@pytest.mark.asyncio
async def test_reconcile_venue_by_synthetic_ref(service, session):
    first, created1 = await service.reconcile_venue("Emirates Stadium", "mock_football", T0)
    await session.commit()
    second, created2 = await service.reconcile_venue("Emirates Stadium", "mock_football", T0 + timedelta(days=1))
    await session.commit()

    assert created1 and not created2
    assert first.id == second.id
    assert second.version == 2


@pytest.mark.asyncio
async def test_reconcile_competition_and_kg_link(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()

    competition, created = await service.reconcile_competition("39", "mock_football", sport.id, T0, name="Premier League")
    await session.commit()

    assert created
    assert competition.name == "Premier League"

    kg_node = await service.kg.nodes.get_by_entity_ref(NodeType.COMPETITION, str(competition.id.value))
    assert kg_node is not None


@pytest.mark.asyncio
async def test_reconcile_team_merges_provider_refs_on_repeat_sync(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()

    first, created1 = await service.reconcile_team(_team_record(), sport.id, T0)
    await session.commit()
    second, created2 = await service.reconcile_team(_team_record(name="Arsenal FC"), sport.id, T0 + timedelta(days=1))
    await session.commit()

    assert created1 and not created2
    assert first.id == second.id
    assert second.name == "Arsenal FC"
    assert second.version == 2
    assert len(second.provider_refs) == 1  # same ref re-seen, not duplicated


@pytest.mark.asyncio
async def test_reconcile_player_resolves_team_id(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    team, _ = await service.reconcile_team(_team_record(), sport.id, T0)
    await session.commit()

    player_record = ProviderPlayerRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="p1"),
        team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        name="Alex Carter", date_of_birth=datetime(1998, 1, 1, tzinfo=timezone.utc), position="forward",
    )
    player, created = await service.reconcile_player(player_record, sport.id, T0)
    await session.commit()

    assert created
    assert player.team_id == team.id


@pytest.mark.asyncio
async def test_reconcile_fixture_raises_when_teams_unresolved(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    season, _ = await service.reconcile_season("39", "2026", "mock_football", (await service.reconcile_competition("39", "mock_football", sport.id, T0))[0].id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )

    with pytest.raises(ReconciliationDependencyError):
        await service.reconcile_fixture(fixture_record, season.id, T0)


@pytest.mark.asyncio
async def test_reconcile_fixture_end_to_end_creates_and_updates(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    fixture, created = await service.reconcile_fixture(fixture_record, season.id, T0)
    await session.commit()

    assert created
    assert fixture.home_team_id == home.id
    assert fixture.away_team_id == away.id

    events = await service.timeline.list_recent(entity_kind=EntityKind.FIXTURE)
    assert events[0].event_type is TimelineEventType.FIXTURE_CREATED

    updated_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0 + timedelta(hours=1), competition_ref="39", season_label="2026",
    )
    updated, created2 = await service.reconcile_fixture(updated_record, season.id, T0 + timedelta(days=1))
    await session.commit()

    assert not created2
    assert updated.id == fixture.id
    assert updated.version == 2

    events2 = await service.timeline.list_recent(entity_kind=EntityKind.FIXTURE, limit=10)
    assert any(e.event_type is TimelineEventType.FIXTURE_UPDATED for e in events2)


@pytest.mark.asyncio
async def test_reconcile_fixture_default_does_not_cross_provider_match(service, session):
    """Regression proof: match_by_teams_and_date defaults to False, so a second provider's
    fixture record for the same real-world match creates a duplicate fixture rather than being
    silently merged — the existing api-football-only sync_fixtures path must behave exactly as
    it did before this option existed."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    original_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    original, _ = await service.reconcile_fixture(original_record, season.id, T0)
    await session.commit()

    # Pre-seed the second-provider team refs pointing at the SAME teams (simulating a confirmed
    # cross-provider team mapping) so only the fixture-identity behavior is under test.
    await service.ref_index.upsert(ProviderRefIndexEntry("football_data_org", "fd-t1", EntityKind.TEAM, str(home.id.value)))
    await service.ref_index.upsert(ProviderRefIndexEntry("football_data_org", "fd-t2", EntityKind.TEAM, str(away.id.value)))
    await session.commit()

    second_provider_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="football_data_org", external_id="fd-fx1"),
        home_team_ref=ProviderRef(provider="football_data_org", external_id="fd-t1"),
        away_team_ref=ProviderRef(provider="football_data_org", external_id="fd-t2"),
        scheduled_at=T0, competition_ref="2021", season_label="2026",
    )
    duplicate, created = await service.reconcile_fixture(second_provider_record, season.id, T0)
    await session.commit()

    assert created
    assert duplicate.id != original.id


@pytest.mark.asyncio
async def test_reconcile_fixture_match_by_teams_and_date_updates_existing_fixture(service, session):
    """The football-data.org upcoming-fixture sync path's opt-in: a second provider's own
    external fixture id never matches the first provider's, so this recognizes "same real-world
    match" by (home team, away team, kickoff within a day) instead of creating a duplicate."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    original_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    original, _ = await service.reconcile_fixture(original_record, season.id, T0)
    await session.commit()

    await service.ref_index.upsert(ProviderRefIndexEntry("football_data_org", "fd-t1", EntityKind.TEAM, str(home.id.value)))
    await service.ref_index.upsert(ProviderRefIndexEntry("football_data_org", "fd-t2", EntityKind.TEAM, str(away.id.value)))
    await session.commit()

    # Same match, reported a few hours later than the first provider's timestamp — still within
    # the +/-1 day window this fallback matches on.
    second_provider_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="football_data_org", external_id="fd-fx1"),
        home_team_ref=ProviderRef(provider="football_data_org", external_id="fd-t1"),
        away_team_ref=ProviderRef(provider="football_data_org", external_id="fd-t2"),
        scheduled_at=T0 + timedelta(hours=3), competition_ref="2021", season_label="2026",
    )
    matched, created = await service.reconcile_fixture(
        second_provider_record, season.id, T0, match_by_teams_and_date=True
    )
    await session.commit()

    assert not created
    assert matched.id == original.id
    assert matched.version == 2


@pytest.mark.asyncio
async def test_reconcile_fixture_match_by_teams_and_date_creates_new_when_no_candidate(service, session):
    """No existing fixture within the date window -> safe default of creating a new one, not
    guessing at a match that isn't there."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    await service.ref_index.upsert(ProviderRefIndexEntry("football_data_org", "fd-t1", EntityKind.TEAM, str(home.id.value)))
    await service.ref_index.upsert(ProviderRefIndexEntry("football_data_org", "fd-t2", EntityKind.TEAM, str(away.id.value)))
    await session.commit()

    record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="football_data_org", external_id="fd-fx1"),
        home_team_ref=ProviderRef(provider="football_data_org", external_id="fd-t1"),
        away_team_ref=ProviderRef(provider="football_data_org", external_id="fd-t2"),
        scheduled_at=T0, competition_ref="2021", season_label="2026",
    )
    fixture, created = await service.reconcile_fixture(record, season.id, T0, match_by_teams_and_date=True)

    assert created
    assert fixture is not None


@pytest.mark.asyncio
async def test_reconcile_fixture_applies_real_status_transitions(service, session):
    """Previously reconcile_fixture always froze at existing.status forever, no matter what the
    provider reported — so sync_live_fixtures' 30s poll never actually moved a fixture past
    SCHEDULED. This proves a fixture now genuinely progresses scheduled -> live -> completed as
    the provider's raw status code changes across syncs."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    def record(status):
        return ProviderFixtureRecord(
            external_ref=ProviderRef(provider="mock_football", external_id="fx-status"),
            home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
            scheduled_at=T0, competition_ref="39", season_label="2026", status=status,
        )

    scheduled, _ = await service.reconcile_fixture(record("NS"), season.id, T0)
    await session.commit()
    assert scheduled.status is FixtureStatus.SCHEDULED

    live, _ = await service.reconcile_fixture(record("1H"), season.id, T0)
    await session.commit()
    assert live.status is FixtureStatus.LIVE

    completed, _ = await service.reconcile_fixture(record("FT"), season.id, T0)
    await session.commit()
    assert completed.status is FixtureStatus.COMPLETED


@pytest.mark.asyncio
async def test_reconcile_fixture_ignores_illegal_status_regression(service, session):
    """A flaky/delayed provider response reporting a completed match as 'not started' again must
    not corrupt the fixture back to SCHEDULED — reconcile_fixture should keep the current status
    rather than let a bad record silently rewrite match history."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    def record(status):
        return ProviderFixtureRecord(
            external_ref=ProviderRef(provider="mock_football", external_id="fx-regress"),
            home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
            scheduled_at=T0, competition_ref="39", season_label="2026", status=status,
        )

    await service.reconcile_fixture(record("1H"), season.id, T0)
    await session.commit()
    completed, _ = await service.reconcile_fixture(record("FT"), season.id, T0)
    await session.commit()
    assert completed.status is FixtureStatus.COMPLETED

    regressed, _ = await service.reconcile_fixture(record("NS"), season.id, T0)
    await session.commit()
    assert regressed.status is FixtureStatus.COMPLETED


@pytest.mark.asyncio
async def test_reconcile_fixture_rejects_scheduled_to_completed_by_default(service, session):
    """A provider that reports IN_PLAY (the normal case) must still be forced through LIVE
    before COMPLETED — allow_skip_live defaults to False, so a SCHEDULED->FINISHED jump with no
    intervening live report is treated as illegal, same as any other skipped transition."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    def record(status):
        return ProviderFixtureRecord(
            external_ref=ProviderRef(provider="mock_football", external_id="fx-skip"),
            home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
            scheduled_at=T0, competition_ref="39", season_label="2026", status=status,
        )

    await service.reconcile_fixture(record("NS"), season.id, T0)
    await session.commit()
    unchanged, _ = await service.reconcile_fixture(record("FT"), season.id, T0)
    await session.commit()

    assert unchanged.status is FixtureStatus.SCHEDULED


@pytest.mark.asyncio
async def test_reconcile_fixture_allow_skip_live_permits_scheduled_to_completed(service, session):
    """football-data.org's free-tier adapter never reports IN_PLAY — its fixtures go straight
    from SCHEDULED to FINISHED. allow_skip_live=True is the one narrow, explicit exception to the
    "never SCHEDULED->COMPLETED directly" rule that makes that legitimate report land, rather than
    a real finished match sitting stuck at SCHEDULED forever."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    def record(status):
        return ProviderFixtureRecord(
            external_ref=ProviderRef(provider="mock_football", external_id="fx-skip-allowed"),
            home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
            scheduled_at=T0, competition_ref="39", season_label="2026", status=status,
            home_score=2, away_score=1,
        )

    await service.reconcile_fixture(record("NS"), season.id, T0)
    await session.commit()
    completed, _ = await service.reconcile_fixture(record("FT"), season.id, T0, allow_skip_live=True)
    await session.commit()

    assert completed.status is FixtureStatus.COMPLETED
    assert completed.home_score == 2
    assert completed.away_score == 1


@pytest.mark.asyncio
async def test_reconcile_fixture_notifies_watchers_on_kickoff_and_final_result(service_with_alerts, session):
    """End-to-end proof that a real Watchlist follow + a real fixture status transition produces
    a real, persisted AlertEvent — not just that the pieces work in isolation."""
    service, alerts = service_with_alerts
    watchlist = SqlAlchemyWatchlistRepository(session=session)
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away_team, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    def record(status):
        return ProviderFixtureRecord(
            external_ref=ProviderRef(provider="mock_football", external_id="fx-alert"),
            home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
            scheduled_at=T0, competition_ref="39", season_label="2026", status=status,
        )

    scheduled, _ = await service.reconcile_fixture(record("NS"), season.id, T0)
    await session.commit()

    fixture_watcher = UserId(uuid4())
    team_watcher = UserId(uuid4())
    await watchlist.add(
        WatchlistEntry(
            id=WatchlistEntryId(uuid4()), user_id=fixture_watcher, entity_type=WatchlistEntityType.FIXTURE,
            entity_ref=str(scheduled.id.value), created_at=T0,
        )
    )
    await watchlist.add(
        WatchlistEntry(
            id=WatchlistEntryId(uuid4()), user_id=team_watcher, entity_type=WatchlistEntityType.TEAM,
            entity_ref=str(away_team.id.value), created_at=T0,
        )
    )
    await session.commit()

    await service.reconcile_fixture(record("1H"), season.id, T0 + timedelta(hours=1))
    await session.commit()

    fixture_watcher_alerts = await alerts.list_for_user(fixture_watcher)
    team_watcher_alerts = await alerts.list_for_user(team_watcher)
    assert len(fixture_watcher_alerts) == 1
    assert fixture_watcher_alerts[0].alert_type is AlertType.KICKOFF
    assert len(team_watcher_alerts) == 1
    assert team_watcher_alerts[0].alert_type is AlertType.KICKOFF

    await service.reconcile_fixture(record("FT"), season.id, T0 + timedelta(hours=3))
    await session.commit()

    all_fixture_alerts = await alerts.list_for_user(fixture_watcher)
    assert len(all_fixture_alerts) == 2
    assert {a.alert_type for a in all_fixture_alerts} == {AlertType.KICKOFF, AlertType.FINAL_RESULT}
    assert all_fixture_alerts[0].alert_type is AlertType.FINAL_RESULT  # most recent first


@pytest.mark.asyncio
async def test_get_or_create_match_creates_once_then_returns_same_row(service, session):
    fixture_id = FixtureId(uuid4())

    first = await service.get_or_create_match(fixture_id, T0)
    await session.commit()
    second = await service.get_or_create_match(fixture_id, T0 + timedelta(hours=1))
    await session.commit()

    assert first.id == second.id
    assert first.fixture_id == fixture_id


@pytest.mark.asyncio
async def test_reconcile_team_statistics_requires_reconciled_team(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()

    record = ProviderTeamStatisticsRecord(
        fixture_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        stat_set={"possession_pct": 55.0},
    )
    with pytest.raises(ReconciliationDependencyError):
        await service.reconcile_team_statistics(record, MatchId(uuid4()), T0)


@pytest.mark.asyncio
async def test_reconcile_team_statistics_succeeds_after_team_reconciled(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    team, _ = await service.reconcile_team(_team_record(), sport.id, T0)
    await session.commit()

    match_id = MatchId(uuid4())
    record = ProviderTeamStatisticsRecord(
        fixture_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        stat_set={"possession_pct": 55.0},
    )
    stats, created = await service.reconcile_team_statistics(record, match_id, T0)
    await session.commit()

    assert created
    assert stats.team_id == team.id
    assert stats.stat_set["possession_pct"] == pytest.approx(55.0)


@pytest.mark.asyncio
async def test_reconcile_lineup_skips_unresolved_players(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    team, _ = await service.reconcile_team(_team_record(), sport.id, T0)
    await session.commit()
    player, _ = await service.reconcile_player(
        ProviderPlayerRecord(
            external_ref=ProviderRef(provider="mock_football", external_id="p1"),
            team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            name="Alex Carter", date_of_birth=None, position="forward",
        ),
        sport.id, T0,
    )
    await session.commit()

    match_id = MatchId(uuid4())
    lineup_record = ProviderLineupRecord(
        fixture_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        formation="4-3-3",
        slots=(
            ProviderLineupSlotRecord(player_ref=ProviderRef(provider="mock_football", external_id="p1"), role="starter"),
            ProviderLineupSlotRecord(player_ref=ProviderRef(provider="mock_football", external_id="p999"), role="starter"),
        ),
    )
    lineup, created, unresolved = await service.reconcile_lineup(lineup_record, match_id, T0)
    await session.commit()

    assert created
    assert len(lineup.slots) == 1
    assert lineup.slots[0].player_id == player.id
    assert unresolved == ["p999"]


@pytest.mark.asyncio
async def test_reconcile_standing_creates_new_snapshot_each_call(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    team, _ = await service.reconcile_team(_team_record(), sport.id, T0)
    await session.commit()

    season_id = SeasonId(uuid4())
    record = ProviderStandingRecord(
        team_ref=ProviderRef(provider="mock_football", external_id="t1"), rank=1, points=45.0, record={"won": 14}
    )
    first = await service.reconcile_standing(record, season_id, T0)
    second = await service.reconcile_standing(record, season_id, T0 + timedelta(days=7))
    await session.commit()

    assert first.id != second.id  # two distinct snapshots, not an in-place update
    all_standings = await service.standings.list_by_season(season_id)
    assert len(all_standings) == 2


@pytest.mark.asyncio
async def test_reconcile_standing_requires_reconciled_team(service, session):
    record = ProviderStandingRecord(
        team_ref=ProviderRef(provider="mock_football", external_id="unknown"), rank=1, points=45.0, record={}
    )
    with pytest.raises(ReconciliationDependencyError):
        await service.reconcile_standing(record, SeasonId(uuid4()), T0)


@pytest.mark.asyncio
async def test_reconcile_fixture_resolves_prediction_outcomes_on_completion_with_score(
    service_with_outcome_resolver, session,
):
    """The audit-identified missing link: a fixture reaching COMPLETED with a real final score
    must trigger prediction-outcome resolution — this was previously never wired anywhere."""
    service, resolver = service_with_outcome_resolver
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    def record(status, home_score=None, away_score=None):
        return ProviderFixtureRecord(
            external_ref=ProviderRef(provider="mock_football", external_id="fx-outcome"),
            home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
            scheduled_at=T0, competition_ref="39", season_label="2026", status=status,
            home_score=home_score, away_score=away_score,
        )

    await service.reconcile_fixture(record("1H"), season.id, T0)
    await session.commit()
    assert resolver.calls == []  # not completed yet

    completed, _ = await service.reconcile_fixture(record("FT", home_score=2, away_score=1), season.id, T0)
    await session.commit()

    assert len(resolver.calls) == 1
    fixture_id, home_score, away_score, now = resolver.calls[0]
    assert fixture_id == str(completed.id.value)
    assert home_score == 2
    assert away_score == 1
    assert now == T0


@pytest.mark.asyncio
async def test_reconcile_fixture_does_not_resolve_outcomes_without_a_final_score(
    service_with_outcome_resolver, session,
):
    """A provider can (rarely) report FT with no score attached yet — resolving outcomes with a
    fabricated 0-0 would be worse than not resolving at all."""
    service, resolver = service_with_outcome_resolver
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-no-score"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026", status="FT",
    )
    await service.reconcile_fixture(record, season.id, T0)
    await session.commit()

    assert resolver.calls == []


@pytest.mark.asyncio
async def test_reconcile_fixture_computes_form_differential_when_sport_code_matches_a_calculator(
    service_with_form_differential, session,
):
    """The audit-identified missing link: a fixture-keyed feature calculator exists
    (`FixtureFormDifferentialCalculator`) but was never invoked from reconciliation — now it
    must run on every reconcile_fixture call, not just on completion, since pre-match form is
    exactly what a prediction needs before kickoff."""
    service, calculator = service_with_form_differential
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-diff"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    fixture, _ = await service.reconcile_fixture(fixture_record, season.id, T0, sport_code="football")
    await session.commit()

    assert len(calculator.calls) == 1
    fixture_id, home_team_id, away_team_id, now = calculator.calls[0]
    assert fixture_id == str(fixture.id.value)
    assert home_team_id == home.id
    assert away_team_id == away.id
    assert now == T0


@pytest.mark.asyncio
async def test_reconcile_fixture_computes_every_registered_calculator_for_a_sport(session):
    """2026-08-03: `form_differential_calculators` moved from one calculator per sport to a tuple,
    so football's newly-added possession/shots_total/corners/fouls/cards differentials all
    actually run alongside shots_on_target on every reconciliation, not just the first one
    registered."""
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    calculator_one = _RecordingFormDifferentialCalculator()
    calculator_two = _RecordingFormDifferentialCalculator()
    service = EntityReconciliationService(
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
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        form_differential_calculators={"football": (calculator_one, calculator_two)},
    )
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-multi-diff"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    await service.reconcile_fixture(fixture_record, season.id, T0, sport_code="football")
    await session.commit()

    assert len(calculator_one.calls) == 1
    assert len(calculator_two.calls) == 1


@pytest.mark.asyncio
async def test_reconcile_fixture_skips_form_differential_without_sport_code(
    service_with_form_differential, session,
):
    """A caller that doesn't pass sport_code (e.g. an older call site) must not crash — it just
    silently opts out of the differential computation."""
    service, calculator = service_with_form_differential
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-no-sport"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    await service.reconcile_fixture(fixture_record, season.id, T0)
    await session.commit()

    assert calculator.calls == []


@pytest.mark.asyncio
async def test_reconcile_fixture_skips_form_differential_for_unregistered_sport(
    service_with_form_differential, session,
):
    """A sport with no registered calculator (e.g. basketball, before it gets one) must not
    raise — reconciliation for that sport keeps working exactly as before this feature existed."""
    service, calculator = service_with_form_differential
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-other-sport"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    await service.reconcile_fixture(fixture_record, season.id, T0, sport_code="basketball")
    await session.commit()

    assert calculator.calls == []
