from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.intelligence.application.historical_entity_resolution_service import (
    HistoricalEntityResolutionService,
)
from modules.intelligence.application.historical_news_relevance_engine import (
    HistoricalFixtureContext,
    HistoricalNewsRelevanceEngine,
)
from modules.intelligence.domain.entities import NewsEvent, ResolvedNewsEntity
from modules.intelligence.domain.value_objects import (
    EntityResolutionStatus,
    NewsArticleId,
    NewsEventConfidenceTier,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
)
from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.predictions.application.historical_feature_reconstruction_service import (
    HistoricalFeatureReconstructionService,
    NewsFeatureEligibility,
)
from modules.predictions.application.news_market_impact_engine import NewsMarketImpactEngine
from modules.predictions.application.news_market_impact_registry import MARKET_IMPACT_RULES
from modules.sports.domain.entities import Player, Transfer
from modules.sports.domain.value_objects import EntityId, FixtureId, PlayerId, SportId, TeamId
from tests.unit.modules.features.conftest import (
    InMemoryFeatureDefinitionRepository,
    InMemoryFeatureLineageRepository,
    InMemoryFeatureValueRepository,
    InMemoryFeatureVersionRepository,
    InMemoryOnlineFeatureStore,
)

T0 = datetime(2024, 3, 1, tzinfo=timezone.utc)
KICKOFF = datetime(2024, 3, 2, tzinfo=timezone.utc)
HOME_TEAM = TeamId(uuid4())
AWAY_TEAM = TeamId(uuid4())
UNRELATED_TEAM = TeamId(uuid4())


@dataclass
class InMemoryNewsEventRepository:
    store: dict = field(default_factory=dict)

    def add(self, entity_ref: str, event: NewsEvent) -> None:
        self.store.setdefault(entity_ref, []).append(event)

    async def list_for_entity(self, entity_ref: str):
        return list(self.store.get(entity_ref, []))


@dataclass
class InMemoryKGNodeRepository:
    by_id: dict = field(default_factory=dict)
    by_ref: dict = field(default_factory=dict)

    def add(self, node: KGNode) -> None:
        self.by_id[node.id] = node
        self.by_ref[(node.node_type, node.entity_ref)] = node

    async def get(self, node_id):
        return self.by_id.get(node_id)

    async def get_by_entity_ref(self, node_type, entity_ref: str):
        return self.by_ref.get((node_type, entity_ref))


@dataclass
class InMemoryPlayerRepository:
    by_team: dict = field(default_factory=dict)
    by_id: dict = field(default_factory=dict)

    def add(self, team_id: TeamId, player: Player) -> None:
        self.by_team.setdefault(team_id, []).append(player)
        self.by_id[player.id] = player

    async def list_by_team(self, team_id: TeamId):
        return list(self.by_team.get(team_id, []))

    async def get(self, player_id: PlayerId):
        return self.by_id.get(player_id)


@dataclass
class InMemoryTransferRepository:
    transfers: list = field(default_factory=list)

    def add(self, transfer: Transfer) -> None:
        self.transfers.append(transfer)

    async def list_by_player(self, player_id: PlayerId):
        return [t for t in self.transfers if t.player_id == player_id]

    async def list_by_team(self, team_id: TeamId):
        return [t for t in self.transfers if t.from_team_id == team_id or t.to_team_id == team_id]

    async def get(self, transfer_id):
        return None

    async def upsert(self, transfer):
        return transfer


def _fixture_context(kickoff=KICKOFF) -> HistoricalFixtureContext:
    return HistoricalFixtureContext(fixture_id=FixtureId(uuid4()), home_team_id=HOME_TEAM, away_team_id=AWAY_TEAM, kickoff=kickoff)


def _forward_player() -> tuple[Player, KGNode]:
    player = Player(id=PlayerId(uuid4()), sport_id=SportId(uuid4()), name="Striker", date_of_birth=None, position="attacker")
    node = KGNode(id=KGNodeId(uuid4()), node_type=NodeType.PLAYER, entity_ref=str(player.id.value))
    return player, node


