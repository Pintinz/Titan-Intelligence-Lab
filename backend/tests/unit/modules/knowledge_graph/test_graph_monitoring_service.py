from __future__ import annotations

from datetime import datetime, timezone

from modules.knowledge_graph.application.graph_monitoring_service import (
    GraphMetricsRecorder,
    GraphMonitoringService,
)
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _services(sqlite_session, recorder=None):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    edges = SqlAlchemyKGEdgeRepository(session=sqlite_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    monitoring = GraphMonitoringService(nodes=nodes, edges=edges, recorder=recorder or GraphMetricsRecorder())
    return population, monitoring


async def test_recorder_tracks_population_and_traversal_timing():
    recorder = GraphMetricsRecorder()

    with recorder.time_population():
        pass
    with recorder.time_traversal():
        pass

    assert recorder.populate_count == 1
    assert recorder.traversal_count == 1
    assert recorder.avg_population_seconds >= 0
    assert recorder.avg_traversal_seconds >= 0


def test_recorder_averages_are_zero_with_no_samples():
    recorder = GraphMetricsRecorder()

    assert recorder.avg_population_seconds == 0.0
    assert recorder.avg_traversal_seconds == 0.0


def test_entity_resolution_accuracy_is_none_with_no_duplicates_detected():
    recorder = GraphMetricsRecorder()

    assert recorder.entity_resolution_accuracy is None


def test_entity_resolution_accuracy_is_merge_over_merge_plus_duplicate():
    recorder = GraphMetricsRecorder()
    recorder.record_duplicate_detected(4)
    recorder.record_merge()
    recorder.record_merge()
    recorder.record_merge()

    assert recorder.entity_resolution_accuracy == 3 / 7


async def test_snapshot_reports_node_and_edge_counts_by_type(sqlite_session):
    population, monitoring = _services(sqlite_session)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    p1 = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    p2 = await population.upsert_node(NodeType.PLAYER, "p2", now=T0)
    await population.upsert_edge(p1, team, EdgeType.PLAYS_FOR, T0)
    await population.upsert_edge(p2, team, EdgeType.PLAYS_FOR, T0)
    await sqlite_session.commit()

    snapshot = await monitoring.snapshot()

    assert snapshot.node_count == 3
    assert snapshot.edge_count == 2
    assert snapshot.nodes_by_type[NodeType.TEAM] == 1
    assert snapshot.nodes_by_type[NodeType.PLAYER] == 2
    assert snapshot.edges_by_type[EdgeType.PLAYS_FOR] == 2
    assert snapshot.cache_hit_ratio is None  # no cache wired in this test


async def test_snapshot_reflects_recorder_and_cache(sqlite_session):
    recorder = GraphMetricsRecorder()
    recorder.record_merge()
    recorder.record_duplicate_detected()

    class _FakeCache:
        hit_ratio = 0.75

    population, monitoring = _services(sqlite_session, recorder=recorder)
    monitoring.cache = _FakeCache()

    snapshot = await monitoring.snapshot()

    assert snapshot.merge_count == 1
    assert snapshot.duplicate_count == 1
    assert snapshot.entity_resolution_accuracy == 0.5
    assert snapshot.cache_hit_ratio == 0.75


async def test_growth_since_diffs_two_snapshots(sqlite_session):
    population, monitoring = _services(sqlite_session)
    before = await monitoring.snapshot()
    await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await sqlite_session.commit()
    after = await monitoring.snapshot()

    growth = monitoring.growth_since(before, after)

    assert growth == {"node_growth": 1, "edge_growth": 0}
