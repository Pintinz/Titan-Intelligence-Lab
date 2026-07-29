"""Graph-structural similarity — the framework-only implementation of `SimilarityPort`
(docs/ontology.md §5). Scores two nodes by Jaccard overlap of their immediate graph neighbors
("two players are similar if they share many teammates/opponents/competitions") — a real,
deterministic, explainable metric with no ML embeddings, exactly the Milestone 7 scope.

Covers Player/Team/Coach/Venue/Competition/Model/Feature similarity identically: the metric
doesn't care what `NodeType` it's given, only which other nodes it's connected to — the same
one implementation serves every similarity kind the ontology names ("Historical Match
Similarity" would need per-match feature vectors rather than graph neighbors to be meaningful,
which is exactly the future embedding-backed adapter's job, not this one's).
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType


@dataclass
class GraphStructuralSimilarity:
    query: GraphQueryService
    neighbor_depth: int = 1
    max_candidates: int = 500

    async def similarity(self, node_a: KGNodeId, node_b: KGNodeId) -> float:
        if node_a == node_b:
            return 1.0
        neighbors_a = await self._neighbor_ids(node_a)
        neighbors_b = await self._neighbor_ids(node_b)
        if not neighbors_a and not neighbors_b:
            return 0.0
        intersection = neighbors_a & neighbors_b
        union = neighbors_a | neighbors_b
        return len(intersection) / len(union) if union else 0.0

    async def most_similar(
        self, node_id: KGNodeId, node_type: NodeType, limit: int = 10, min_score: float = 0.0
    ) -> list[tuple[KGNode, float]]:
        candidates = (await self.query.nodes.list_by_type(node_type))[: self.max_candidates]
        scored: list[tuple[KGNode, float]] = []
        for candidate in candidates:
            if candidate.id == node_id:
                continue
            score = await self.similarity(node_id, candidate.id)
            if score >= min_score:
                scored.append((candidate, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]

    async def _neighbor_ids(self, node_id: KGNodeId) -> set[KGNodeId]:
        subgraph = await self.query.neighborhood(node_id, depth=self.neighbor_depth, max_nodes=self.max_candidates)
        return {n.id for n in subgraph.nodes if n.id != node_id}
