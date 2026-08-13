from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.features.domain.value_objects import FeatureKey
from modules.intelligence.application.historical_entity_resolution_service import (
    HistoricalEntityResolutionService,
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
from modules.predictions.application.news_market_impact_engine import NewsMarketImpactEngine
from modules.sports.domain.entities import Player, Transfer
from modules.sports.domain.value_objects import EntityId, PlayerId, SportId, TeamId
from tests.unit.modules.features.conftest import (
    InMemoryFeatureDefinitionRepository,
    InMemoryFeatureLineageRepository,
    InMemoryFeatureValueRepository,
    InMemoryFeatureVersionRepository,
    InMemoryOnlineFeatureStore,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@dataclass
class InMemoryNewsEventRepository:
    store: dict = field(default_factory=dict)

    def add(self, entity_ref: str, event: NewsEvent) -> None:
        self.store.setdefault(entity_ref, []).append(event)

    async def list_for_entity(self, entity_ref: str):
        return list(self.store.get(entity_ref, []))


@dataclass
class InMemoryKGNodeRepository:
    store: dict = field(default_factory=dict)

    def add(self, node: KGNode) -> None:
        self.store[(node.node_type, node.entity_ref)] = node

    async def get_by_entity_ref(self, node_type, entity_ref: str):
        return self.store.get((node_type, entity_ref))


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


def _engine(registration, store, events, kg_nodes, players, transfers=None, historical_entity_resolution=None) -> NewsMarketImpactEngine:
    return NewsMarketImpactEngine(
        registration=registration, store=store, events=events, kg_nodes=kg_nodes, players=players,
        transfers=transfers, historical_entity_resolution=historical_entity_resolution,
        sport_code="football",
    )


@pytest.fixture
def registration():
    definitions = InMemoryFeatureDefinitionRepository()
    lineage = FeatureLineageService(lineage=InMemoryFeatureLineageRepository(), definitions=definitions)
    return FeatureRegistrationService(
        definitions=definitions, versions=InMemoryFeatureVersionRepository(), lineage=lineage
    )


@pytest.fixture
def store(registration):
    return FeatureStoreService(
        definitions=registration.definitions, offline=InMemoryFeatureValueRepository(), online=InMemoryOnlineFeatureStore()
    )


def _event(
    event_type: NewsEventType, resolved_ref: str, *,
    confidence_tier=NewsEventConfidenceTier.CONFIRMED, availability="VERIFIED_PRE_MATCH", occurred_at=T0,
) -> NewsEvent:
    return NewsEvent(
        id=NewsEventId(uuid4()), event_type=event_type, summary="x", confidence=0.8,
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=occurred_at, detected_at=occurred_at,
        affected_entity_refs=(resolved_ref,),
        resolved_entities=(ResolvedNewsEntity(ref=resolved_ref, node_type="player", status=EntityResolutionStatus.RESOLVED),),
        confidence_tier=confidence_tier, availability_classification=availability, information_available_at=occurred_at,
    )


def _forward(*, current_team_id: TeamId | None = None) -> tuple[Player, KGNode]:
    player = Player(
        id=PlayerId(uuid4()), sport_id=SportId(uuid4()), name="Striker", date_of_birth=None,
        position="attacker", team_id=current_team_id,
    )
    node = KGNode(id=KGNodeId(uuid4()), node_type=NodeType.PLAYER, entity_ref=str(player.id.value))
    return player, node


def _transfer(player_id: PlayerId, to_team: TeamId | None, effective_date: datetime, from_team: TeamId | None = None) -> Transfer:
    return Transfer(id=EntityId(uuid4()), player_id=player_id, from_team_id=from_team, to_team_id=to_team, effective_date=effective_date)


# --- Fail-closed: historical mode requires the new dependencies ---------------------------------

async def test_historical_reference_time_without_wiring_fails_closed(registration, store):
    team_id = TeamId(uuid4())
    engine = _engine(registration, store, InMemoryNewsEventRepository(), InMemoryKGNodeRepository(), InMemoryPlayerRepository())

    with pytest.raises(ValueError, match="historical_reference_time"):
        await engine.compute_and_write("fixture-1", team_id, "home", T0, historical_reference_time=T0)


# --- Basic historical roster reconstruction ------------------------------------------------------

async def test_historical_roster_uses_transfer_chain_not_current_team_id(registration, store):
    """The player's CURRENT `team_id` (set on the Player object below) is TEAM_CURRENT — a
    completely different team from the one the Transfer chain says they were on at T0. The
    historically-reconstructed roster must follow the Transfer evidence, never `Player.team_id`."""
    team_historical = TeamId(uuid4())
    team_current = TeamId(uuid4())
    player, node = _forward(current_team_id=team_current)  # current team_id deliberately wrong
    events = InMemoryNewsEventRepository()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.add(team_historical, player)  # also registered under the historical team for list_by_team parity
    players.by_id[player.id] = player
    transfers.add(_transfer(player.id, team_historical, T0 - timedelta(days=100)))
    events.add(str(node.id), _event(NewsEventType.INJURY, str(node.id), occurred_at=T0))

    resolution = HistoricalEntityResolutionService(transfers=transfers)
    engine = _engine(registration, store, events, kg_nodes, players, transfers=transfers, historical_entity_resolution=resolution)
    await engine.ensure_registered(T0)

    written = await engine.compute_and_write(
        "fixture-1", team_historical, "home", T0, kickoff=T0 + timedelta(hours=2), historical_reference_time=T0,
    )

    goal_impact = next(v for v in written if v.feature_key == FeatureKey("news.football.home_goal_impact"))
    assert goal_impact.value < 0.0


async def test_historical_roster_excludes_a_player_never_historically_on_this_team(registration, store):
    """Even though `players.list_by_team` has been (mis-)populated with this player under the
    target team, the Transfer chain says they were never on it — historical mode must exclude
    them, since roster membership routes through Transfer evidence, not the list_by_team fixture."""
    team_id = TeamId(uuid4())
    unrelated_team = TeamId(uuid4())
    player, node = _forward()
    events = InMemoryNewsEventRepository()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(_transfer(player.id, unrelated_team, T0 - timedelta(days=10)))  # never joined team_id
    events.add(str(node.id), _event(NewsEventType.INJURY, str(node.id), occurred_at=T0))

    resolution = HistoricalEntityResolutionService(transfers=transfers)
    engine = _engine(registration, store, events, kg_nodes, players, transfers=transfers, historical_entity_resolution=resolution)
    await engine.ensure_registered(T0)

    written = await engine.compute_and_write(
        "fixture-1", team_id, "home", T0, kickoff=T0 + timedelta(hours=2), historical_reference_time=T0,
    )

    assert written == []


# --- E. Leakage: a later transfer must not affect an earlier reconstruction ----------------------

async def test_e_later_transfer_does_not_leak_into_an_earlier_reconstruction(registration, store):
    team_id = TeamId(uuid4())
    later_team = TeamId(uuid4())
    player, node = _forward()
    events = InMemoryNewsEventRepository()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(_transfer(player.id, team_id, T0 - timedelta(days=100)))
    transfers.add(_transfer(player.id, later_team, T0 + timedelta(days=50)))  # after the reconstruction point
    events.add(str(node.id), _event(NewsEventType.INJURY, str(node.id), occurred_at=T0))

    resolution = HistoricalEntityResolutionService(transfers=transfers)
    engine = _engine(registration, store, events, kg_nodes, players, transfers=transfers, historical_entity_resolution=resolution)
    await engine.ensure_registered(T0)

    written = await engine.compute_and_write(
        "fixture-1", team_id, "home", T0, kickoff=T0 + timedelta(hours=2), historical_reference_time=T0,
    )

    goal_impact = next(v for v in written if v.feature_key == FeatureKey("news.football.home_goal_impact"))
    assert goal_impact.value < 0.0  # still counted for team_id — the later transfer is irrelevant


# --- F. Current Player.team_id differs from historical team --------------------------------------

async def test_f_current_player_team_id_conflict_historical_transfer_wins(registration, store):
    """Structural + behavioral: the Player object's own `team_id` field says one thing, the
    Transfer chain says another — only the Transfer chain is ever consulted in historical mode."""
    historical_team = TeamId(uuid4())
    current_team_per_player_dot_team_id = TeamId(uuid4())
    player, node = _forward(current_team_id=current_team_per_player_dot_team_id)
    assert player.team_id == current_team_per_player_dot_team_id
    assert player.team_id != historical_team

    events = InMemoryNewsEventRepository()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(_transfer(player.id, historical_team, T0 - timedelta(days=5)))
    events.add(str(node.id), _event(NewsEventType.INJURY, str(node.id), occurred_at=T0))

    resolution = HistoricalEntityResolutionService(transfers=transfers)
    engine = _engine(registration, store, events, kg_nodes, players, transfers=transfers, historical_entity_resolution=resolution)
    await engine.ensure_registered(T0)

    written = await engine.compute_and_write(
        "fixture-1", historical_team, "home", T0, kickoff=T0 + timedelta(hours=2), historical_reference_time=T0,
    )

    goal_impact = next(v for v in written if v.feature_key == FeatureKey("news.football.home_goal_impact"))
    assert goal_impact.value < 0.0


# --- G. Knowledge Graph never overrides historical resolution ------------------------------------

async def test_g_historical_resolution_never_reads_kg_edges_for_membership():
    """Structural proof: `_resolve_roster`'s historical branch depends only on `transfers`/
    `historical_entity_resolution` — `kg_nodes` (used elsewhere, only for event lookup by ref) is
    never consulted for membership, so a stale/never-superseded `PLAYS_FOR` edge (the Milestone 13
    audit's own finding) cannot influence historical roster reconstruction."""
    import inspect

    source = inspect.getsource(NewsMarketImpactEngine._resolve_roster)
    assert "kg_nodes" not in source


# --- H. Insufficient transfer coverage ------------------------------------------------------------

async def test_h_no_transfer_evidence_excludes_the_player(registration, store):
    team_id = TeamId(uuid4())
    player, node = _forward()
    events = InMemoryNewsEventRepository()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()  # empty — no transfer history at all
    kg_nodes.add(node)
    players.by_id[player.id] = player
    events.add(str(node.id), _event(NewsEventType.INJURY, str(node.id), occurred_at=T0))

    resolution = HistoricalEntityResolutionService(transfers=transfers)
    engine = _engine(registration, store, events, kg_nodes, players, transfers=transfers, historical_entity_resolution=resolution)
    await engine.ensure_registered(T0)

    written = await engine.compute_and_write(
        "fixture-1", team_id, "home", T0, kickoff=T0 + timedelta(hours=2), historical_reference_time=T0,
    )

    assert written == []


# --- Live/current mode is byte-identical when historical_reference_time is omitted ----------------

async def test_live_mode_unaffected_by_the_new_optional_fields(registration, store):
    team_id = TeamId(uuid4())
    player, node = _forward(current_team_id=team_id)
    events = InMemoryNewsEventRepository()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    kg_nodes.add(node)
    players.add(team_id, player)
    events.add(str(node.id), _event(NewsEventType.INJURY, str(node.id), occurred_at=T0))

    # No transfers/historical_entity_resolution wired at all — must still work for live mode.
    engine = _engine(registration, store, events, kg_nodes, players)
    await engine.ensure_registered(T0)

    written = await engine.compute_and_write("fixture-1", team_id, "home", T0)

    goal_impact = next(v for v in written if v.feature_key == FeatureKey("news.football.home_goal_impact"))
    assert goal_impact.value < 0.0
