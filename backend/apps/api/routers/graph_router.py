"""Knowledge Graph API — Milestone 7 (Sports Semantic Intelligence Platform,
docs/api_specification.md `/api/v1/graph`). Exposes exactly the eight categories the
constitution's API section names: Entity Search, Relationship Search, Graph Traversal,
Timeline Queries, Similarity Queries, Context Queries, Neighborhood Queries, Graph Statistics.

Read-only by design — every route here queries the graph built by
``KnowledgeGraphPopulationService``/``EntityReconciliationService``; nothing in this router
mutates it. Gated at ``get_current_user`` (any authenticated user), matching the broad-read
posture already established for RLS (docs/rls.md) — semantic graph data is not
per-organization/per-user sensitive the way billing or PATs are.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import (
    build_context_engine,
    build_graph_monitoring_service,
    build_graph_query_service,
    build_kg_population_service,
    build_semantic_search_service,
    build_similarity_service,
    get_session,
)
from modules.identity.domain.entities import User
from modules.knowledge_graph.application.context_engine import ContextBundle
from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGNodeId, NodeType
from modules.knowledge_graph.ports.graph_query import Subgraph

router = APIRouter(prefix="/api/v1/graph", tags=["knowledge-graph"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_node_id(value: str) -> KGNodeId:
    try:
        return KGNodeId(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid node id: {value}") from None


def _parse_node_type(value: str) -> NodeType:
    try:
        return NodeType(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized node_type '{value}'") from None


def _parse_edge_type(value: str | None) -> EdgeType | None:
    if value is None:
        return None
    try:
        return EdgeType(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized edge_type '{value}'") from None


def _serialize_node(node: KGNode) -> dict:
    return {
        "id": str(node.id),
        "node_type": node.node_type.value,
        "entity_ref": node.entity_ref,
        "attributes": node.attributes,
        "aliases": node.aliases,
        "status": node.status,
        "confidence": node.confidence,
        "version": node.version,
    }


def _serialize_edge(edge: KGEdge) -> dict:
    return {
        "id": str(edge.id),
        "from_node_id": str(edge.from_node_id),
        "to_node_id": str(edge.to_node_id),
        "edge_type": edge.edge_type.value,
        "weight": edge.weight,
        "confidence": edge.confidence,
        "directed": edge.directed,
        "valid_from": edge.valid_from.isoformat(),
        "valid_to": edge.valid_to.isoformat() if edge.valid_to else None,
    }


def _serialize_subgraph(subgraph: Subgraph) -> dict:
    return {
        "nodes": [_serialize_node(n) for n in subgraph.nodes],
        "edges": [_serialize_edge(e) for e in subgraph.edges],
        "truncated": subgraph.truncated,
    }


def _serialize_context(bundle: ContextBundle) -> dict:
    return {
        "subject": _serialize_node(bundle.subject),
        "neighborhood": _serialize_subgraph(bundle.neighborhood),
        "related_by_type": {
            node_type.value: [_serialize_node(n) for n in nodes]
            for node_type, nodes in bundle.related_by_type.items()
        },
        "generated_at": bundle.generated_at.isoformat() if bundle.generated_at else None,
    }


# -- Entity Search --------------------------------------------------------------------------------


@router.get("/entities/{node_type}")
async def search_entities(
    node_type: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    search = build_semantic_search_service(session)
    entities = await search.find_by_node_type(_parse_node_type(node_type))
    return envelope([_serialize_node(n) for n in entities])


@router.get("/entities/{node_type}/{entity_ref}")
async def get_entity(
    node_type: str, entity_ref: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    kg = build_kg_population_service(session)
    node = await kg.nodes.get_by_entity_ref(_parse_node_type(node_type), entity_ref)
    if node is None:
        raise HTTPException(status_code=404, detail="entity not found")
    edges_out = await kg.edges.list_from(node.id)
    edges_in = await kg.edges.list_to(node.id)
    return envelope({**_serialize_node(node), "edges_out": [_serialize_edge(e) for e in edges_out], "edges_in": [_serialize_edge(e) for e in edges_in]})


# -- Relationship Search --------------------------------------------------------------------------


@router.get("/relationships")
async def search_relationships(
    from_id: str = Query(...),
    to_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    search = build_semantic_search_service(session)
    edges = await search.find_relationships_between(_parse_node_id(from_id), _parse_node_id(to_id))
    return envelope([_serialize_edge(e) for e in edges])


# -- Graph Traversal -------------------------------------------------------------------------------


@router.get("/traverse")
async def traverse(
    node_id: str = Query(...),
    edge_type: str = Query(...),
    reverse: bool = Query(default=False),
    max_hops: int = Query(default=5, ge=1, le=20),
    max_nodes: int = Query(default=200, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    query = build_graph_query_service(session)
    nodes = await query.traverse(
        _parse_node_id(node_id), _parse_edge_type(edge_type), reverse=reverse, max_hops=max_hops, max_nodes=max_nodes
    )
    return envelope([_serialize_node(n) for n in nodes])


@router.get("/shortest-path")
async def shortest_path(
    from_id: str = Query(...),
    to_id: str = Query(...),
    edge_type: str | None = Query(default=None),
    max_depth: int = Query(default=6, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    query = build_graph_query_service(session)
    path = await query.shortest_path(
        _parse_node_id(from_id), _parse_node_id(to_id), edge_type=_parse_edge_type(edge_type), max_depth=max_depth
    )
    if path is None:
        return envelope(None, meta={"connected": False})
    return envelope([_serialize_node(n) for n in path], meta={"connected": True})


# -- Timeline Queries ------------------------------------------------------------------------------


@router.get("/timeline/{node_id}")
async def timeline(
    node_id: str,
    edge_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    query = build_graph_query_service(session)
    history = await query.edge_history(_parse_node_id(node_id), edge_type=_parse_edge_type(edge_type))
    return envelope([_serialize_edge(e) for e in history])


@router.get("/at-time/{node_id}")
async def at_time(
    node_id: str,
    as_of: datetime = Query(...),
    depth: int = Query(default=1, ge=1, le=5),
    max_nodes: int = Query(default=200, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    query = build_graph_query_service(session)
    subgraph = await query.at_time(_parse_node_id(node_id), as_of, depth=depth, max_nodes=max_nodes)
    return envelope(_serialize_subgraph(subgraph))


# -- Similarity Queries -----------------------------------------------------------------------------


@router.get("/similar/{node_id}")
async def similar_entities(
    node_id: str,
    node_type: str = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    similarity_service = build_similarity_service(session)
    ranked = await similarity_service.similarity_port.most_similar(
        _parse_node_id(node_id), _parse_node_type(node_type), limit=limit, min_score=min_score
    )
    return envelope([{"node": _serialize_node(n), "score": score} for n, score in ranked])


# -- Context Queries --------------------------------------------------------------------------------


@router.get("/context/{node_id}")
async def context(
    node_id: str,
    depth: int = Query(default=1, ge=1, le=5),
    max_nodes: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    engine = build_context_engine(session)
    bundle = await engine.build_context(_parse_node_id(node_id), _now(), depth=depth, max_nodes=max_nodes)
    if bundle is None:
        raise HTTPException(status_code=404, detail="entity not found")
    return envelope(_serialize_context(bundle))


# -- Neighborhood Queries ---------------------------------------------------------------------------


@router.get("/neighborhood/{node_id}")
async def neighborhood(
    node_id: str,
    depth: int = Query(default=1, ge=1, le=5),
    edge_type: str | None = Query(default=None),
    max_nodes: int = Query(default=200, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    query = build_graph_query_service(session)
    subgraph = await query.neighborhood(
        _parse_node_id(node_id), depth=depth, edge_type=_parse_edge_type(edge_type), max_nodes=max_nodes
    )
    return envelope(_serialize_subgraph(subgraph))


# -- Graph Statistics -------------------------------------------------------------------------------


@router.get("/statistics")
async def statistics(session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    monitoring = build_graph_monitoring_service(session)
    snapshot = await monitoring.snapshot()
    return envelope(
        {
            "node_count": snapshot.node_count,
            "edge_count": snapshot.edge_count,
            "nodes_by_type": {nt.value: count for nt, count in snapshot.nodes_by_type.items()},
            "edges_by_type": {et.value: count for et, count in snapshot.edges_by_type.items()},
            "avg_population_seconds": snapshot.avg_population_seconds,
            "avg_traversal_seconds": snapshot.avg_traversal_seconds,
            "cache_hit_ratio": snapshot.cache_hit_ratio,
            "entity_resolution_accuracy": snapshot.entity_resolution_accuracy,
            "merge_count": snapshot.merge_count,
            "duplicate_count": snapshot.duplicate_count,
        }
    )
