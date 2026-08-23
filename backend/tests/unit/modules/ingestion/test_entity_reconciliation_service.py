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
from modules.ingestion.domain.value_objects import EntityKind, SyncTrigger, TimelineEventType
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
from modules.sports.ports.provider_gateway import (
    ProviderCoachRecord,
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderInjuryRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
    ProviderTransferRecord,
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
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        coaching_staff=SqlAlchemyCoachingStaffRepository(session=session),
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

    async def resolve_for_fixture(
        self, fixture_id, home_score, away_score, now, *,
        home_score_ht=None, away_score_ht=None, home_score_first5=None, away_score_first5=None,
        home_quarters=None, away_quarters=None,
    ):
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
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        coaching_staff=SqlAlchemyCoachingStaffRepository(session=session),
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
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        coaching_staff=SqlAlchemyCoachingStaffRepository(session=session),
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        form_differential_calculators={"football": (calculator,)},
    ), calculator


class _RecordingTeamFormCalculator:
    """Stub standing in for `RollingTeamStatAverageCalculator` — verifies only the *wiring*
    (called for both teams, only on completion with a real score), not its own rolling-average
    computation, which `test_windowed_feature_engineering_service.py` already covers directly."""

    def __init__(self):
        self.calls = []

    async def compute_and_write(self, team_id, now):
        self.calls.append((team_id, now))
        return None


@pytest.fixture
def service_with_team_form(session):
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    calculator = _RecordingTeamFormCalculator()
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
        team_form_calculators={"football": (calculator,)},
    ), calculator


class _RecordingTransferActivityCalculator:
    """Stub standing in for `TransferActivityCalculator` — verifies only the *wiring* (called
    once per side, with the right args), not its own computation, which
    `test_windowed_feature_engineering_service.py` already covers directly."""

    def __init__(self):
        self.calls = []

    async def compute_and_write(self, fixture_id, team_id, now):
        self.calls.append((fixture_id, team_id, now))
        return None


