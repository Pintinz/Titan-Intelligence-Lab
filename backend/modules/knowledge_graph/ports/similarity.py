"""Similarity Engine port — framework only, no ML embeddings yet (docs/ontology.md §5,
Milestone 7 explicit scope: "Implement framework only. No ML embeddings yet... Support future
embedding providers.").

``SimilarityPort`` is deliberately backend-agnostic: `GraphStructuralSimilarity` (this
milestone's only implementation) scores similarity from shared graph neighbors — a real,
deterministic, explainable baseline. A future embedding-vector-backed adapter (Gemini
embeddings or similar) implements the exact same port and slots in without touching any
consumer, the same mock-first/adapter-swap shape used for every other pluggable capability in
this codebase (docs/decisions.md ADR-008).
"""

from __future__ import annotations

from typing import Protocol

from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType


class SimilarityPort(Protocol):
    async def similarity(self, node_a: KGNodeId, node_b: KGNodeId) -> float: ...

    async def most_similar(
        self, node_id: KGNodeId, node_type: NodeType, limit: int = 10, min_score: float = 0.0
    ) -> list[tuple[KGNode, float]]: ...
