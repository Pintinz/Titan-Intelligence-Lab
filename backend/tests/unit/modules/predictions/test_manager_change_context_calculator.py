from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
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
from modules.predictions.application.manager_change_context_calculator import (
    football_manager_change_context_calculator,
)
from modules.sports.domain.value_objects import TeamId

T0 = datetime(2026, 8, 27, tzinfo=timezone.utc)


@dataclass
class InMemoryFeatureVersionRepository:
    store: list = field(default_factory=list)

    async def record(self, snapshot):
        self.store.append(snapshot)
        return snapshot

    async def list_by_feature(self, feature_key):
        return [s for s in self.store if s.feature_key == feature_key]


@dataclass
class InMemoryFeatureLineageRepository:
    edges: list = field(default_factory=list)

    async def add_edge(self, edge):
        self.edges.append(edge)
        return edge

    async def list_dependencies(self, feature_key):
        return [e.depends_on_feature_key for e in self.edges if e.feature_key == feature_key]

    async def list_dependents(self, feature_key):
        return [e.feature_key for e in self.edges if e.depends_on_feature_key == feature_key]


@dataclass
class InMemoryOnlineFeatureStore:
    store: dict = field(default_factory=dict)

    async def get(self, feature_key, entity_type, entity_id):
        return self.store.get((feature_key, entity_type, entity_id))

    async def set(self, value, ttl_seconds):
        self.store[(value.feature_key, value.entity_type, value.entity_id)] = value

    async def delete(self, feature_key, entity_type, entity_id):
        self.store.pop((feature_key, entity_type, entity_id), None)


@dataclass
class InMemoryKGNodeRepository:
    store: dict = field(default_factory=dict)  # {(node_type, entity_ref): KGNode}

    def add(self, node_type: NodeType, entity_ref: str) -> KGNode:
        node = KGNode(id=KGNodeId(uuid4()), node_type=node_type, entity_ref=entity_ref)
        self.store[(node_type, entity_ref)] = node
        return node

    async def get_by_entity_ref(self, node_type, entity_ref):
        return self.store.get((node_type, entity_ref))


@dataclass
class InMemoryNewsEventRepository:
    store: list = field(default_factory=list)  # list[NewsEvent]

    def add(self, event: NewsEvent) -> None:
        self.store.append(event)

    async def list_for_entity(self, entity_ref):
        return [e for e in self.store if entity_ref in e.affected_entity_refs]


def _manager_change_event(
    team_ref: str, occurred_at: datetime, *,
    availability_classification: str = "VERIFIED_PRE_MATCH",
    information_available_at: datetime | None = None,
) -> NewsEvent:
    return NewsEvent(
        id=NewsEventId(uuid4()), event_type=NewsEventType.MANAGER_CHANGE, summary="A manager change occurred.",
        confidence=0.8, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()),
        occurred_at=occurred_at, detected_at=occurred_at,
        resolved_entities=(ResolvedNewsEntity(ref=team_ref, node_type="team", status=EntityResolutionStatus.RESOLVED),),
        affected_entity_refs=(team_ref,),
        availability_classification=availability_classification,
        information_available_at=information_available_at if information_available_at is not None else occurred_at,
    )


@pytest.fixture
def registration(feature_definition_repo):
    lineage = FeatureLineageService(lineage=InMemoryFeatureLineageRepository(), definitions=feature_definition_repo)
    return FeatureRegistrationService(
        definitions=feature_definition_repo, versions=InMemoryFeatureVersionRepository(), lineage=lineage
    )


@pytest.fixture
def store(feature_definition_repo, feature_value_repo):
    return FeatureStoreService(
        definitions=feature_definition_repo, offline=feature_value_repo, online=InMemoryOnlineFeatureStore()
    )


@pytest.fixture
def kg_nodes():
    return InMemoryKGNodeRepository()


@pytest.fixture
def events():
    return InMemoryNewsEventRepository()


async def test_writes_honest_days_elapsed_since_the_most_recent_manager_change(registration, store, events, kg_nodes):
    calculator = football_manager_change_context_calculator(registration, store, events, kg_nodes)
    team_id = TeamId(uuid4())
    node = kg_nodes.add(NodeType.TEAM, str(team_id.value))
    events.add(_manager_change_event(str(node.id), T0 - timedelta(days=10)))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(str(uuid4()), team_id, "home", T0)

    assert value is not None
    assert value.value == pytest.approx(10.0, abs=0.01)
    assert value.feature_key.value == "news.football.home_days_since_manager_change"