@pytest.fixture
def service_with_transfer_activity(session):
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    home_calculator = _RecordingTransferActivityCalculator()
    away_calculator = _RecordingTransferActivityCalculator()
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
        transfer_activity_calculators={"football": (home_calculator, away_calculator)},
    ), home_calculator, away_calculator


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
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        coaching_staff=SqlAlchemyCoachingStaffRepository(session=session),
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
async def test_reconcile_team_auto_merges_via_cross_provider_ref(service, session):
    """TheSportsDB-class integration: a team record carrying a deterministic cross_provider_ref
    (e.g. TheSportsDB's real idAPIfootball field) merges into the already-reconciled team under
    that other provider, rather than creating a duplicate."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    primary, _ = await service.reconcile_team(_team_record(), sport.id, T0)
    await session.commit()

    supplementary_record = ProviderTeamRecord(
        external_ref=ProviderRef(provider="thesportsdb", external_id="tsdb-1"),
        name="Arsenal", short_name="ARS", country="England",
        cross_provider_ref=ProviderRef(provider="mock_football", external_id="t1"),
    )
    merged, created = await service.reconcile_team(supplementary_record, sport.id, T0)
    await session.commit()

    assert not created
    assert merged.id == primary.id
    assert len(merged.provider_refs) == 2  # both provider refs now point at the same team


@pytest.mark.asyncio
async def test_reconcile_team_cross_provider_ref_falls_back_to_create_when_unresolved(service, session):
    """If the claimed cross-provider team hasn't been reconciled yet, this creates a new team
    like normal rather than raising — the claim just doesn't resolve to anything yet."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()

    record = ProviderTeamRecord(
        external_ref=ProviderRef(provider="thesportsdb", external_id="tsdb-1"),
        name="Arsenal", short_name="ARS", country="England",
        cross_provider_ref=ProviderRef(provider="mock_football", external_id="never-seen"),
    )
    team, created = await service.reconcile_team(record, sport.id, T0)
    await session.commit()

    assert created
    assert team.name == "Arsenal"


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
async def test_reconcile_player_keeps_existing_photo_when_a_later_sync_reports_none(service, session):
    """Matches `reconcile_team`'s `logo_url` fallback: a resync that doesn't report a photo (e.g.
    a provider outage returning a partial record) must never blank out a real one already on file."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    team, _ = await service.reconcile_team(_team_record(), sport.id, T0)
    await session.commit()

    ref = ProviderRef(provider="mock_football", external_id="p1")
    team_ref = ProviderRef(provider="mock_football", external_id="t1")
    first = ProviderPlayerRecord(
        external_ref=ref, team_ref=team_ref, name="Alex Carter",
        date_of_birth=datetime(1998, 1, 1, tzinfo=timezone.utc), position="forward",
        photo_url="https://media.api-sports.io/football/players/1.png",
    )
    player, _ = await service.reconcile_player(first, sport.id, T0)
    await session.commit()
    assert player.photo_url == "https://media.api-sports.io/football/players/1.png"

    second = ProviderPlayerRecord(
        external_ref=ref, team_ref=team_ref, name="Alex Carter",
        date_of_birth=datetime(1998, 1, 1, tzinfo=timezone.utc), position="forward", photo_url=None,
    )
    player, created = await service.reconcile_player(second, sport.id, T0)
    await session.commit()

    assert not created
    assert player.photo_url == "https://media.api-sports.io/football/players/1.png"


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
async def test_reconcile_fixture_preserve_existing_score_does_not_overwrite(service, session):
    """A supplementary (non-authoritative) source's own score must never clobber one an already-
    trusted provider set — the real bug this option exists to prevent for TheSportsDB-class
    integrations."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    authoritative_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
        status="FT", home_score=2, away_score=1,
    )
    original, _ = await service.reconcile_fixture(authoritative_record, season.id, T0)
    await session.commit()
    assert original.home_score == 2
    assert original.away_score == 1

    await service.ref_index.upsert(ProviderRefIndexEntry("thesportsdb", "tsdb-t1", EntityKind.TEAM, str(home.id.value)))
    await service.ref_index.upsert(ProviderRefIndexEntry("thesportsdb", "tsdb-t2", EntityKind.TEAM, str(away.id.value)))
    await session.commit()

    # Same real-world match, but this supplementary source reports a different (wrong) score.
    supplementary_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="thesportsdb", external_id="tsdb-fx1"),
        home_team_ref=ProviderRef(provider="thesportsdb", external_id="tsdb-t1"),
        away_team_ref=ProviderRef(provider="thesportsdb", external_id="tsdb-t2"),
        scheduled_at=T0, competition_ref="4328", season_label="2026",
        status="FT", home_score=9, away_score=9,
    )
    merged, created = await service.reconcile_fixture(
        supplementary_record, season.id, T0, match_by_teams_and_date=True,
        allow_skip_live=True, preserve_existing_score=True,
    )
    await session.commit()

    assert not created
    assert merged.id == original.id
    assert merged.home_score == 2  # untouched, not overwritten with the supplementary source's 9
    assert merged.away_score == 1


