from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.intelligence.application.historical_entity_resolution_service import (
    HistoricalEntityResolutionService,
)
from modules.intelligence.application.historical_news_relevance_engine import (
    HistoricalFixtureContext,
    HistoricalNewsRelevanceEngine,
    HistoricalRelevanceClassification,
)
from modules.intelligence.domain.entities import NewsEvent, ResolvedNewsEntity
from modules.intelligence.domain.value_objects import (
    EntityResolutionStatus,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
)
from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.sports.domain.entities import Transfer
from modules.sports.domain.value_objects import EntityId, FixtureId, PlayerId, TeamId

T0 = datetime(2024, 3, 1, tzinfo=timezone.utc)
FIXTURE_KICKOFF = datetime(2024, 3, 2, tzinfo=timezone.utc)

HOME_TEAM = TeamId(uuid4())
AWAY_TEAM = TeamId(uuid4())
UNRELATED_TEAM = TeamId(uuid4())
PLAYER = PlayerId(uuid4())


@dataclass
class _FakeTransferRepo:
    by_player: dict = field(default_factory=dict)

    async def list_by_player(self, player_id):
        return self.by_player.get(player_id, [])

    async def list_by_team(self, team_id):
        return []

    async def get(self, transfer_id):
        return None

    async def upsert(self, transfer):
        return transfer


@dataclass
class _FakeKGNodeRepo:
    nodes: dict = field(default_factory=dict)  # KGNodeId -> KGNode

    async def get(self, node_id):
        return self.nodes.get(node_id)

    async def get_by_entity_ref(self, node_type, entity_ref):
        for node in self.nodes.values():
            if node.node_type is node_type and node.entity_ref == entity_ref:
                return node
        return None

    async def list_by_type(self, node_type):
        return [n for n in self.nodes.values() if n.node_type is node_type]

    async def upsert(self, node):
        self.nodes[node.id] = node
        return node


def _transfer(to_team, effective_date: datetime, from_team=None) -> Transfer:
    return Transfer(
        id=EntityId(uuid4()), player_id=PLAYER, from_team_id=from_team, to_team_id=to_team,
        effective_date=effective_date,
    )


def _team_node(team_id: TeamId) -> tuple[KGNodeId, KGNode]:
    node_id = KGNodeId(uuid4())
    return node_id, KGNode(id=node_id, node_type=NodeType.TEAM, entity_ref=str(team_id.value))


def _player_node(player_id: PlayerId) -> tuple[KGNodeId, KGNode]:
    node_id = KGNodeId(uuid4())
    return node_id, KGNode(id=node_id, node_type=NodeType.PLAYER, entity_ref=str(player_id.value))


def _fixture_context(kickoff=FIXTURE_KICKOFF) -> HistoricalFixtureContext:
    return HistoricalFixtureContext(
        fixture_id=FixtureId(uuid4()), home_team_id=HOME_TEAM, away_team_id=AWAY_TEAM, kickoff=kickoff,
    )


def _event(resolved_entities, information_available_at=None, event_type=NewsEventType.INJURY) -> NewsEvent:
    return NewsEvent(
        id=NewsEventId(uuid4()), event_type=event_type, summary="test event", confidence=0.7,
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()),
        occurred_at=T0, detected_at=T0, resolved_entities=tuple(resolved_entities),
        information_available_at=information_available_at,
    )


def _engine(kg_nodes: dict, transfers_by_player: dict, market_rule_exists=None) -> HistoricalNewsRelevanceEngine:
    return HistoricalNewsRelevanceEngine(
        kg_nodes=_FakeKGNodeRepo(nodes=kg_nodes),
        entity_resolution=HistoricalEntityResolutionService(
            transfers=_FakeTransferRepo(by_player=transfers_by_player)
        ),
        market_rule_exists=market_rule_exists,
    )


# --- J. Unknown information_available_at -------------------------------------------------------

