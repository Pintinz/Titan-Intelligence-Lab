"""Graph Monitoring — metrics for Nodes, Edges, Relationship Types, Population Speed,
Traversal Time, Cache Hit Ratio, Entity Resolution Accuracy, Merge Count, Duplicate Count,
Graph Growth (docs/ontology.md §10, Milestone 7).

`GraphMetricsRecorder` is a plain in-memory counter object — the same "framework, not a
monitoring platform" posture already taken for Similarity/Context (no Prometheus/OpenTelemetry
wiring this milestone; `modules.admin`'s HealthIntelligenceEngine, Milestone 3, is the existing
precedent for where a real metrics *pipeline* lives if one is needed later). Callers
(`GraphQueryService` consumers, `GraphPopulationBatchService`, `EntityResolutionService`) record
into it explicitly; nothing here wraps their methods automatically, keeping instrumentation
opt-in and visible at the call site rather than magic.

"Entity Resolution Accuracy" has no ground-truth label in this milestone's scope, so it is
reported as a defined proxy — the fraction of detected duplicate candidates that were actually
merged — not a true precision/recall figure; the docstring on the property says so explicitly
rather than implying more rigor than the number actually has.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.knowledge_graph.ports.repositories import KGEdgeRepositoryPort, KGNodeRepositoryPort


@dataclass
class GraphMetricsRecorder:
    populate_count: int = 0
    populate_total_seconds: float = 0.0
    traversal_count: int = 0
    traversal_total_seconds: float = 0.0
    merge_count: int = 0
    duplicate_count: int = 0

    def record_population(self, duration_seconds: float) -> None:
        self.populate_count += 1
        self.populate_total_seconds += duration_seconds

    def record_traversal(self, duration_seconds: float) -> None:
        self.traversal_count += 1
        self.traversal_total_seconds += duration_seconds

    def record_merge(self) -> None:
        self.merge_count += 1

    def record_duplicate_detected(self, count: int = 1) -> None:
        self.duplicate_count += count

    @contextmanager
    def time_population(self):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record_population(time.perf_counter() - started)

    @contextmanager
    def time_traversal(self):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record_traversal(time.perf_counter() - started)

    @property
    def avg_population_seconds(self) -> float:
        return self.populate_total_seconds / self.populate_count if self.populate_count else 0.0

    @property
    def avg_traversal_seconds(self) -> float:
        return self.traversal_total_seconds / self.traversal_count if self.traversal_count else 0.0

    @property
    def entity_resolution_accuracy(self) -> float | None:
        """Proxy metric: fraction of detected duplicate candidates that were actually merged.
        ``None`` when no duplicates have been detected yet (undefined, not zero)."""
        total = self.merge_count + self.duplicate_count
        return self.merge_count / total if total else None


@dataclass(frozen=True)
class GraphMetricsSnapshot:
    node_count: int
    edge_count: int
    nodes_by_type: dict
    edges_by_type: dict
    avg_population_seconds: float
    avg_traversal_seconds: float
    cache_hit_ratio: float | None
    entity_resolution_accuracy: float | None
    merge_count: int
    duplicate_count: int


@dataclass
class GraphMonitoringService:
    nodes: KGNodeRepositoryPort
    edges: KGEdgeRepositoryPort
    recorder: GraphMetricsRecorder = field(default_factory=GraphMetricsRecorder)
    cache: object | None = None  # duck-typed: anything exposing a `.hit_ratio` property

    async def node_count(self) -> int:
        return sum(await self.nodes.count_by_type(node_type) for node_type in NodeType)

    async def edge_count(self) -> int:
        return sum(await self.edges.count_by_type(edge_type) for edge_type in EdgeType)

    async def nodes_by_type(self) -> dict:
        # SQL COUNT per type, not `len(await list_by_type(...))` — that fetched and ORM-mapped
        # every row of every node type just to discard everything but a count, and was the
        # dominant cost of the public platform-summary/knowledge-graph-preview endpoints on a
        # real-scale graph (see KGNodeRepositoryPort.count_by_type docstring).
        return {
            node_type: count
            for node_type in NodeType
            if (count := await self.nodes.count_by_type(node_type)) > 0
        }

    async def edges_by_type(self) -> dict:
        return {
            edge_type: count
            for edge_type in EdgeType
            if (count := await self.edges.count_by_type(edge_type)) > 0
        }

    async def snapshot(self) -> GraphMetricsSnapshot:
        nodes_by_type = await self.nodes_by_type()
        edges_by_type = await self.edges_by_type()
        return GraphMetricsSnapshot(
            node_count=sum(nodes_by_type.values()),
            edge_count=sum(edges_by_type.values()),
            nodes_by_type=nodes_by_type,
            edges_by_type=edges_by_type,
            avg_population_seconds=self.recorder.avg_population_seconds,
            avg_traversal_seconds=self.recorder.avg_traversal_seconds,
            cache_hit_ratio=getattr(self.cache, "hit_ratio", None) if self.cache is not None else None,
            entity_resolution_accuracy=self.recorder.entity_resolution_accuracy,
            merge_count=self.recorder.merge_count,
            duplicate_count=self.recorder.duplicate_count,
        )

    def growth_since(self, previous: GraphMetricsSnapshot, current: GraphMetricsSnapshot) -> dict:
        return {
            "node_growth": current.node_count - previous.node_count,
            "edge_growth": current.edge_count - previous.edge_count,
        }