@pytest.mark.asyncio
async def test_reconcile_fixture_preserve_existing_score_still_fills_when_absent(service, session):
    """The guard only locks a score that's already present — a genuinely-empty existing score
    still gets filled in from the supplementary source, since there's nothing trusted to protect."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    scheduled_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx1"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026", status="NS",
    )
    original, _ = await service.reconcile_fixture(scheduled_record, season.id, T0)
    await session.commit()
    assert original.home_score is None

    await service.ref_index.upsert(ProviderRefIndexEntry("thesportsdb", "tsdb-t1", EntityKind.TEAM, str(home.id.value)))
    await service.ref_index.upsert(ProviderRefIndexEntry("thesportsdb", "tsdb-t2", EntityKind.TEAM, str(away.id.value)))
    await session.commit()

    supplementary_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="thesportsdb", external_id="tsdb-fx1"),
        home_team_ref=ProviderRef(provider="thesportsdb", external_id="tsdb-t1"),
        away_team_ref=ProviderRef(provider="thesportsdb", external_id="tsdb-t2"),
        scheduled_at=T0, competition_ref="4328", season_label="2026",
        status="FT", home_score=3, away_score=0,
    )
    merged, created = await service.reconcile_fixture(
        supplementary_record, season.id, T0, match_by_teams_and_date=True,
        allow_skip_live=True, preserve_existing_score=True,
    )
    await session.commit()

    assert not created
    assert merged.home_score == 3
    assert merged.away_score == 0


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
async def test_get_or_create_match_sets_started_at_from_the_fixtures_real_scheduled_at(service, session):
    """POST-M24 Phase 5A audit finding: a `Match` created with `started_at=None` is permanently
    invisible to `TeamStatisticsRepositoryPort.list_recent_by_team` (its query joins on
    `Match.started_at < before`, and SQL's NULL comparison is never true) — every rolling-form/
    differential feature calculator for every sport reads through that one method, so this was a
    real, universal bug, not sport-specific. The fixture's own real `scheduled_at` is the correct,
    non-fabricated value to use."""
    sport, _ = await service.reconcile_sport(SportCode.BASKETBALL, "Basketball", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("nba", "api_basketball", sport.id, T0, name="NBA")
    season, _ = await service.reconcile_season("nba", "2026", "api_basketball", competition.id, T0)
    home, _ = await service.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("api_basketball", "h1"), name="Home", short_name="HOM", country=None),
        sport.id, T0,
    )
    away, _ = await service.reconcile_team(
        ProviderTeamRecord(external_ref=ProviderRef("api_basketball", "a1"), name="Away", short_name="AWY", country=None),
        sport.id, T0,
    )
    kickoff = T0 - timedelta(days=3)
    fixture, _ = await service.reconcile_fixture(
        ProviderFixtureRecord(
            external_ref=ProviderRef("api_basketball", "fx1"), home_team_ref=ProviderRef("api_basketball", "h1"),
            away_team_ref=ProviderRef("api_basketball", "a1"), scheduled_at=kickoff, competition_ref="nba",
            season_label="2026",
        ),
        season.id, T0,
    )
    await session.commit()

    match = await service.get_or_create_match(fixture.id, T0)

    assert match.started_at.replace(tzinfo=timezone.utc) == kickoff


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
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        coaching_staff=SqlAlchemyCoachingStaffRepository(session=session),
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


@pytest.mark.asyncio
async def test_reconcile_fixture_recomputes_team_form_for_both_teams_on_completion(
    service_with_team_form, session,
):
    """Premier League data-enrichment audit (2026-08-22): `RollingTeamStatAverageCalculator`
    (a team's own rolling last-N form) had no recurring trigger anywhere in the system before
    this fix. Must fire for BOTH home and away teams once a fixture completes with a real score
    — that's the only moment either team's last-N match list actually changes."""
    service, calculator = service_with_team_form
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-completed"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
        status="FT", home_score=2, away_score=1,
    )
    await service.reconcile_fixture(fixture_record, season.id, T0, sport_code="football")
    await session.commit()

    assert calculator.calls == [(home.id, T0), (away.id, T0)]


@pytest.mark.asyncio
async def test_reconcile_fixture_skips_team_form_when_not_yet_completed(
    service_with_team_form, session,
):
    """A team's rolling form must not be recomputed on every pre-match sync — only once a match
    genuinely finishes with a real score, mirroring `_resolve_prediction_outcomes`'s own gate."""
    service, calculator = service_with_team_form
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-scheduled"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026", status="NS",
    )
    await service.reconcile_fixture(fixture_record, season.id, T0, sport_code="football")
    await session.commit()

    assert calculator.calls == []


@pytest.mark.asyncio
async def test_reconcile_fixture_sets_last_verified_at_to_the_sync_time(session):
    """Premier League data-enrichment audit (2026-08-22): Fixture had no provenance timestamp
    recording when it was last confirmed against a real provider sync. Every reconciliation —
    not just completion — should stamp it, since even a pre-match resync re-verifies the
    fixture's current known state."""
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
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
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        coaching_staff=SqlAlchemyCoachingStaffRepository(session=session),
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
    )
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-provenance"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    fixture, _ = await service.reconcile_fixture(fixture_record, season.id, T0)
    await session.commit()

    assert fixture.last_verified_at == T0