async def test_j_unknown_reference_time_is_insufficient_provenance():
    engine = _engine({}, {})
    event = _event([])

    result = await engine.resolve_relevance(event, None, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.INSUFFICIENT_PROVENANCE
    assert result.reference_time is None


# --- K. Historical entity cannot be resolved -----------------------------------------------------

async def test_k_entity_that_no_longer_exists_in_the_kg_is_unresolved():
    engine = _engine({}, {})
    event = _event([ResolvedNewsEntity(ref=str(uuid4()), node_type="team", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.ENTITY_UNRESOLVED


async def test_k_event_with_no_resolved_mentions_at_all_is_entity_unresolved():
    engine = _engine({}, {})
    event = _event([ResolvedNewsEntity(ref="some raw unresolved text", node_type=None, status=EntityResolutionStatus.UNRESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.ENTITY_UNRESOLVED
    assert result.entity_resolution == "unresolved"


# --- L. Historical player cannot be linked to the fixture team (no bracketing evidence) ----------

async def test_l_player_with_no_bracketing_transfer_evidence_is_historically_unresolved():
    node_id, node = _player_node(PLAYER)
    engine = _engine(
        kg_nodes={node_id: node},
        transfers_by_player={PLAYER: [_transfer(HOME_TEAM, T0 + timedelta(days=100))]},  # only future evidence
    )
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="player", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.HISTORICALLY_UNRESOLVED
    assert result.membership_resolution == "unresolved"


# --- M. Historical team directly matches fixture home team ---------------------------------------

async def test_m_team_mention_matching_fixture_home_team_is_historically_relevant():
    node_id, node = _team_node(HOME_TEAM)
    engine = _engine(kg_nodes={node_id: node}, transfers_by_player={})
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="team", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.HISTORICALLY_RELEVANT
    assert any("home_team_id" in e for e in result.evidence)


# --- N. Historical team directly matches fixture away team ---------------------------------------

async def test_n_team_mention_matching_fixture_away_team_is_historically_relevant():
    node_id, node = _team_node(AWAY_TEAM)
    engine = _engine(kg_nodes={node_id: node}, transfers_by_player={})
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="team", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.HISTORICALLY_RELEVANT
    assert any("away_team_id" in e for e in result.evidence)


# --- O. Historical player belongs to fixture team at article availability time --------------------

async def test_o_player_historically_on_home_team_at_reference_time_is_historically_relevant():
    node_id, node = _player_node(PLAYER)
    engine = _engine(
        kg_nodes={node_id: node},
        transfers_by_player={PLAYER: [_transfer(HOME_TEAM, T0 - timedelta(days=30))]},
    )
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="player", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.HISTORICALLY_RELEVANT
    assert result.membership_resolution == "resolved"


# --- P. Historical player belongs to an unrelated team --------------------------------------------

async def test_p_player_historically_on_an_unrelated_team_is_not_relevant():
    node_id, node = _player_node(PLAYER)
    engine = _engine(
        kg_nodes={node_id: node},
        transfers_by_player={PLAYER: [_transfer(UNRELATED_TEAM, T0 - timedelta(days=30))]},
    )
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="player", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.NOT_RELEVANT


# --- Case 1 (from the M13 audit): current-fixture bias is structurally impossible -----------------

async def test_case1_team_currently_associated_is_never_consulted_only_the_given_fixture_context():
    """The engine only ever compares against the `fixture_context` it was explicitly given —
    there is no code path that looks up "this team's current/upcoming fixture." A team matching
    some OTHER (unrelated) fixture must not leak into this fixture's relevance."""
    node_id, node = _team_node(UNRELATED_TEAM)
    engine = _engine(kg_nodes={node_id: node}, transfers_by_player={})
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="team", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.NOT_RELEVANT


# --- Q. Market cannot be resolved -------------------------------------------------------------------

async def test_q_relevant_event_with_no_configured_market_rule_is_market_unresolved():
    node_id, node = _team_node(HOME_TEAM)
    engine = _engine(kg_nodes={node_id: node}, transfers_by_player={}, market_rule_exists=lambda et, mk: False)
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="team", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context(), market_key="football.corners")

    assert result.classification is HistoricalRelevanceClassification.MARKET_UNRESOLVED
    assert result.market_resolution == "unresolved"


async def test_q_relevant_event_with_a_configured_market_rule_stays_historically_relevant():
    node_id, node = _team_node(HOME_TEAM)
    engine = _engine(kg_nodes={node_id: node}, transfers_by_player={}, market_rule_exists=lambda et, mk: True)
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="team", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context(), market_key="football.total_goals_over_under")

    assert result.classification is HistoricalRelevanceClassification.HISTORICALLY_RELEVANT
    assert result.market_resolution == "resolved"


async def test_q_no_market_rule_checker_configured_treats_market_as_unresolved():
    node_id, node = _team_node(HOME_TEAM)
    engine = _engine(kg_nodes={node_id: node}, transfers_by_player={})  # market_rule_exists=None
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="team", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(event, T0, _fixture_context(), market_key="football.corners")

    assert result.classification is HistoricalRelevanceClassification.MARKET_UNRESOLVED


# --- R/S. BACKFILL/ADMIN_MANUAL can never become VERIFIED_PRE_MATCH via this engine -----------------

async def test_r_historical_relevance_never_mutates_the_events_own_provenance_fields():
    """This engine never writes to `NewsEvent.availability_classification`/
    `information_available_at` — proving BACKFILL/ADMIN_MANUAL events stay exactly as
    `classify_news_availability` (Milestone 9, untouched) already classified them, regardless of
    how historically relevant this engine finds them."""
    node_id, node = _team_node(HOME_TEAM)
    engine = _engine(kg_nodes={node_id: node}, transfers_by_player={})
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="team", status=EntityResolutionStatus.RESOLVED)])
    event.availability_classification = "UNKNOWN_AVAILABILITY_TIME"  # BACKFILL/ADMIN_MANUAL's real state

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.HISTORICALLY_RELEVANT
    assert event.availability_classification == "UNKNOWN_AVAILABILITY_TIME"  # unchanged
    assert event.information_available_at is None  # unchanged


# --- T. Historical relevance cannot bypass Feature Store eligibility ---------------------------------

async def test_t_historically_relevant_event_still_fails_feature_eligibility_if_not_verified_pre_match():
    node_id, node = _team_node(HOME_TEAM)
    engine = _engine(kg_nodes={node_id: node}, transfers_by_player={})
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="team", status=EntityResolutionStatus.RESOLVED)])
    event.availability_classification = "UNKNOWN_AVAILABILITY_TIME"

    result = await engine.resolve_relevance(event, T0, _fixture_context())

    assert result.classification is HistoricalRelevanceClassification.HISTORICALLY_RELEVANT
    assert event.is_feature_eligible() is False  # the existing, unchanged M9 eligibility gate


