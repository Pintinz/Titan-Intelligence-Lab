"""Semantic Search — named retrieval APIs over the Graph Query Engine (docs/ontology.md §6,
Milestone 7: "Implement semantic retrieval APIs" with a literal list of example queries). Every
method here is a thin, domain-named wrapper around `GraphQueryService`'s traversal primitives —
no new query capability is introduced, only vocabulary a caller (Prediction Engine, News
Engine, AI Assistant) can call without knowing the underlying edge-direction conventions
established in `population_service.py` (e.g. PLAYS_FOR is player -> team, COACHED_BY is
subject -> coach).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGNodeId, NodeType
from modules.knowledge_graph.ports.graph_query import Subgraph


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — duplicated
    per-module rather than imported, matching the existing convention across this codebase."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass
class SemanticSearchService:
    query: GraphQueryService

    async def find_players_for_team(self, team_id: KGNodeId) -> list[KGNode]:
        """"Find every player who played for Team X" — PLAYS_FOR is player -> team, so this
        walks the edge in reverse."""
        return await self.query.traverse(team_id, EdgeType.PLAYS_FOR, reverse=True)

    async def find_teams_coached_by(self, coach_id: KGNodeId) -> list[KGNode]:
        """COACHED_BY is subject -> coach, so teams coached by ``coach_id`` are found in reverse."""
        return await self.query.traverse(coach_id, EdgeType.COACHED_BY, reverse=True)

    async def find_matches_coached_by(self, coach_id: KGNodeId) -> list[KGNode]:
        """"Find every match coached by Coach Y" — two hops: teams coached by Y, then every
        match those teams were INVOLVED_IN."""
        teams = await self.find_teams_coached_by(coach_id)
        matches: dict[KGNodeId, KGNode] = {}
        for team in teams:
            for match in await self.query.traverse(team.id, EdgeType.INVOLVED_IN):
                matches[match.id] = match
        return list(matches.values())

    async def find_rivals(self, team_id: KGNodeId) -> list[KGNode]:
        """"Find all rivals of Liverpool" — RIVAL_OF is undirected (`directed=False`), so both
        sides of the edge are followed."""
        rivals = []
        for edge in await self.query.touching_edges(team_id, EdgeType.RIVAL_OF):
            other = await self.query.nodes.get(self.query.other_end(edge, team_id))
            if other is not None:
                rivals.append(other)
        return rivals

    async def find_injuries_before(self, match_id: KGNodeId, before: datetime) -> list[KGEdge]:
        """"Find every injury before Match Z" — all INJURED_IN edges touching ``match_id`` whose
        ``valid_from`` predates ``before`` (typically the match's own kickoff time)."""
        edges = await self.query.touching_edges(match_id, EdgeType.INJURED_IN)
        return [e for e in edges if _ensure_aware(e.valid_from, before) < before]

    async def find_transfers_involving(self, team_id: KGNodeId) -> list[KGEdge]:
        """"Find all transfers involving Team X" — TRANSFERRED_TO touches a team on either the
        origin or destination side."""
        return await self.query.touching_edges(team_id, EdgeType.TRANSFERRED_TO)

    async def find_relationships_between(self, node_a: KGNodeId, node_b: KGNodeId) -> list[KGEdge]:
        """"Find relationships between two players" — every edge directly connecting the pair,
        of any type, not a path through intermediaries (that's `GraphQueryService.shortest_path`)."""
        return [
            edge for edge in await self.query.touching_edges(node_a, None)
            if self.query.other_end(edge, node_a) == node_b
        ]

    async def find_context_around_fixture(
        self, fixture_id: KGNodeId, depth: int = 1, max_nodes: int = 200
    ) -> Subgraph:
        """"Find contextual entities around a fixture" — delegates to neighborhood expansion;
        the richer, narrative version of this lives in `ContextEngine.context_for_fixture`."""
        return await self.query.neighborhood(fixture_id, depth=depth, max_nodes=max_nodes)

    async def find_by_node_type(self, node_type: NodeType) -> list[KGNode]:
        """Plain entity-type listing — the base case every other semantic query composes with."""
        return await self.query.nodes.list_by_type(node_type)
