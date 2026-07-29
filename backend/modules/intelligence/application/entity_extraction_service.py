"""Entity Extraction — Named Entity Recognition + Knowledge Graph linking (Milestone 8
"ENTITY EXTRACTION": "Automatically identify Players, Teams, Competitions, Leagues, Coaches,
Officials, Venues, Countries, Sponsors, Organizations... Link every extracted entity to the
Knowledge Graph.").

Every mention `TextIntelligenceProviderPort.extract_entities` identifies is resolved against the
existing graph via `EntityResolutionService.find_by_alias` (Milestone 7) — reused, not
reimplemented, per "using existing Graph APIs only." An unresolved mention (no matching alias)
is returned as such rather than autonomously creating a new Knowledge Graph node for every NER
hit — node creation for a confirmed new entity is `KnowledgeGraphEnrichmentService`'s job
(Milestone 8), which applies its own confidence/source-reliability gating before writing
anything to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.intelligence.ports.text_intelligence_provider import TextIntelligenceProviderPort
from modules.knowledge_graph.application.entity_resolution_service import EntityResolutionService
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType

# Free-form NER labels (Gemini/mock output) -> the ontology's NodeType (docs/ontology.md).
# "Leagues"/"Sponsors" from the spec map onto existing NodeType members (Competition/
# Organization respectively) rather than introducing new ones for a synonym.
ENTITY_TYPE_TO_NODE_TYPE = {
    "player": NodeType.PLAYER,
    "team": NodeType.TEAM,
    "competition": NodeType.COMPETITION,
    "league": NodeType.COMPETITION,
    "coach": NodeType.COACH,
    "manager": NodeType.MANAGER,
    "official": NodeType.OFFICIAL,
    "referee": NodeType.REFEREE,
    "venue": NodeType.VENUE,
    "country": NodeType.COUNTRY,
    "organization": NodeType.ORGANIZATION,
    "sponsor": NodeType.ORGANIZATION,
}


@dataclass(frozen=True)
class ResolvedEntityMention:
    """One NER hit, with a Knowledge Graph link if `EntityResolutionService` found a match.
    ``node_type`` is ``None`` when the NER label doesn't map to a known ontology member (e.g. a
    generic "unknown" mention) — extraction confidence alone, no resolution attempted."""

    text: str
    node_type: NodeType | None
    kg_node_id: KGNodeId | None
    confidence: float


@dataclass
class EntityExtractionService:
    text_intelligence: TextIntelligenceProviderPort
    entity_resolution: EntityResolutionService

    async def extract_and_link(self, text: str) -> list[ResolvedEntityMention]:
        mentions = await self.text_intelligence.extract_entities(text)
        resolved: list[ResolvedEntityMention] = []
        for mention in mentions:
            node_type = ENTITY_TYPE_TO_NODE_TYPE.get(mention.entity_type)
            kg_node_id: KGNodeId | None = None
            if node_type is not None:
                matches = await self.entity_resolution.find_by_alias(node_type, mention.text)
                if matches:
                    kg_node_id = matches[0].id
            resolved.append(
                ResolvedEntityMention(
                    text=mention.text, node_type=node_type, kg_node_id=kg_node_id, confidence=mention.confidence
                )
            )
        return resolved