@pytest.mark.asyncio
async def test_reconcile_fixture_computes_transfer_activity_for_both_sides(
    service_with_transfer_activity, session,
):
    """Milestone 7 — the fixture-association and home/away-correctness scenarios: transfer
    activity has no fixture of its own to attach to (unlike lineups), so it must be computed from
    reconcile_fixture directly, once per side, against the correct team_id."""
    service, home_calculator, away_calculator = service_with_transfer_activity
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    home, _ = await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-transfer-activity"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    fixture, _ = await service.reconcile_fixture(fixture_record, season.id, T0, sport_code="football")
    await session.commit()

    assert len(home_calculator.calls) == 1
    home_fixture_id, home_team_id, home_now = home_calculator.calls[0]
    assert home_fixture_id == str(fixture.id.value)
    assert home_team_id == home.id
    assert home_now == T0

    assert len(away_calculator.calls) == 1
    away_fixture_id, away_team_id, away_now = away_calculator.calls[0]
    assert away_fixture_id == str(fixture.id.value)
    assert away_team_id == away.id
    assert away_now == T0


@pytest.mark.asyncio
async def test_reconcile_fixture_skips_transfer_activity_without_sport_code(
    service_with_transfer_activity, session,
):
    """A caller that doesn't pass sport_code must not crash — it just silently opts out, exactly
    like form differential's equivalent test above."""
    service, home_calculator, away_calculator = service_with_transfer_activity
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-transfer-no-sport"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    await service.reconcile_fixture(fixture_record, season.id, T0)
    await session.commit()

    assert home_calculator.calls == []
    assert away_calculator.calls == []


@pytest.mark.asyncio
async def test_reconcile_fixture_skips_transfer_activity_for_unregistered_sport(
    service_with_transfer_activity, session,
):
    """A sport with no registered calculator must not raise."""
    service, home_calculator, away_calculator = service_with_transfer_activity
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0)
    season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()

    fixture_record = ProviderFixtureRecord(
        external_ref=ProviderRef(provider="mock_football", external_id="fx-transfer-other-sport"),
        home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        scheduled_at=T0, competition_ref="39", season_label="2026",
    )
    await service.reconcile_fixture(fixture_record, season.id, T0, sport_code="basketball")
    await session.commit()

    assert home_calculator.calls == []
    assert away_calculator.calls == []


# -- Injury / Transfer / Coaching staff (squad intelligence) --------------------------------


async def _reconciled_player(service, session, team_ref="t1", player_ref="p1"):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    team, _ = await service.reconcile_team(_team_record(team_ref), sport.id, T0)
    await session.commit()
    player, _ = await service.reconcile_player(
        ProviderPlayerRecord(
            external_ref=ProviderRef(provider="mock_football", external_id=player_ref),
            team_ref=ProviderRef(provider="mock_football", external_id=team_ref),
            name="Alex Carter", date_of_birth=datetime(1998, 1, 1, tzinfo=timezone.utc), position="forward",
        ),
        sport.id, T0,
    )
    await session.commit()
    return team, player


@pytest.mark.asyncio
async def test_reconcile_injury_requires_reconciled_player(service):
    record = ProviderInjuryRecord(
        player_ref=ProviderRef(provider="mock_football", external_id="unknown"),
        team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        status="Missing Fixture", reason="Hamstring",
    )
    with pytest.raises(ReconciliationDependencyError):
        await service.reconcile_injury(record, T0)


