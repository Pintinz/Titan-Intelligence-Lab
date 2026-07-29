from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.ingestion.application.entity_reconciliation_service import (
    EntityReconciliationService,
    ReconciliationDependencyError,
)
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
from modules.sports.domain.value_objects import MatchId, ProviderRef, SeasonId, SportCode
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

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


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
        team_statistics=SqlAlchemyTeamStatisticsRepository(session=session),
        lineups=SqlAlchemyLineupRepository(session=session),
        standings=SqlAlchemyStandingRepository(session=session),
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
    )


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
