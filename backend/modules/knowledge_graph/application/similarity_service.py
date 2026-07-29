"""SimilarityService — computes similarity via an injected `SimilarityPort` and, when it
clears a threshold, persists it as a weighted `SIMILAR_TO` edge (docs/knowledge_graph.md's own
description of that edge type: "weighted, computed"). This is the bridge between the framework
in `ports.similarity`/`infrastructure.similarity` and the graph itself — computing a score is
useless to downstream consumers (Recommendation Engine, Context Engine) until it's actually
written back as a queryable relationship.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort
from modules.knowledge_graph.ports.similarity import SimilarityPort


@dataclass
class SimilarityService:
    similarity_port: SimilarityPort
    population: KnowledgeGraphPopulationService
    nodes: KGNodeRepositoryPort
    similarity_threshold: float = 0.3

    async def compute_and_store(self, node_a: KGNode, node_b: KGNode, now: datetime) -> float:
        score = await self.similarity_port.similarity(node_a.id, node_b.id)
        if score >= self.similarity_threshold:
            await self.population.upsert_edge(
                node_a, node_b, EdgeType.SIMILAR_TO, now,
                weight=score, confidence=score, directed=False,
                attributes={"metric": type(self.similarity_port).__name__},
            )
        return score

    async def recompute_for_type(self, node_type: NodeType, now: datetime, limit_per_node: int = 5) -> int:
        """Recomputes and stores SIMILAR_TO edges for every node of ``node_type`` against its
        top ``limit_per_node`` most-similar peers. Returns the number of edges written. Bounded
        (Graph Performance) — intended for periodic batch runs, not per-request use."""
        candidates = await self.nodes.list_by_type(node_type)
        written = 0
        for node in candidates:
            ranked = await self.similarity_port.most_similar(
                node.id, node_type, limit=limit_per_node, min_score=self.similarity_threshold
            )
            for other, score in ranked:
                await self.population.upsert_edge(
                    node, other, EdgeType.SIMILAR_TO, now,
                    weight=score, confidence=score, directed=False,
                    attributes={"metric": type(self.similarity_port).__name__},
                )
                written += 1
        return written
