"""Knowledge Graph Enrichment (Milestone 8 "KNOWLEDGE GRAPH ENRICHMENT": "Automatically create:
Nodes, Edges, Relationships, Temporal Events, Aliases, Context, Historical references — using
existing Graph APIs only."). Every operation here composes Milestone 5/7's existing
`KnowledgeGraphPopulationService` and `TemporalGraphService` — nothing new is added to the
Knowledge Graph module itself; this service is purely a caller.

Temporal Events and Historical references fall out of the existing machinery for free once an
edge exists: `TemporalGraphService.supersede_edge` records the transition, and
`GraphQueryService.edge_history`/`entity_evolution` (Milestone 7) already answer "what changed
and when" for any edge this service creates — nothing new needed here. "Context" is likewise
already served by `ContextEngine` (Milestone 7) reading whatever this service writes; this
service's job is only the write side.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from modules.intelligence.application.entity_extraction_service import ResolvedEntityMention
from modules.intelligence.domain.entities import NewsEvent
from modules.intelligence.domain.value_objects import NewsEventType
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.application.temporal_graph_service import TemporalGraphService
from modules.knowledge_graph.domain.value_objects import EdgeType, KGNodeId, NodeType
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "unknown"


def _looks_like_node_id(ref: str) -> KGNodeId | None:
    try:
        return KGNodeId(UUID(ref))
    except ValueError:
        return None


@dataclass(frozen=True)
class EnrichmentResult:
    nodes_created: tuple[str, ...] = ()
    aliases_added: tuple[str, ...] = ()
    edges_created: tuple[str, ...] = ()


@dataclass
class KnowledgeGraphEnrichmentService:
    population: KnowledgeGraphPopulationService
    temporal: TemporalGraphService
    nodes: KGNodeRepositoryPort

    async def enrich_from_mentions(
        self, mentions: list[ResolvedEntityMention], now: datetime, source: str = "news_intelligence"
    ) -> EnrichmentResult:
        """Nodes + Aliases: an already-resolved mention contributes its literal text as a new
        alias on the existing node (a news article may call a player by a nickname the graph
        doesn't have yet); an unresolved mention with a known ontology type becomes a brand new
        node, discovered purely from news content."""
        nodes_created: list[str] = []
        aliases_added: list[str] = []
        for mention in mentions:
            if mention.node_type is None:
                continue
            if mention.kg_node_id is not None:
                node = await self.nodes.get(mention.kg_node_id)
                if node is not None and mention.text not in node.aliases:
                    await self.population.upsert_node(node.node_type, node.entity_ref, now=now, aliases=[mention.text])
                    aliases_added.append(mention.text)
            else:
                entity_ref = _slugify(mention.text)
                await self.population.upsert_node(
                    mention.node_type, entity_ref, now=now, aliases=[mention.text],
                    source=source, confidence=mention.confidence,
                )
                nodes_created.append(entity_ref)
        return EnrichmentResult(nodes_created=tuple(nodes_created), aliases_added=tuple(aliases_added))

    async def enrich_from_event(self, event: NewsEvent, now: datetime) -> EnrichmentResult:
        """Edges + Relationships + Temporal Events: maps a subset of `NewsEventType`s to
        unambiguous graph relationship changes. Event types without a safe, unambiguous target
        (e.g. INJURY with no linked match/venue) create no edge — better to enrich nothing than
        guess a relationship the article didn't actually establish."""
        refs = [r for r in (_looks_like_node_id(ref) for ref in event.affected_entity_refs) if r is not None]
        resolved_nodes = [n for n in [await self.nodes.get(ref) for ref in refs] if n is not None]

        if event.event_type is NewsEventType.TRANSFER:
            return await self._transfer_edge(resolved_nodes, now)
        if event.event_type is NewsEventType.MANAGER_CHANGE:
            return await self._manager_change_edge(resolved_nodes, now)
        return EnrichmentResult()

    async def _transfer_edge(self, resolved_nodes, now: datetime) -> EnrichmentResult:
        player = next((n for n in resolved_nodes if n.node_type is NodeType.PLAYER), None)
        new_team = next((n for n in resolved_nodes if n.node_type is NodeType.TEAM), None)
        if player is None or new_team is None:
            return EnrichmentResult()

        current_edges = [
            e for e in await self.temporal.query.edges.list_from(player.id, EdgeType.PLAYS_FOR) if e.is_current
        ]
        if current_edges:
            await self.temporal.supersede_edge(
                current_edges[0], player, new_team, EdgeType.PLAYS_FOR, now, source="news_intelligence"
            )
        else:
            await self.population.upsert_edge(player, new_team, EdgeType.PLAYS_FOR, now, source="news_intelligence")
        return EnrichmentResult(edges_created=(f"{player.entity_ref}->{new_team.entity_ref}:plays_for",))

    async def _manager_change_edge(self, resolved_nodes, now: datetime) -> EnrichmentResult:
        team = next((n for n in resolved_nodes if n.node_type is NodeType.TEAM), None)
        coach = next((n for n in resolved_nodes if n.node_type in (NodeType.COACH, NodeType.MANAGER)), None)
        if team is None or coach is None:
            return EnrichmentResult()

        await self.population.upsert_edge(team, coach, EdgeType.COACHED_BY, now, source="news_intelligence")
        return EnrichmentResult(edges_created=(f"{team.entity_ref}->{coach.entity_ref}:coached_by",))