async def test_uses_the_most_recent_of_several_manager_change_events(registration, store, events, kg_nodes):
    calculator = football_manager_change_context_calculator(registration, store, events, kg_nodes)
    team_id = TeamId(uuid4())
    node = kg_nodes.add(NodeType.TEAM, str(team_id.value))
    events.add(_manager_change_event(str(node.id), T0 - timedelta(days=100)))
    events.add(_manager_change_event(str(node.id), T0 - timedelta(days=5)))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(str(uuid4()), team_id, "away", T0)

    assert value.value == pytest.approx(5.0, abs=0.01)


async def test_returns_none_when_no_manager_change_event_exists(registration, store, events, kg_nodes):
    calculator = football_manager_change_context_calculator(registration, store, events, kg_nodes)
    team_id = TeamId(uuid4())
    kg_nodes.add(NodeType.TEAM, str(team_id.value))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(str(uuid4()), team_id, "home", T0)

    assert value is None


async def test_returns_none_when_the_team_has_no_kg_node_at_all(registration, store, events, kg_nodes):
    calculator = football_manager_change_context_calculator(registration, store, events, kg_nodes)
    team_id = TeamId(uuid4())

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(str(uuid4()), team_id, "home", T0)

    assert value is None


async def test_ignores_an_event_that_is_not_feature_eligible(registration, store, events, kg_nodes):
    """UNKNOWN_AVAILABILITY_TIME events (point-in-time unverified) must never contribute — same
    is_feature_eligible() gate every other news-derived feature in this codebase respects."""
    calculator = football_manager_change_context_calculator(registration, store, events, kg_nodes)
    team_id = TeamId(uuid4())
    node = kg_nodes.add(NodeType.TEAM, str(team_id.value))
    events.add(_manager_change_event(str(node.id), T0 - timedelta(days=3), availability_classification="UNKNOWN_AVAILABILITY_TIME"))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(str(uuid4()), team_id, "home", T0)

    assert value is None


async def test_ignores_an_event_expired_past_its_validity_window(registration, store, events, kg_nodes):
    """MANAGER_CHANGE's own TTL (180 days, news_validity_policy.py) — a manager change from years
    ago is no longer "recent" and must not be treated as if it were."""
    calculator = football_manager_change_context_calculator(registration, store, events, kg_nodes)
    team_id = TeamId(uuid4())
    node = kg_nodes.add(NodeType.TEAM, str(team_id.value))
    events.add(_manager_change_event(str(node.id), T0 - timedelta(days=400)))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(str(uuid4()), team_id, "home", T0)

    assert value is None


async def test_ignores_information_only_available_after_kickoff(registration, store, events, kg_nodes):
    """Point-in-time leakage guard: information that only became available after the fixture's
    own kickoff must never influence that fixture's pre-match feature, even if it's otherwise a
    real, feature-eligible, still-valid event."""
    calculator = football_manager_change_context_calculator(registration, store, events, kg_nodes)
    team_id = TeamId(uuid4())
    node = kg_nodes.add(NodeType.TEAM, str(team_id.value))
    kickoff = T0 - timedelta(days=5)
    events.add(
        _manager_change_event(
            str(node.id), T0 - timedelta(days=10),
            information_available_at=T0 - timedelta(days=1),  # after kickoff
        )
    )

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(str(uuid4()), team_id, "home", T0, kickoff=kickoff)

    assert value is None


async def test_registers_both_side_feature_keys_idempotently(registration, store, events, kg_nodes):
    calculator = football_manager_change_context_calculator(registration, store, events, kg_nodes)

    await calculator.ensure_registered(T0)
    await calculator.ensure_registered(T0)  # idempotent — must not raise on re-registration

    from modules.features.domain.value_objects import FeatureKey

    for feature_key in (
        "news.football.home_days_since_manager_change",
        "news.football.away_days_since_manager_change",
    ):
        definition = await registration.definitions.get(FeatureKey(feature_key))
        assert definition is not None
        assert definition.leakage_classification == "PRE_MATCH_SAFE"