def _team_node(team_id: TeamId) -> KGNode:
    return KGNode(id=KGNodeId(uuid4()), node_type=NodeType.TEAM, entity_ref=str(team_id.value))


def _event(node_ref: str, *, node_type="player", availability="VERIFIED_PRE_MATCH", information_available_at=T0, event_type=NewsEventType.INJURY) -> NewsEvent:
    return NewsEvent(
        id=NewsEventId(uuid4()), event_type=event_type, summary="x", confidence=0.8,
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0, detected_at=T0,
        affected_entity_refs=(node_ref,),
        resolved_entities=(ResolvedNewsEntity(ref=node_ref, node_type=node_type, status=EntityResolutionStatus.RESOLVED),),
        confidence_tier=NewsEventConfidenceTier.CONFIRMED, availability_classification=availability,
        information_available_at=information_available_at,
    )


@pytest.fixture
def registration():
    definitions = InMemoryFeatureDefinitionRepository()
    lineage = FeatureLineageService(lineage=InMemoryFeatureLineageRepository(), definitions=definitions)
    return FeatureRegistrationService(definitions=definitions, versions=InMemoryFeatureVersionRepository(), lineage=lineage)


@pytest.fixture
def store(registration):
    return FeatureStoreService(definitions=registration.definitions, offline=InMemoryFeatureValueRepository(), online=InMemoryOnlineFeatureStore())


def _service(registration, store, kg_nodes, players, transfers, events=None):
    resolution = HistoricalEntityResolutionService(transfers=transfers)
    relevance_engine = HistoricalNewsRelevanceEngine(
        kg_nodes=kg_nodes, entity_resolution=resolution,
        market_rule_exists=lambda et, mk: any(r.event_type is et and r.market_key == mk for r in MARKET_IMPACT_RULES),
    )
    impact_engine = NewsMarketImpactEngine(
        registration=registration, store=store, events=events or InMemoryNewsEventRepository(),
        kg_nodes=kg_nodes, players=players, transfers=transfers, historical_entity_resolution=resolution,
        sport_code="football",
    )
    return HistoricalFeatureReconstructionService(news_market_impact=impact_engine, relevance_engine=relevance_engine)


# --- audit_events_for_fixture classification matrix ------------------------------------------

async def test_eligible_event_is_news_feature_eligible(registration, store):
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    service = _service(registration, store, kg_nodes, players, transfers)
    event = _event(str(node.id))

    results = await service.audit_events_for_fixture(_fixture_context(), [event])

    assert len(results) == 1
    assert results[0].eligibility is NewsFeatureEligibility.NEWS_FEATURE_ELIGIBLE


async def test_c_unknown_availability_time_is_news_feature_ineligible(registration, store):
    """Case C — HISTORICALLY_RELEVANT but UNKNOWN_AVAILABILITY_TIME must never become eligible."""
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    service = _service(registration, store, kg_nodes, players, transfers)
    event = _event(str(node.id), availability="UNKNOWN_AVAILABILITY_TIME")

    results = await service.audit_events_for_fixture(_fixture_context(), [event])

    assert results[0].eligibility is NewsFeatureEligibility.NEWS_FEATURE_INELIGIBLE
    assert event.availability_classification == "UNKNOWN_AVAILABILITY_TIME"  # unchanged


async def test_b_article_after_kickoff_is_never_pre_match_eligible(registration, store):
    """Case B/M — even VERIFIED_PRE_MATCH + historically relevant must be excluded once
    information_available_at is not strictly before the target fixture's own kickoff."""
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    service = _service(registration, store, kg_nodes, players, transfers)
    post_kickoff_event = _event(str(node.id), information_available_at=KICKOFF + timedelta(hours=1))

    results = await service.audit_events_for_fixture(_fixture_context(), [post_kickoff_event])

    assert results[0].eligibility is NewsFeatureEligibility.NEWS_FEATURE_INELIGIBLE


async def test_k_entity_unresolved(registration, store):
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    service = _service(registration, store, kg_nodes, players, transfers)
    event = _event(str(uuid4()))  # never registered as a KG node

    results = await service.audit_events_for_fixture(_fixture_context(), [event])

    assert results[0].eligibility is NewsFeatureEligibility.NEWS_ENTITY_UNRESOLVED


