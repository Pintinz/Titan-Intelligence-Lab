"""Temporal Graph — Relationship Versioning, Time-valid Edges, Historical Snapshots, Historical
Traversal, Entity Evolution (docs/ontology.md §8, Milestone 7).

Time-valid Edges and Historical Snapshots/Traversal are already carried by `KGEdge.valid_from`/
`valid_to` and `GraphQueryService.at_time`/`edge_history` (Milestone 7's Graph Query Engine
work) — this service adds the one operation `population_service.py`'s `upsert_edge` docstring
explicitly deferred: `supersede_edge`, the deliberate "close one relationship, open a new one"
transition (e.g. a transfer ending a player's PLAYS_FOR at their old team and starting one at
their new team), as opposed to `upsert_edge`'s in-place idempotent update of an unchanged
relationship.

Entity Evolution is derived from existing edge history rather than a new node-versioning table:
the graph is relational, not event-sourced (docs/decisions.md ADR-005/ADR-029's same
scope posture), so a node's "evolution" is expressed as the timeline of its relationships
opening and closing — a real, queryable answer without introducing per-node snapshot storage
this milestone doesn't otherwise need.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGEdgeId, KGNodeId
from modules.knowledge_graph.ports.repositories import KGEdgeRepositoryPort


@dataclass(frozen=True)
class TemporalEvent:
    edge: KGEdge
    kind: str  # "opened" | "closed"
    at: datetime


@dataclass
class TemporalGraphService:
    query: GraphQueryService
    edges: KGEdgeRepositoryPort
    population: KnowledgeGraphPopulationService

    async def close_edge(self, edge_id: KGEdgeId, now: datetime) -> KGEdge | None:
        return await self.edges.close(edge_id, now)

    async def supersede_edge(
        self,
        old_edge: KGEdge,
        from_node: KGNode,
        to_node: KGNode,
        edge_type: EdgeType,
        now: datetime,
        weight: float = 1.0,
        attributes: dict | None = None,
        confidence: float = 1.0,
        source: str = "ingestion",
        directed: bool = True,
    ) -> KGEdge:
        """Closes ``old_edge`` at ``now`` and opens a new current edge from ``from_node`` to
        ``to_node`` — a distinct, explicit relationship change, not `upsert_edge`'s in-place
        update of an unchanged one. ``old_edge`` need not touch the same node pair as the new
        edge (the transfer case: old edge is player->old_team, new edge is player->new_team)."""
        await self.edges.close(old_edge.id, now)
        return await self.population.upsert_edge(
            from_node, to_node, edge_type, now,
            weight=weight, attributes=attributes, confidence=confidence, source=source, directed=directed,
        )

    async def entity_evolution(self, node_id: KGNodeId, edge_type: EdgeType | None = None) -> list[TemporalEvent]:
        """The chronological timeline of ``node_id``'s relationships opening and (if since
        superseded/closed) closing — Entity Evolution derived from `GraphQueryService.edge_history`."""
        history = await self.query.edge_history(node_id, edge_type)
        events: list[TemporalEvent] = []
        for edge in history:
            events.append(TemporalEvent(edge=edge, kind="opened", at=edge.valid_from))
            if edge.valid_to is not None:
                events.append(TemporalEvent(edge=edge, kind="closed", at=edge.valid_to))
        events.sort(key=lambda event: event.at)
        return events
