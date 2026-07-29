"""Graph Query Engine port (docs/ontology.md, docs/decisions.md ADR — Milestone 7).

Named ``GraphQueryPort`` per docs/knowledge_graph.md §6's own build-order plan (written back in
Milestone 5: "Read API (GraphQueryPort) for direct entity relationships — Milestone 9",
delivered here instead once the constitution redefined this milestone's number and scope). A
``Protocol`` like every other port in this codebase — implemented today by
``GraphQueryService`` against the relational ``kg_nodes``/``kg_edges`` tables (ADR-005), but
swappable for a dedicated graph database backend later without touching any consumer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGNodeId, NodeType


@dataclass(frozen=True)
class Subgraph:
    """A bounded set of nodes + the edges connecting them — the common return shape for every
    multi-hop query (neighborhood, subgraph extraction, historical snapshot, context
    expansion). Deliberately bounded (``max_nodes`` on every query that produces one) rather
    than unbounded, per the Graph Performance requirement ("Memory Usage")."""

    nodes: tuple[KGNode, ...] = field(default_factory=tuple)
    edges: tuple[KGEdge, ...] = field(default_factory=tuple)
    truncated: bool = False  # True if the traversal hit max_nodes and stopped early — treat
    # the result as a sample, not the complete neighborhood, when this is set.


class GraphQueryPort(Protocol):
    async def shortest_path(
        self, from_node_id: KGNodeId, to_node_id: KGNodeId, edge_type: EdgeType | None = None, max_depth: int = 6
    ) -> list[KGNode] | None: ...

    async def neighborhood(
        self, node_id: KGNodeId, depth: int = 1, edge_type: EdgeType | None = None, max_nodes: int = 200
    ) -> Subgraph: ...

    async def subgraph_extraction(
        self, node_ids: list[KGNodeId], depth: int = 1, max_nodes: int = 500
    ) -> Subgraph: ...

    async def traverse(
        self, node_id: KGNodeId, edge_type: EdgeType, reverse: bool = False, max_hops: int = 5, max_nodes: int = 200
    ) -> list[KGNode]: ...

    async def connected_components(
        self, node_type: NodeType, edge_type: EdgeType | None = None, max_nodes: int = 2000
    ) -> list[list[KGNodeId]]: ...

    async def at_time(self, node_id: KGNodeId, as_of: datetime, depth: int = 1, max_nodes: int = 200) -> Subgraph: ...

    async def most_connected(
        self, node_type: NodeType, edge_type: EdgeType, direction: str = "in", limit: int = 10
    ) -> list[tuple[KGNode, int]]: ...

    async def edge_history(self, node_id: KGNodeId, edge_type: EdgeType | None = None) -> list[KGEdge]: ...