@pytest.mark.asyncio
async def test_reconcile_injury_updates_same_player_row_in_place(service, session):
    """Re-syncing the same player's injury updates the existing row rather than creating a
    second one — the provider's /injuries endpoint always reports current status, not a log."""
    _, player = await _reconciled_player(service, session)
    record = ProviderInjuryRecord(
        player_ref=ProviderRef(provider="mock_football", external_id="p1"),
        team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        status="Missing Fixture", reason="Hamstring", reported_at=T0,
    )
    first, created = await service.reconcile_injury(record, T0)
    await session.commit()
    assert created
    assert first.reason == "Hamstring"

    updated_record = ProviderInjuryRecord(
        player_ref=ProviderRef(provider="mock_football", external_id="p1"),
        team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        status="Questionable", reason="Knee Injury", reported_at=T0 + timedelta(days=3),
    )
    second, created_again = await service.reconcile_injury(updated_record, T0 + timedelta(days=3))
    await session.commit()

    assert not created_again
    assert second.id == first.id
    assert second.reason == "Knee Injury"
    assert second.status == "Questionable"
    assert second.player_id == player.id

    all_injuries = await service.injuries.list_by_player(player.id)
    assert len(all_injuries) == 1  # updated in place, never duplicated


@pytest.mark.asyncio
async def test_reconcile_injury_never_fabricates_expected_return(service, session):
    await _reconciled_player(service, session)
    record = ProviderInjuryRecord(
        player_ref=ProviderRef(provider="mock_football", external_id="p1"),
        team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        status="Missing Fixture", reason="Illness",
    )
    injury, _ = await service.reconcile_injury(record, T0)
    assert injury.expected_return is None


