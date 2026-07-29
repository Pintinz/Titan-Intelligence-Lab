"""Graph Population extensions — Batch Writes, Relationship Discovery, Relationship Deletion,
Historical Replay (docs/ontology.md §9, Milestone 7: "Extend Milestone 5 population engine.
Support Incremental Updates, Merge, Relationship Discovery, Relationship Updates, Relationship
Deletion, Duplicate Prevention, Historical Replay.").

Incremental Updates, Relationship Updates, and Duplicate Prevention are already satisfied by
`KnowledgeGraphPopulationService.upsert_node`/`upsert_edge`'s idempotent-in-place behavior
(Milestone 5), and Merge by `EntityResolutionService` (Milestone 7) — this service adds only
what Milestone 5 didn't already cover: batching multiple upserts behind one call, inferring
new edges from existing graph structure, hard-deleting an erroneous edge (as opposed to
`TemporalGraphService.close_edge`'s historical-preserving close), and replaying a batch of
historical population events in true chronological order regardless of the order they're
handed in (so out-of-sequence backfills don't corrupt `version`/`valid_from`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import combinations

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGEdgeId, KGNodeId, NodeType
from modules.knowledge_graph.ports.repositories import KGEdgeRepositoryPort


@dataclass(frozen=True)
class NodeSpec:
    node_type: NodeType
    entity_ref: str
    attributes: dict | None = None
    provider_refs: dict | None = None
    aliases: list[str] | None = None


@dataclass(frozen=True)
class NodeReplayEvent:
    at: datetime
    node_type: NodeType
    entity_ref: str
    attributes: dict | None = None
    provider_refs: dict | None = None
    aliases: list[str] | None = None


@dataclass(frozen=True)
class EdgeReplayEvent:
    at: datetime
    from_type: NodeType
    from_ref: str
    to_type: NodeType
    to_ref: str
    edge_type: EdgeType
    weight: float = 1.0
    attributes: dict | None = None
    directed: bool = True


@dataclass
class GraphPopulationBatchService:
    population: KnowledgeGraphPopulationService
    query: GraphQueryService
    edges: KGEdgeRepositoryPort

    # -- Batch Writes ----------------------------------------------------------------------------

    async def batch_upsert_nodes(self, specs: list[NodeSpec], now: datetime) -> list[KGNode]:
        return [
            await self.population.upsert_node(
                spec.node_type, spec.entity_ref, spec.attributes, now=now,
                provider_refs=spec.provider_refs, aliases=spec.aliases,
            )
            for spec in specs
        ]

    # -- Relationship Discovery --------------------------------------------------------------------

    async def discover_teammate_relationships(self, team_id: KGNodeId, now: datetime) -> list[KGEdge]:
        """Infers TEAMMATE_OF between every pair of players currently PLAYS_FOR the same team —
        a real, bounded, non-ML relationship-discovery pass (the Similarity Engine's graph-
        structural heuristic covers the general case; this covers the specific one the
        constitution names explicitly under Relationship Engine)."""
        players = await self.query.traverse(team_id, EdgeType.PLAYS_FOR, reverse=True)
        return [
            await self.population.upsert_edge(a, b, EdgeType.TEAMMATE_OF, now, directed=False)
            for a, b in combinations(players, 2)
        ]

    # -- Relationship Deletion -----------------------------------------------------------------------

    async def delete_edge(self, edge_id: KGEdgeId) -> bool:
        """Hard delete for an erroneous edge — distinct from `TemporalGraphService.close_edge`,
        which preserves the edge as historical record of a genuine relationship that ended."""
        return await self.edges.delete(edge_id)

    # -- Historical Replay -------------------------------------------------------------------------

    async def replay(self, events: list[NodeReplayEvent | EdgeReplayEvent]) -> None:
        """Applies a batch of population events in ascending ``at`` order regardless of the
        order ``events`` was handed in — a historical backfill delivered out of sequence still
        produces the same graph state as if it had been ingested in real time."""
        for event in sorted(events, key=lambda e: e.at):
            if isinstance(event, NodeReplayEvent):
                await self.population.upsert_node(
                    event.node_type, event.entity_ref, event.attributes, now=event.at,
                    provider_refs=event.provider_refs, aliases=event.aliases,
                )
            else:
                from_node = await self.population.upsert_node(event.from_type, event.from_ref, now=event.at)
                to_node = await self.population.upsert_node(event.to_type, event.to_ref, now=event.at)
                await self.population.upsert_edge(
                    from_node, to_node, event.edge_type, event.at,
                    weight=event.weight, attributes=event.attributes, directed=event.directed,
                )
