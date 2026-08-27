"""Re-resolves every already-stored `NewsEvent`'s entities against the Knowledge Graph, for events
extracted before the entity-resolution audit fix (2026-08-27, `population_service.py`) started
writing real `aliases`. `EventExtractionService.extract_and_record` only ever resolves entities
ONCE, at extraction time — a `NewsEvent` whose entities failed to resolve back then stays
permanently `UNRESOLVED` even after the underlying KG bug is fixed and the alias backfill
(`backfill_kg_node_aliases.py`) runs, unless something re-attempts the lookup against the
now-fixed graph. This script is that one-time catch-up, for events already sitting in the
database — no Gemini call needed, since an `UNRESOLVED` `ResolvedNewsEntity.ref` already holds the
original raw mention text (`EventExtractionService`'s own contract: `ref = mention.text` when
unresolved), only the graph lookup needs to run again.

Idempotent and safe to re-run: an event with every entity already `RESOLVED` is left untouched: an
event that still can't resolve some entity keeps trying next run (e.g. once more KG nodes exist).
Never invents an entity or a resolution — an entity that still doesn't match any alias stays
`UNRESOLVED`, honestly.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from modules.intelligence.domain.entities import ResolvedNewsEntity
from modules.intelligence.domain.value_objects import EntityResolutionStatus
from modules.knowledge_graph.application.entity_resolution_service import EntityResolutionService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemyNewsEventRepository
from modules.knowledge_graph.infrastructure.persistence.repositories import SqlAlchemyKGEdgeRepository, SqlAlchemyKGNodeRepository
from modules.intelligence.ports.repositories import NewsEventRepositoryPort

_LIST_TIMELINE_LIMIT = 5000  # comfortably above any real dev/production event count today


def _rebuild_affected_entity_refs(resolved_entities: tuple[ResolvedNewsEntity, ...]) -> tuple[str, ...]:
    """The exact RESOLVED-only, deduped, order-preserving contract `EventExtractionService.
    extract_and_record` already establishes for `affected_entity_refs` — kept in sync here so a
    re-resolved event's `affected_entity_refs` (what `NewsMarketImpactEngine.list_for_entity`
    actually queries against) reflects any newly-resolved entity too."""
    return tuple(dict.fromkeys(e.ref for e in resolved_entities if e.status is EntityResolutionStatus.RESOLVED))


async def reresolve_all(events: NewsEventRepositoryPort, resolver: EntityResolutionService) -> dict[str, int]:
    """Pure logic over injected ports — real repos in `main()`, test doubles in tests."""
    checked = 0
    updated = 0
    newly_resolved_entities = 0

    for event in await events.list_timeline(limit=_LIST_TIMELINE_LIMIT):
        unresolved = [e for e in event.resolved_entities if e.status is EntityResolutionStatus.UNRESOLVED]
        if not unresolved:
            continue
        checked += 1

        changed = False
        new_resolved_entities = list(event.resolved_entities)
        for i, entry in enumerate(new_resolved_entities):
            if entry.status is not EntityResolutionStatus.UNRESOLVED or entry.node_type is None:
                continue
            try:
                node_type = NodeType(entry.node_type)
            except ValueError:
                continue
            matches = await resolver.find_by_alias(node_type, entry.ref)
            if not matches:
                continue
            new_resolved_entities[i] = ResolvedNewsEntity(
                ref=str(matches[0].id), node_type=entry.node_type, status=EntityResolutionStatus.RESOLVED,
            )
            changed = True
            newly_resolved_entities += 1

        if not changed:
            continue

        event.resolved_entities = tuple(new_resolved_entities)
        event.affected_entity_refs = _rebuild_affected_entity_refs(event.resolved_entities)
        await events.record(event)
        updated += 1

    return {"events_checked": checked, "events_updated": updated, "entities_newly_resolved": newly_resolved_entities}


async def main() -> None:
    from apps.api.composition import get_engine

    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        events = SqlAlchemyNewsEventRepository(session=session)
        nodes = SqlAlchemyKGNodeRepository(session=session)
        edges = SqlAlchemyKGEdgeRepository(session=session)
        population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
        resolver = EntityResolutionService(nodes=nodes, edges=edges, population=population)

        results = await reresolve_all(events, resolver)
        await session.commit()

        print("News event re-resolution:")
        print(f"  events with at least one unresolved entity: {results['events_checked']}")
        print(f"  events updated (>=1 entity newly resolved): {results['events_updated']}")
        print(f"  entities newly resolved: {results['entities_newly_resolved']}")


if __name__ == "__main__":
    asyncio.run(main())