@pytest.mark.asyncio
async def test_reconcile_transfer_creates_distinct_rows_for_distinct_moves(service, session):
    """Unlike injuries, each real transfer is a genuine historical event — two different moves
    for the same player both persist rather than the second overwriting the first."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
    away_team, _ = await service.reconcile_team(_team_record("t2", "Chelsea"), sport.id, T0)
    await session.commit()
    _, player = await _reconciled_player(service, session, team_ref="t1", player_ref="p1")

    first = ProviderTransferRecord(
        player_ref=ProviderRef(provider="mock_football", external_id="p1"),
        from_team_ref=None, to_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        effective_date=datetime(2020, 7, 1, tzinfo=timezone.utc), transfer_type="Free",
    )
    second = ProviderTransferRecord(
        player_ref=ProviderRef(provider="mock_football", external_id="p1"),
        from_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
        to_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
        effective_date=datetime(2023, 1, 15, tzinfo=timezone.utc), transfer_type="€10M",
    )
    await service.reconcile_transfer(first, T0)
    await session.commit()
    await service.reconcile_transfer(second, T0)
    await session.commit()

    # re-syncing the same first record again must not duplicate it
    await service.reconcile_transfer(first, T0)
    await session.commit()

    transfers = await service.transfers.list_by_player(player.id)
    assert len(transfers) == 2
    assert {t.transfer_type for t in transfers} == {"Free", "€10M"}
    assert away_team.id in {t.to_team_id for t in transfers}


@pytest.mark.asyncio
async def test_reconcile_coaching_staff_closes_previous_when_person_changes(service, session):
    """Time-aware: a new coach closes the previous one's row (valid_to set) instead of
    overwriting it — history is preserved."""
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    team, _ = await service.reconcile_team(_team_record(), sport.id, T0)
    await session.commit()

    first, created = await service.reconcile_coaching_staff(
        ProviderCoachRecord(team_ref=ProviderRef(provider="mock_football", external_id="t1"), person_name="Mikel Arteta"),
        T0,
    )
    await session.commit()
    assert created
    assert first.valid_to is None

    later = T0 + timedelta(days=200)
    second, created_again = await service.reconcile_coaching_staff(
        ProviderCoachRecord(team_ref=ProviderRef(provider="mock_football", external_id="t1"), person_name="New Manager"),
        later,
    )
    await session.commit()
    assert created_again
    assert second.person_name == "New Manager"
    assert second.valid_to is None

    history = await service.coaching_staff.list_by_team(team.id)
    assert len(history) == 2
    closed = next(c for c in history if c.person_name == "Mikel Arteta")
    # SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — compare naive.
    assert closed.valid_to.replace(tzinfo=None) == later.replace(tzinfo=None)  # closed, not deleted/overwritten


@pytest.mark.asyncio
async def test_reconcile_coaching_staff_same_person_is_a_no_op(service, session):
    sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
    await session.commit()
    await service.reconcile_team(_team_record(), sport.id, T0)
    await session.commit()

    record = ProviderCoachRecord(team_ref=ProviderRef(provider="mock_football", external_id="t1"), person_name="Mikel Arteta")
    first, created = await service.reconcile_coaching_staff(record, T0)
    await session.commit()
    second, created_again = await service.reconcile_coaching_staff(record, T0 + timedelta(days=30))
    await session.commit()

    assert created
    assert not created_again


class TestVerifiedPreMatchAvailabilityIntegration:
    """Milestone 5 (Verified Pre-Match Data Availability) — integration proof that
    `reconcile_lineup`/`reconcile_injury`/`reconcile_transfer` actually route through
    `classify_availability` end-to-end (modules.ingestion.application.provenance), not just that
    the pure function itself is correct (see test_availability_classification.py's unit-level
    A-K coverage). Scenarios A/B/F/G/H/I re-verified here against the real reconciliation call
    path, against a real SQLite session."""

    @pytest.mark.asyncio
    async def test_lineup_reconciled_via_live_scheduled_within_window_is_verified_pre_match(self, service, session):
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
        kickoff = T0 + timedelta(minutes=60)
        record = ProviderLineupRecord(
            fixture_ref=ProviderRef(provider="mock_football", external_id="fx1"),
            team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            formation="4-3-3",
            slots=(ProviderLineupSlotRecord(player_ref=ProviderRef(provider="mock_football", external_id="p1"), role="starter"),),
        )
        lineup, _, _ = await service.reconcile_lineup(
            record, match_id, T0, trigger=SyncTrigger.LIVE_SCHEDULED, kickoff=kickoff,
        )
        await session.commit()

        assert lineup.availability_classification == "VERIFIED_PRE_MATCH"
        assert lineup.information_available_at == T0
        assert lineup.fetched_at == T0
        assert player.id == lineup.slots[0].player_id

    @pytest.mark.asyncio
    async def test_lineup_reconciled_via_admin_manual_is_unknown_availability(self, service, session):
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        await session.commit()
        await service.reconcile_team(_team_record(), sport.id, T0)
        await session.commit()

        match_id = MatchId(uuid4())
        kickoff = T0 + timedelta(minutes=60)
        record = ProviderLineupRecord(
            fixture_ref=ProviderRef(provider="mock_football", external_id="fx1"),
            team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            formation="4-3-3", slots=(),
        )
        lineup, _, _ = await service.reconcile_lineup(
            record, match_id, T0, trigger=SyncTrigger.ADMIN_MANUAL, kickoff=kickoff,
        )
        await session.commit()

        assert lineup.availability_classification == "UNKNOWN_AVAILABILITY_TIME"
        assert lineup.information_available_at is None

    @pytest.mark.asyncio
    async def test_injury_reconciled_via_live_scheduled_still_stays_unknown(self, service, session):
        """Proves the real call path never lets an injury reach VERIFIED_PRE_MATCH today, even
        under the one trigger that would otherwise qualify — because no adapter yet supplies a
        genuine report timestamp (reconcile_injury hardcodes has_genuine_timestamp=False)."""
        await _reconciled_player(service, session)
        record = ProviderInjuryRecord(
            player_ref=ProviderRef(provider="mock_football", external_id="p1"),
            team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            status="Missing Fixture", reason="Hamstring",
        )
        injury, _ = await service.reconcile_injury(record, T0, trigger=SyncTrigger.LIVE_SCHEDULED)
        await session.commit()

        assert injury.availability_classification == "UNKNOWN_AVAILABILITY_TIME"
        assert injury.information_available_at is None
        assert injury.fetched_at == T0

    @pytest.mark.asyncio
    async def test_transfer_reconciled_via_live_scheduled_is_verified_pre_match(self, service, session):
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        await session.commit()
        await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
        await session.commit()
        _, player = await _reconciled_player(service, session, team_ref="t1", player_ref="p1")

        record = ProviderTransferRecord(
            player_ref=ProviderRef(provider="mock_football", external_id="p1"),
            from_team_ref=None, to_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            effective_date=datetime(2026, 9, 1, tzinfo=timezone.utc), transfer_type="Free",
        )
        transfer = await service.reconcile_transfer(record, T0, trigger=SyncTrigger.LIVE_SCHEDULED)
        await session.commit()

        assert transfer.availability_classification == "VERIFIED_PRE_MATCH"
        assert transfer.information_available_at == T0

    @pytest.mark.asyncio
    async def test_transfer_reconciled_via_admin_manual_stays_unknown(self, service, session):
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        await session.commit()
        await service.reconcile_team(_team_record("t1", "Arsenal"), sport.id, T0)
        await session.commit()
        await _reconciled_player(service, session, team_ref="t1", player_ref="p1")

        record = ProviderTransferRecord(
            player_ref=ProviderRef(provider="mock_football", external_id="p1"),
            from_team_ref=None, to_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            effective_date=datetime(2026, 9, 1, tzinfo=timezone.utc), transfer_type="Free",
        )
        transfer = await service.reconcile_transfer(record, T0, trigger=SyncTrigger.ADMIN_MANUAL)
        await session.commit()

        assert transfer.availability_classification == "UNKNOWN_AVAILABILITY_TIME"

    @pytest.mark.asyncio
    async def test_reconciliation_defaults_never_accidentally_verify(self, service, session):
        """A caller that doesn't pass trigger/kickoff at all (every pre-Milestone-5 test and
        script) must get exactly the same UNKNOWN_AVAILABILITY_TIME result as before this
        milestone — the new parameters are additive, never a silent behavior change for existing
        callers."""
        await _reconciled_player(service, session)
        record = ProviderInjuryRecord(
            player_ref=ProviderRef(provider="mock_football", external_id="p1"),
            team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            status="Missing Fixture", reason="Hamstring",
        )
        injury, _ = await service.reconcile_injury(record, T0)
        await session.commit()

        assert injury.availability_classification == "UNKNOWN_AVAILABILITY_TIME"


class TestProviderRefIndexCanonicalEntityId:
    """Milestone 4 item 1: "Add tests proving: provider reference -> canonical entity ->
    fixture/team/player resolves correctly." Exercises the real round trip through
    `SqlAlchemyProviderRefIndexRepository`/`_canonical_entity_id`
    (modules/ingestion/infrastructure/persistence/mappers.py) against a real SQLite session —
    not a fake/in-memory repo — so both the write-time normalization and the read-time lookup
    are proven against actual storage, not just the mapper function in isolation."""

    @staticmethod
    async def _raw_stored_entity_id(session: AsyncSession, provider: str, external_id: str, entity_kind: EntityKind) -> str:
        from sqlalchemy import select as sa_select

        from modules.ingestion.infrastructure.persistence.models import ProviderRefIndexModel

        stmt = sa_select(ProviderRefIndexModel.entity_id).where(
            ProviderRefIndexModel.provider == provider,
            ProviderRefIndexModel.external_id == external_id,
            ProviderRefIndexModel.entity_kind == entity_kind.value,
        )
        return (await session.execute(stmt)).scalar_one()

    @pytest.mark.asyncio
    async def test_team_provider_ref_resolves_to_canonical_hyphenated_team_id(self, service, session):
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        await session.commit()
        team, _ = await service.reconcile_team(_team_record(), sport.id, T0)
        await session.commit()

        stored = await self._raw_stored_entity_id(session, "mock_football", "t1", EntityKind.TEAM)
        assert stored == str(team.id.value)  # canonical hyphenated form, matching Team.id itself

        resolved = await service.ref_index.get("mock_football", "t1", EntityKind.TEAM)
        assert resolved == str(team.id.value)

        looked_up = await service.teams.get(team.id)
        assert looked_up is not None
        assert looked_up.id == team.id
        assert looked_up.name == team.name

    @pytest.mark.asyncio
    async def test_player_provider_ref_resolves_to_canonical_player_id(self, service, session):
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        await session.commit()
        await service.reconcile_team(_team_record(), sport.id, T0)
        await session.commit()
        player, _ = await service.reconcile_player(
            ProviderPlayerRecord(
                external_ref=ProviderRef(provider="mock_football", external_id="p1"),
                team_ref=ProviderRef(provider="mock_football", external_id="t1"),
                name="Bukayo Saka", date_of_birth=None, position="FW",
            ),
            sport.id, T0,
        )
        await session.commit()

        stored = await self._raw_stored_entity_id(session, "mock_football", "p1", EntityKind.PLAYER)
        assert stored == str(player.id.value)

        from modules.sports.domain.value_objects import PlayerId

        looked_up = await service.players.get(PlayerId(_as_uuid_for_test(stored)))
        assert looked_up is not None
        assert looked_up.id == player.id

    @pytest.mark.asyncio
    async def test_fixture_provider_ref_resolves_through_team_refs_to_real_fixture(self, service, session):
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        await session.commit()
        home, _ = await service.reconcile_team(_team_record(external_id="t1", name="Arsenal"), sport.id, T0)
        away, _ = await service.reconcile_team(_team_record(external_id="t2", name="Chelsea"), sport.id, T0)
        await session.commit()
        competition, _ = await service.reconcile_competition("39", "mock_football", sport.id, T0, name="Premier League")
        season, _ = await service.reconcile_season("39", "2026", "mock_football", competition.id, T0)
        await session.commit()

        record = ProviderFixtureRecord(
            external_ref=ProviderRef(provider="mock_football", external_id="f1"),
            home_team_ref=ProviderRef(provider="mock_football", external_id="t1"),
            away_team_ref=ProviderRef(provider="mock_football", external_id="t2"),
            scheduled_at=T0, competition_ref="39", season_label="2026", status="SCHEDULED",
        )
        fixture, _ = await service.reconcile_fixture(record, season.id, T0)
        await session.commit()

        stored = await self._raw_stored_entity_id(session, "mock_football", "f1", EntityKind.FIXTURE)
        assert stored == str(fixture.id.value)

        looked_up = await service.fixtures.get(fixture.id)
        assert looked_up is not None
        assert looked_up.home_team_id == home.id
        assert looked_up.away_team_id == away.id

    @pytest.mark.asyncio
    async def test_pre_fix_hex_stored_entity_id_still_resolves_correctly(self, service, session):
        """Rows written before the mapper's canonicalization fix (or by any external
        script) may still be stored in raw hex-no-hyphen form. `uuid.UUID()` parsing is
        hyphen-agnostic, so lookups through the real reconciliation/repository path must
        resolve identically regardless of which form is on disk — proving the read path
        does not depend on the write-time fix having already normalized every row."""
        sport, _ = await service.reconcile_sport(SportCode.FOOTBALL, "Football", T0)
        await session.commit()
        team, _ = await service.reconcile_team(_team_record(), sport.id, T0)
        await session.commit()

        from modules.ingestion.infrastructure.persistence.models import ProviderRefIndexModel

        model = ProviderRefIndexModel(
            provider="legacy_provider", external_id="legacy-1", entity_kind=EntityKind.TEAM.value,
            entity_id=str(team.id.value).replace("-", ""),
        )
        session.add(model)
        await session.commit()

        resolved = await service.ref_index.get("legacy_provider", "legacy-1", EntityKind.TEAM)
        assert resolved == str(team.id.value)  # mapper normalizes hex back to canonical on read

        looked_up = await service.teams.get(team.id)
        assert looked_up is not None
        assert looked_up.id == team.id


def _as_uuid_for_test(value: str):
    from uuid import UUID

    return UUID(value)
    assert second.id == first.id
