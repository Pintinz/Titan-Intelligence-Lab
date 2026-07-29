"""Cached node repository — Graph Performance ("Caching"), Milestone 7. Decorates any
`KGNodeRepositoryPort` with the same generic `SyncCachePort` Milestone 5's ingestion module
already built (docs/decisions.md ADR-008: mock-first port, real Redis adapter tested against
fakeredis) — no new caching concept introduced, the KG module reuses existing infrastructure
rather than inventing a parallel cache.

Read-through: `get`/`get_by_entity_ref` check the cache first and populate it on a miss. The
write path (`upsert`) invalidates both key shapes for the affected node so a stale cached value
is never served after a write. `list_by_type` is deliberately NOT cached — it is a bulk fan-out
query, not a single-entity lookup, and caching an unbounded/growing per-type list would need its
own invalidation strategy this milestone doesn't need yet.

`hits`/`misses`/`hit_ratio` feed Graph Monitoring's "Cache Hit Ratio" metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from modules.ingestion.ports.cache import SyncCachePort
from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort


def _node_to_cache_value(node: KGNode) -> dict:
    return {
        "id": str(node.id.value),
        "node_type": node.node_type.value,
        "entity_ref": node.entity_ref,
        "attributes": node.attributes,
        "provider_refs": node.provider_refs,
        "aliases": node.aliases,
        "source": node.source,
        "version": node.version,
        "status": node.status,
        "confidence": node.confidence,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
        "merged_into": node.merged_into,
    }


def _cache_value_to_node(value: dict) -> KGNode:
    return KGNode(
        id=KGNodeId(UUID(value["id"])),
        node_type=NodeType(value["node_type"]),
        entity_ref=value["entity_ref"],
        attributes=value["attributes"],
        provider_refs=value["provider_refs"],
        aliases=value["aliases"],
        source=value["source"],
        version=value["version"],
        status=value["status"],
        confidence=value["confidence"],
        created_at=datetime.fromisoformat(value["created_at"]) if value["created_at"] else None,
        updated_at=datetime.fromisoformat(value["updated_at"]) if value["updated_at"] else None,
        merged_into=value["merged_into"],
    )


@dataclass
class CachedKGNodeRepository:
    inner: KGNodeRepositoryPort
    cache: SyncCachePort
    ttl_seconds: int = 300
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)

    async def get(self, node_id: KGNodeId) -> KGNode | None:
        key = f"kgnode:id:{node_id.value}"
        cached = await self.cache.get(key)
        if cached is not None:
            self.hits += 1
            return _cache_value_to_node(cached)
        self.misses += 1
        node = await self.inner.get(node_id)
        if node is not None:
            await self.cache.set(key, _node_to_cache_value(node), self.ttl_seconds)
        return node

    async def get_by_entity_ref(self, node_type: NodeType, entity_ref: str) -> KGNode | None:
        key = f"kgnode:ref:{node_type.value}:{entity_ref}"
        cached = await self.cache.get(key)
        if cached is not None:
            self.hits += 1
            return _cache_value_to_node(cached)
        self.misses += 1
        node = await self.inner.get_by_entity_ref(node_type, entity_ref)
        if node is not None:
            await self.cache.set(key, _node_to_cache_value(node), self.ttl_seconds)
        return node

    async def list_by_type(self, node_type: NodeType) -> list[KGNode]:
        return await self.inner.list_by_type(node_type)

    async def upsert(self, node: KGNode) -> KGNode:
        result = await self.inner.upsert(node)
        await self.cache.delete(f"kgnode:id:{result.id.value}")
        await self.cache.delete(f"kgnode:ref:{result.node_type.value}:{result.entity_ref}")
        return result

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
