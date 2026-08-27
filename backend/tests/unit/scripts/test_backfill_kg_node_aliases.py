"""Tests for `scripts/backfill_kg_node_aliases.py`'s `backfill_aliases` — the one-time catch-up for
KG nodes populated before the entity-resolution audit fix (`population_service.py`, 2026-08-27)
started writing `aliases` at write time. See that script's own module docstring for the underlying
defect this closes: `EntityResolutionService.find_by_alias` (the lookup `EntityExtractionService`
uses to resolve a free-text news mention) searches `aliases` exclusively, never `attributes`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base
from modules.knowledge_graph.infrastructure.persistence.repositories import SqlAlchemyKGNodeRepository
from scripts.backfill_kg_node_aliases import backfill_aliases

T0 = datetime(2026, 8, 27, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://", execution_options={"schema_translate_map": {"knowledge_graph": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def test_backfills_team_alias_from_name_attribute(sqlite_session):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    await nodes.upsert(
        KGNode(id=KGNodeId(uuid4()), node_type=NodeType.TEAM, entity_ref="team-1", attributes={"name": "Arsenal"})
    )

    results = await backfill_aliases(nodes, T0)

    assert results["team"] == 1
    node = await nodes.get_by_entity_ref(NodeType.TEAM, "team-1")
    assert node.aliases == ["Arsenal"]


async def test_leaves_already_aliased_nodes_untouched(sqlite_session):
    """Idempotent, and never overwrites an alias list a caller already curated (e.g. one that
    includes nicknames beyond the plain `attributes["name"]`)."""
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    await nodes.upsert(
        KGNode(
            id=KGNodeId(uuid4()), node_type=NodeType.TEAM, entity_ref="team-1",
            attributes={"name": "Manchester City"}, aliases=["Manchester City", "Man City"],
        )
    )

    results = await backfill_aliases(nodes, T0)

    assert results.get("team", 0) == 0
    node = await nodes.get_by_entity_ref(NodeType.TEAM, "team-1")
    assert node.aliases == ["Manchester City", "Man City"]


async def test_skips_a_node_with_no_name_attribute_rather_than_fabricating_one(sqlite_session):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    await nodes.upsert(KGNode(id=KGNodeId(uuid4()), node_type=NodeType.TEAM, entity_ref="team-1", attributes={}))

    results = await backfill_aliases(nodes, T0)

    assert results.get("team", 0) == 0
    assert results["_skipped_no_name"] == 1
    node = await nodes.get_by_entity_ref(NodeType.TEAM, "team-1")
    assert node.aliases == []


async def test_country_backfills_from_name_or_code(sqlite_session):
    """Country nodes carry both `name` and `code` — either is a real, usable alias, never both
    required."""
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    await nodes.upsert(
        KGNode(id=KGNodeId(uuid4()), node_type=NodeType.COUNTRY, entity_ref="GB", attributes={"code": "GB", "name": "United Kingdom"})
    )

    results = await backfill_aliases(nodes, T0)

    assert results["country"] == 1
    node = await nodes.get_by_entity_ref(NodeType.COUNTRY, "GB")
    assert node.aliases == ["GB", "United Kingdom"]


async def test_backfills_every_resolvable_node_type_in_one_pass(sqlite_session):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    for node_type, entity_ref in (
        (NodeType.TEAM, "team-1"), (NodeType.PLAYER, "player-1"), (NodeType.VENUE, "venue-1"),
        (NodeType.COMPETITION, "comp-1"), (NodeType.ORGANIZATION, "org-1"),
    ):
        await nodes.upsert(
            KGNode(id=KGNodeId(uuid4()), node_type=node_type, entity_ref=entity_ref, attributes={"name": f"Real {entity_ref}"})
        )

    results = await backfill_aliases(nodes, T0)

    assert results["team"] == 1
    assert results["player"] == 1
    assert results["venue"] == 1
    assert results["competition"] == 1
    assert results["organization"] == 1


async def test_running_twice_is_idempotent(sqlite_session):
    nodes = SqlAlchemyKGNodeRepository(session=sqlite_session)
    await nodes.upsert(
        KGNode(id=KGNodeId(uuid4()), node_type=NodeType.TEAM, entity_ref="team-1", attributes={"name": "Arsenal"})
    )

    first = await backfill_aliases(nodes, T0)
    second = await backfill_aliases(nodes, T0)

    assert first["team"] == 1
    assert second.get("team", 0) == 0
