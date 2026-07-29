"""Entity Resolution — provider mapping, alias resolution, duplicate detection, and canonical
merge (docs/ontology.md §4, Milestone 7).

Provider-ref/alias lookups filter in Python over `KGNodeRepositoryPort.list_by_type` results
rather than a dedicated indexed query — the same "BFS not recursive CTE" scope call the Graph
Query Engine already made (docs/decisions.md ADR-029): correct and portable at this
milestone's traffic scale, revisit with a real index (e.g. a `provider_ref_index`-style table,
mirroring `modules.ingestion`'s ADR-021 pattern) only if it measurably doesn't scale.

Merge is non-destructive: a duplicate node is never deleted. `merge()` marks it
``status="merged"`` with a `merged_into` pointer (Historical Identity), redirects its edges onto
the canonical node by creating equivalent edges from/to the canonical (via the same idempotent
`upsert_edge` the population service already uses — composed in, not reimplemented), and folds
its aliases/provider_refs into the canonical so future lookups resolve directly. The
duplicate's own original edges are left untouched as historical record of what it used to
represent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from uuid import UUID

from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.knowledge_graph.ports.repositories import KGEdgeRepositoryPort, KGNodeRepositoryPort


@dataclass(frozen=True)
class DuplicateCandidate:
    node_a: KGNode
    node_b: KGNode
    reason: str  # "shared_alias:<alias>" or "shared_provider_ref:<provider>:<external_id>"


@dataclass
class EntityResolutionService:
    nodes: KGNodeRepositoryPort
    edges: KGEdgeRepositoryPort
    population: KnowledgeGraphPopulationService

    # -- Provider Mapping / Alias Resolution -----------------------------------------------------

    async def find_by_provider_ref(self, node_type: NodeType, provider: str, external_id: str) -> KGNode | None:
        candidates = await self.nodes.list_by_type(node_type)
        for node in candidates:
            if node.provider_refs.get(provider) == external_id and not node.is_merged:
                return node
        return None

    async def find_by_alias(self, node_type: NodeType, alias: str) -> list[KGNode]:
        candidates = await self.nodes.list_by_type(node_type)
        needle = alias.strip().lower()
        return [n for n in candidates if not n.is_merged and needle in {a.lower() for a in n.aliases}]

    async def resolve_canonical(self, node: KGNode) -> KGNode:
        """Follows `merged_into` pointers (always a stringified `KGNodeId`, set by `merge()`
        below) to the current canonical node — a merge chain (A merged into B, B later merged
        into C) resolves all the way to C rather than stopping at the first hop."""
        current = node
        seen = {current.id}
        while current.is_merged and current.merged_into:
            next_node = await self._get_by_id_str(current.merged_into)
            if next_node is None or next_node.id in seen:
                break
            current = next_node
            seen.add(current.id)
        return current

    async def _get_by_id_str(self, node_id_str: str) -> KGNode | None:
        try:
            return await self.nodes.get(KGNodeId(UUID(node_id_str)))
        except ValueError:
            return None

    # -- Duplicate Detection -------------------------------------------------------------------------

    async def detect_duplicates(self, node_type: NodeType) -> list[DuplicateCandidate]:
        candidates = [n for n in await self.nodes.list_by_type(node_type) if not n.is_merged]
        found: list[DuplicateCandidate] = []
        seen_pairs: set[frozenset] = set()

        by_alias: dict[str, list[KGNode]] = {}
        by_provider_ref: dict[tuple[str, str], list[KGNode]] = {}
        for node in candidates:
            for alias in node.aliases:
                by_alias.setdefault(alias.lower(), []).append(node)
            for provider, external_id in node.provider_refs.items():
                by_provider_ref.setdefault((provider, external_id), []).append(node)

        for alias, group in by_alias.items():
            found.extend(_pairs(group, f"shared_alias:{alias}", seen_pairs))
        for (provider, external_id), group in by_provider_ref.items():
            found.extend(_pairs(group, f"shared_provider_ref:{provider}:{external_id}", seen_pairs))
        return found

    # -- Conflict Resolution + Canonical Merge --------------------------------------------------------

    async def merge(self, canonical: KGNode, duplicate: KGNode, now: datetime) -> KGNode:
        if canonical.id == duplicate.id:
            raise ValueError("Cannot merge a node into itself")

        for edge in await self.edges.list_from(duplicate.id):
            target = await self.nodes.get(edge.to_node_id)
            if target is not None:
                await self.population.upsert_edge(
                    canonical, target, edge.edge_type, now, weight=edge.weight, attributes=edge.attributes
                )
        for edge in await self.edges.list_to(duplicate.id):
            source = await self.nodes.get(edge.from_node_id)
            if source is not None:
                await self.population.upsert_edge(
                    source, canonical, edge.edge_type, now, weight=edge.weight, attributes=edge.attributes
                )

        merged_canonical = await self.population.upsert_node(
            canonical.node_type, canonical.entity_ref,
            attributes=canonical.attributes, now=now,
            provider_refs={**duplicate.provider_refs, **canonical.provider_refs},
            aliases=list(set(canonical.aliases) | set(duplicate.aliases) | {duplicate.entity_ref}),
        )

        duplicate.status = "merged"
        duplicate.merged_into = str(canonical.id)
        duplicate.updated_at = now
        await self.nodes.upsert(duplicate)

        return merged_canonical


def _pairs(group: list[KGNode], reason: str, seen_pairs: set[frozenset]) -> list[DuplicateCandidate]:
    results = []
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            pair_key = frozenset({group[i].id, group[j].id})
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            results.append(DuplicateCandidate(node_a=group[i], node_b=group[j], reason=reason))
    return results