# --- Leakage tests (spec §15) -----------------------------------------------------------------------

async def test_leakage_a_later_transfer_never_affects_an_earlier_articles_resolution():
    """Article available 2024-03-01; fixture 2024-03-02; a transfer effective 2024-03-10 (after
    the article) must not change how the March 1 article resolves."""
    node_id, node = _player_node(PLAYER)
    engine = _engine(
        kg_nodes={node_id: node},
        transfers_by_player={
            PLAYER: [
                _transfer(HOME_TEAM, datetime(2024, 1, 1, tzinfo=timezone.utc)),
                _transfer(UNRELATED_TEAM, datetime(2024, 3, 10, tzinfo=timezone.utc)),  # future, must be ignored
            ]
        },
    )
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="player", status=EntityResolutionStatus.RESOLVED)])
    article_available_at = datetime(2024, 3, 1, tzinfo=timezone.utc)

    result = await engine.resolve_relevance(event, article_available_at, _fixture_context(kickoff=datetime(2024, 3, 2, tzinfo=timezone.utc)))

    assert result.classification is HistoricalRelevanceClassification.HISTORICALLY_RELEVANT  # still on HOME_TEAM


async def test_leakage_b_historical_evidence_overrides_a_hypothetical_current_team_mismatch():
    """Historical transfer chain says Team A on March 1; a hypothetical 'current' team (never
    consulted by this engine at all) says Team B — resolution must follow the historical chain."""
    node_id, node = _player_node(PLAYER)
    engine = _engine(
        kg_nodes={node_id: node},
        transfers_by_player={PLAYER: [_transfer(HOME_TEAM, datetime(2024, 1, 1, tzinfo=timezone.utc))]},
    )
    event = _event([ResolvedNewsEntity(ref=str(node_id.value), node_type="player", status=EntityResolutionStatus.RESOLVED)])

    result = await engine.resolve_relevance(
        event, datetime(2024, 3, 1, tzinfo=timezone.utc),
        _fixture_context(kickoff=datetime(2024, 3, 2, tzinfo=timezone.utc)),
    )

    assert result.classification is HistoricalRelevanceClassification.HISTORICALLY_RELEVANT


# --- Mode separation (spec §16) ---------------------------------------------------------------------

async def test_mode_separation_engine_never_imports_or_references_mode1_vocabulary_building():
    """Structural proof: `HistoricalNewsRelevanceEngine`'s only dependencies are `kg_nodes`,
    `entity_resolution`, and an optional `market_rule_exists` — no `FixtureRepositoryPort`,
    `TeamRepositoryPort`, or `PlayerRepositoryPort` (Mode 1's upcoming-fixture vocabulary
    dependencies) are present, so it is architecturally impossible for this engine to build or
    consult a "currently upcoming" vocabulary."""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(HistoricalNewsRelevanceEngine)}
    assert field_names == {"kg_nodes", "entity_resolution", "market_rule_exists"}