async def test_h_insufficient_transfer_coverage_is_news_fixture_unresolved(registration, store):
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()  # no transfer history at all
    kg_nodes.add(node)
    players.by_id[player.id] = player
    service = _service(registration, store, kg_nodes, players, transfers)
    event = _event(str(node.id))

    results = await service.audit_events_for_fixture(_fixture_context(), [event])

    assert results[0].eligibility is NewsFeatureEligibility.NEWS_FIXTURE_UNRESOLVED


async def test_j_market_cannot_be_determined_is_news_market_unresolved(registration, store):
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    service = _service(registration, store, kg_nodes, players, transfers)
    event = _event(str(node.id))

    results = await service.audit_events_for_fixture(_fixture_context(), [event], market_key="football.corners")

    assert results[0].eligibility is NewsFeatureEligibility.NEWS_MARKET_UNRESOLVED


async def test_p_a_valid_market_key_does_not_leak_relevance_into_an_unrelated_one(registration, store):
    """P — the same event, evaluated against a market with a real rule, stays eligible; against
    one with no rule, it is market-unresolved. One market's signal never silently satisfies
    another's requirement."""
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    service = _service(registration, store, kg_nodes, players, transfers)
    event = _event(str(node.id))

    goals = await service.audit_events_for_fixture(_fixture_context(), [event], market_key="football.total_goals_over_under")
    corners = await service.audit_events_for_fixture(_fixture_context(), [event], market_key="football.corners")

    assert goals[0].eligibility is NewsFeatureEligibility.NEWS_FEATURE_ELIGIBLE
    assert corners[0].eligibility is NewsFeatureEligibility.NEWS_MARKET_UNRESOLVED


async def test_l_article_belonging_to_an_unrelated_fixture_does_not_leak_in(registration, store):
    node = _team_node(UNRELATED_TEAM)
    kg_nodes = InMemoryKGNodeRepository()
    kg_nodes.add(node)
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    service = _service(registration, store, kg_nodes, players, transfers)
    event = _event(str(node.id), node_type="team")

    results = await service.audit_events_for_fixture(_fixture_context(), [event])

    assert results[0].eligibility is NewsFeatureEligibility.NEWS_FEATURE_INELIGIBLE


# --- Structural: no fixture-lookup dependency (Case N) -----------------------------------------

async def test_n_service_has_no_fixture_repository_dependency():
    """The fixture context is always explicitly supplied by the caller — the service cannot look
    up "the current fixture" for a team, so a caller's own (possibly stale) fixture data can never
    silently substitute for the historical fixture actually being reconstructed."""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(HistoricalFeatureReconstructionService)}
    assert field_names == {"news_market_impact", "relevance_engine"}


# --- O. News unavailable: publish_for_fixture is a no-op, never raises -------------------------

async def test_o_no_candidate_events_publishes_nothing_without_raising(registration, store):
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    service = _service(registration, store, kg_nodes, players, transfers)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    assert written == []


# --- publish_for_fixture actually writes for both sides with historical timestamps -------------

async def test_publish_for_fixture_writes_for_both_sides_stamped_at_the_historical_time(registration, store):
    home_player, home_node = _forward_player()
    away_player, away_node = _forward_player()
    events = InMemoryNewsEventRepository()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(home_node)
    kg_nodes.add(away_node)
    players.by_id[home_player.id] = home_player
    players.by_id[away_player.id] = away_player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=home_player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=away_player.id, from_team_id=None, to_team_id=AWAY_TEAM, effective_date=T0 - timedelta(days=10)))
    events.add(str(home_node.id), _event(str(home_node.id)))
    events.add(str(away_node.id), _event(str(away_node.id)))
    service = _service(registration, store, kg_nodes, players, transfers, events=events)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    assert len(written) >= 2
    assert all(v.as_of == KICKOFF for v in written)
    keys = {v.feature_key.value for v in written}
    assert "news.football.home_goal_impact" in keys
    assert "news.football.away_goal_impact" in keys
