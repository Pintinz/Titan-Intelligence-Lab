"""Backfills `KGNode.aliases` for every already-populated node whose alias list is still empty,
from its own `attributes["name"]` (or `attributes["label"]`/`attributes["code"]` for the few node
types that carry a name under a different key — see `_NAME_ATTRIBUTE_KEYS_BY_TYPE`).

Entity-resolution audit fix (2026-08-27): `KnowledgeGraphPopulationService.populate_team`/
`populate_player`/`populate_venue`/`populate_competition`/`populate_organization`/
`populate_country`/`populate_sport` previously wrote a real-world name into `attributes["name"]`
but never into `aliases` — the field `EntityResolutionService.find_by_alias` exclusively searches
when resolving a free-text news mention (e.g. "Manchester City") against the graph. That write-path
bug is now fixed (`population_service.py`), so every *future* reconciliation call self-heals its
own node's aliases — but a node populated before that fix keeps its empty `aliases` list forever
(`upsert_node` only ever adds to the existing list, never rebuilds it from `attributes`). This
script is the one-time catch-up for nodes that already exist: idempotent (only touches nodes with
an empty `aliases` list; already-aliased nodes are left untouched) and safe to re-run.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from modules.knowledge_graph.domain.value_objects import NodeType
from modules.knowledge_graph.infrastructure.persistence.repositories import SqlAlchemyKGNodeRepository
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort

# Only the node types `EntityExtractionService.ENTITY_TYPE_TO_NODE_TYPE` actually resolves news
# mentions against — no point backfilling aliases for node types the news pipeline never looks up.
_NAME_ATTRIBUTE_KEYS_BY_TYPE: dict[NodeType, tuple[str, ...]] = {
    NodeType.TEAM: ("name",),
    NodeType.PLAYER: ("name",),
    NodeType.VENUE: ("name",),
    NodeType.COMPETITION: ("name",),
    NodeType.ORGANIZATION: ("name",),
    NodeType.COUNTRY: ("name", "code"),
}


async def backfill_aliases(nodes: KGNodeRepositoryPort, now: datetime) -> dict[str, int]:
    """The pure backfill logic, independent of how `nodes` is wired — real `SqlAlchemyKGNode
    Repository` in production (`main()` below), an in-memory/sqlite test double in tests. Returns
    `{node_type_value: count_backfilled}`, plus a `"_skipped_no_name"` entry for nodes that had
    no name attribute at all to backfill from (never fabricated)."""
    updated_by_type: dict[str, int] = {}
    skipped_no_name = 0
    for node_type, name_keys in _NAME_ATTRIBUTE_KEYS_BY_TYPE.items():
        for node in await nodes.list_by_type(node_type):
            if node.aliases:
                continue
            names = [node.attributes.get(key) for key in name_keys]
            names = [n for n in names if n]
            if not names:
                skipped_no_name += 1
                continue
            node.aliases = sorted(set(names))
            node.updated_at = now
            await nodes.upsert(node)
            updated_by_type[node_type.value] = updated_by_type.get(node_type.value, 0) + 1
    updated_by_type["_skipped_no_name"] = skipped_no_name
    return updated_by_type


async def main() -> None:
    from apps.api.composition import get_engine

    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        nodes = SqlAlchemyKGNodeRepository(session=session)
        results = await backfill_aliases(nodes, datetime.now(timezone.utc))
        await session.commit()

        print("KG node alias backfill:")
        for node_type, count in results.items():
            if node_type == "_skipped_no_name":
                continue
            print(f"  {node_type}: {count} nodes backfilled")
        print(f"  skipped (no name attribute to backfill from): {results['_skipped_no_name']}")


if __name__ == "__main__":
    asyncio.run(main())
