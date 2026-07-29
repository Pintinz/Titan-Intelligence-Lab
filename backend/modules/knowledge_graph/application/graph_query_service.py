"""Graph Query Engine — read/traversal layer over the relational KG store (docs/ontology.md,
docs/decisions.md ADR-005/ADR-029). Pure-Python BFS rather than recursive SQL CTEs: portable
across the SQLite fast-test engine and live Postgres without dialect-specific SQL, and simple
enough to reason about at this milestone's traffic scale — revisit with recursive CTEs only if
traversal latency actually becomes a measured problem (same "revisit if it doesn't scale"
posture ADR-005 already took for choosing relational storage over a dedicated graph DB).

Every traversal is bounded (``max_nodes``/``max_hops``/``max_depth``) — Graph Performance's
"Memory Usage" requirement is satisfied by never walking an unbounded frontier, not by a
separate caching layer (docs/ontology.md §7 on what's deliberately not built this milestone).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGNodeId, NodeType
from modules.knowledge_graph.ports.graph_query import Subgraph
from modules.knowledge_graph.ports.repositories import KGEdgeRepositoryPort, KGNodeRepositoryPort


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — same fix used
    in modules.identity/modules.tenancy/modules.ingestion; every timestamp comparison in this
    service goes through it before comparing against a caller-supplied ``as_of``."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass
class GraphQueryService:
    nodes: KGNodeRepositoryPort
    edges: KGEdgeRepositoryPort

    # -- traversal primitives (public: reused by SemanticSearchService/ContextEngine, not just
    # internal to this service) ------------------------------------------------------------------

    async def touching_edges(self, node_id: KGNodeId, edge_type: EdgeType | None = None) -> list[KGEdge]:
        """Every edge touching ``node_id`` in either direction — the undirected view used for
        pathfinding/neighborhood expansion, since "is there a relationship" shouldn't care which
        side of the edge row a node happened to land on."""
        out_edges = await self.edges.list_from(node_id, edge_type)
        in_edges = await self.edges.list_to(node_id, edge_type)
        return out_edges + in_edges

    def other_end(self, edge: KGEdge, node_id: KGNodeId) -> KGNodeId:
        return edge.to_node_id if edge.from_node_id == node_id else edge.from_node_id

    # -- Shortest Path ----------------------------------------------------------------------------

    async def shortest_path(
        self, from_node_id: KGNodeId, to_node_id: KGNodeId, edge_type: EdgeType | None = None, max_depth: int = 6
    ) -> list[KGNode] | None:
        if from_node_id == to_node_id:
            node = await self.nodes.get(from_node_id)
            return [node] if node else None

        visited = {from_node_id}
        parent: dict[KGNodeId, KGNodeId] = {}
        frontier = deque([from_node_id])
        depth = 0

        while frontier and depth < max_depth:
            depth += 1
            for _ in range(len(frontier)):
                current = frontier.popleft()
                for edge in await self.touching_edges(current, edge_type):
                    neighbor = self.other_end(edge, current)
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)
                    parent[neighbor] = current
                    if neighbor == to_node_id:
                        return await self._reconstruct_path(neighbor, parent, from_node_id)
                    frontier.append(neighbor)
        return None

    async def _reconstruct_path(
        self, end: KGNodeId, parent: dict[KGNodeId, KGNodeId], start: KGNodeId
    ) -> list[KGNode]:
        chain = [end]
        while chain[-1] != start:
            chain.append(parent[chain[-1]])
        chain.reverse()
        result = []
        for node_id in chain:
            node = await self.nodes.get(node_id)
            if node is not None:
                result.append(node)
        return result

    # -- Neighborhood Search / Context Expansion ---------------------------------------------------

    async def neighborhood(
        self, node_id: KGNodeId, depth: int = 1, edge_type: EdgeType | None = None, max_nodes: int = 200
    ) -> Subgraph:
        root = await self.nodes.get(node_id)
        if root is None:
            return Subgraph()
        return await self._expand({node_id}, depth, edge_type, max_nodes, seed_nodes={node_id: root})

    async def subgraph_extraction(self, node_ids: list[KGNodeId], depth: int = 1, max_nodes: int = 500) -> Subgraph:
        seeds = set(node_ids)
        seed_nodes = {}
        for node_id in node_ids:
            node = await self.nodes.get(node_id)
            if node is not None:
                seed_nodes[node_id] = node
        return await self._expand(seeds, depth, None, max_nodes, seed_nodes=seed_nodes)

    async def _expand(
        self,
        seeds: set[KGNodeId],
        depth: int,
        edge_type: EdgeType | None,
        max_nodes: int,
        seed_nodes: dict[KGNodeId, KGNode],
    ) -> Subgraph:
        visited_nodes: dict[KGNodeId, KGNode] = dict(seed_nodes)
        collected_edges: dict = {}
        frontier = deque(seeds)
        truncated = False

        for _hop in range(depth):
            next_frontier: deque[KGNodeId] = deque()
            while frontier:
                current = frontier.popleft()
                for edge in await self.touching_edges(current, edge_type):
                    if len(visited_nodes) >= max_nodes:
                        truncated = True
                        break
                    collected_edges[edge.id] = edge
                    neighbor_id = self.other_end(edge, current)
                    if neighbor_id not in visited_nodes:
                        neighbor = await self.nodes.get(neighbor_id)
                        if neighbor is not None:
                            visited_nodes[neighbor_id] = neighbor
                            next_frontier.append(neighbor_id)
                if truncated:
                    break
            frontier = next_frontier
            if truncated:
                break

        return Subgraph(nodes=tuple(visited_nodes.values()), edges=tuple(collected_edges.values()), truncated=truncated)

    # -- Relationship Traversal / Reverse Traversal ------------------------------------------------

    async def traverse(
        self, node_id: KGNodeId, edge_type: EdgeType, reverse: bool = False, max_hops: int = 5, max_nodes: int = 200
    ) -> list[KGNode]:
        visited = {node_id}
        frontier = deque([node_id])
        results: list[KGNode] = []

        for _hop in range(max_hops):
            next_frontier: deque[KGNodeId] = deque()
            while frontier:
                current = frontier.popleft()
                edges = await (self.edges.list_to(current, edge_type) if reverse else self.edges.list_from(current, edge_type))
                for edge in edges:
                    neighbor_id = edge.from_node_id if reverse else edge.to_node_id
                    if neighbor_id in visited or len(visited) >= max_nodes:
                        continue
                    visited.add(neighbor_id)
                    neighbor = await self.nodes.get(neighbor_id)
                    if neighbor is not None:
                        results.append(neighbor)
                        next_frontier.append(neighbor_id)
            frontier = next_frontier
            if len(visited) >= max_nodes:
                break
        return results

    # -- Connected Components -----------------------------------------------------------------------

    async def connected_components(
        self, node_type: NodeType, edge_type: EdgeType | None = None, max_nodes: int = 2000
    ) -> list[list[KGNodeId]]:
        candidates = (await self.nodes.list_by_type(node_type))[:max_nodes]
        candidate_ids = {n.id for n in candidates}
        parent: dict[KGNodeId, KGNodeId] = {n.id: n.id for n in candidates}

        def find(x: KGNodeId) -> KGNodeId:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: KGNodeId, b: KGNodeId) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for node in candidates:
            for edge in await self.touching_edges(node.id, edge_type):
                other = self.other_end(edge, node.id)
                if other in candidate_ids:
                    union(node.id, other)

        groups: dict[KGNodeId, list[KGNodeId]] = {}
        for node_id in candidate_ids:
            groups.setdefault(find(node_id), []).append(node_id)
        return list(groups.values())

    # -- Timeline / Historical Queries ----------------------------------------------------------------

    async def at_time(self, node_id: KGNodeId, as_of: datetime, depth: int = 1, max_nodes: int = 200) -> Subgraph:
        """Graph state as of a past instant: same expansion as `neighborhood`, but an edge is
        only followed if it was valid at ``as_of`` (``valid_from <= as_of <
        valid_to-or-still-open``) — the Historical Snapshot / Historical Traversal /
        Historical Replay capability."""
        full = await self.neighborhood(node_id, depth=depth, max_nodes=max_nodes)
        valid_edges = tuple(e for e in full.edges if self._valid_at(e, as_of))
        touched_ids = {node_id}
        for edge in valid_edges:
            touched_ids.add(edge.from_node_id)
            touched_ids.add(edge.to_node_id)
        valid_nodes = tuple(n for n in full.nodes if n.id in touched_ids)
        return Subgraph(nodes=valid_nodes, edges=valid_edges, truncated=full.truncated)

    def _valid_at(self, edge: KGEdge, as_of: datetime) -> bool:
        valid_from = _ensure_aware(edge.valid_from, as_of)
        if valid_from > as_of:
            return False
        if edge.valid_to is None:
            return True
        return _ensure_aware(edge.valid_to, as_of) > as_of

    async def edge_history(self, node_id: KGNodeId, edge_type: EdgeType | None = None) -> list[KGEdge]:
        """Every edge that has ever touched ``node_id`` — current and closed — sorted oldest
        first, i.e. the Entity Evolution / relationship-history view. `list_from`/`list_to`
        already return both current and historical (``valid_to`` IS NOT NULL) rows."""
        all_edges = await self.touching_edges(node_id, edge_type)
        return sorted(all_edges, key=lambda e: e.valid_from)

    # -- Influence Queries -------------------------------------------------------------------------

    async def most_connected(
        self, node_type: NodeType, edge_type: EdgeType, direction: str = "in", limit: int = 10
    ) -> list[tuple[KGNode, int]]:
        """Degree centrality: the ``limit`` nodes of ``node_type`` with the most edges of
        ``edge_type`` pointing at them (``direction="in"``) or originating from them
        (``direction="out"``)."""
        all_edges = await self.edges.list_by_type(edge_type)
        counts: dict[KGNodeId, int] = {}
        for edge in all_edges:
            key = edge.to_node_id if direction == "in" else edge.from_node_id
            counts[key] = counts.get(key, 0) + 1

        ranked = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
        results: list[tuple[KGNode, int]] = []
        for node_id, count in ranked:
            if len(results) >= limit:
                break
            node = await self.nodes.get(node_id)
            if node is not None and node.node_type is node_type:
                results.append((node, count))
        return results
