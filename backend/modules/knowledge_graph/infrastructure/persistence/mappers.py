from __future__ import annotations

from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGEdgeId, KGNodeId, NodeType
from modules.knowledge_graph.infrastructure.persistence.models import KGEdgeModel, KGNodeModel


def node_to_domain(model: KGNodeModel) -> KGNode:
    return KGNode(
        id=KGNodeId(model.id), node_type=NodeType(model.node_type),
        entity_ref=model.entity_ref, attributes=model.attributes,
        provider_refs=dict(model.provider_refs or {}), aliases=list(model.aliases or []),
        source=model.source, version=model.version, status=model.status,
        confidence=model.confidence, created_at=model.created_at, updated_at=model.updated_at,
        merged_into=model.merged_into,
    )


def node_to_model(entity: KGNode, model: KGNodeModel | None = None) -> KGNodeModel:
    model = model or KGNodeModel(id=entity.id.value)
    model.node_type = entity.node_type.value
    model.entity_ref = entity.entity_ref
    model.attributes = entity.attributes
    model.provider_refs = entity.provider_refs
    model.aliases = entity.aliases
    model.source = entity.source
    model.version = entity.version
    model.status = entity.status
    model.confidence = entity.confidence
    model.created_at = entity.created_at
    model.updated_at = entity.updated_at
    model.merged_into = entity.merged_into
    return model


def edge_to_domain(model: KGEdgeModel) -> KGEdge:
    return KGEdge(
        id=KGEdgeId(model.id), from_node_id=KGNodeId(model.from_node_id), to_node_id=KGNodeId(model.to_node_id),
        edge_type=EdgeType(model.edge_type), valid_from=model.valid_from, weight=model.weight,
        attributes=model.attributes, valid_to=model.valid_to,
        confidence=model.confidence, source=model.source, version=model.version, directed=model.directed,
    )


def edge_to_model(entity: KGEdge, model: KGEdgeModel | None = None) -> KGEdgeModel:
    model = model or KGEdgeModel(id=entity.id.value)
    model.from_node_id = entity.from_node_id.value
    model.to_node_id = entity.to_node_id.value
    model.edge_type = entity.edge_type.value
    model.weight = entity.weight
    model.attributes = entity.attributes
    model.valid_from = entity.valid_from
    model.valid_to = entity.valid_to
    model.confidence = entity.confidence
    model.source = entity.source
    model.version = entity.version
    model.directed = entity.directed
    return model
