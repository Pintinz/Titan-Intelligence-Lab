"""Knowledge Graph entities (docs/ontology.md, docs/database_schema.md §5).

Milestone 7 adds entity-metadata fields required by the Sports Ontology spec (Provider
References, Aliases, Source, Version, Status, Confidence, Created/Updated) and edge-metadata
fields (Confidence, Source, Version, Direction). Every new field carries a default so every
existing `KnowledgeGraphPopulationService.populate_*` call site (Milestone 5) continues to
construct valid nodes/edges unchanged — additive, not breaking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.knowledge_graph.domain.value_objects import EdgeType, KGEdgeId, KGNodeId, NodeType


@dataclass
class KGNode:
    id: KGNodeId
    node_type: NodeType
    entity_ref: str  # stringified id of the domain entity this node represents
    attributes: dict = field(default_factory=dict)
    provider_refs: dict = field(default_factory=dict)  # {"api_football": "12345", ...}
    aliases: list[str] = field(default_factory=list)
    source: str = "ingestion"
    version: int = 1
    status: str = "active"  # active | merged | deprecated — see EntityResolutionService
    confidence: float = 1.0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    merged_into: str | None = None  # stringified KGNodeId this node was merged into, if any

    @property
    def is_merged(self) -> bool:
        return self.status == "merged"


@dataclass
class KGEdge:
    id: KGEdgeId
    from_node_id: KGNodeId
    to_node_id: KGNodeId
    edge_type: EdgeType
    valid_from: datetime
    weight: float = 1.0
    attributes: dict = field(default_factory=dict)
    valid_to: datetime | None = None
    confidence: float = 1.0
    source: str = "ingestion"
    version: int = 1
    directed: bool = True  # False for inherently symmetric relationships (e.g. TEAMMATE_OF)

    @property
    def is_current(self) -> bool:
        return self.valid_to is None
