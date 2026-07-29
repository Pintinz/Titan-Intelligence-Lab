from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.domain.entities import FeatureDefinition, FeatureLineageEdge
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _definition(key: str) -> FeatureDefinition:
    return FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey(key),
        name=key,
        description="d",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="x",
        data_type=FeatureDataType.FLOAT,
        owner="test",
        entity_type=EntityType.TEAM,
        status=FeatureStatus.ACTIVE,
    )


@pytest.fixture
def service(lineage_repo, definition_repo):
    return FeatureLineageService(lineage=lineage_repo, definitions=definition_repo)


@pytest.mark.asyncio
async def test_validate_dependencies_passes_for_existing_features(service, definition_repo):
    await definition_repo.upsert(_definition("football.team.base_stat"))

    errors = await service.validate_dependencies(
        FeatureKey("football.team.derived_stat"), (FeatureKey("football.team.base_stat"),)
    )

    assert errors == []


@pytest.mark.asyncio
async def test_validate_dependencies_rejects_unregistered_dependency(service):
    errors = await service.validate_dependencies(FeatureKey("a"), (FeatureKey("nonexistent"),))

    assert any("not a registered feature" in e for e in errors)


@pytest.mark.asyncio
async def test_validate_dependencies_rejects_self_dependency(service, definition_repo):
    await definition_repo.upsert(_definition("a"))

    errors = await service.validate_dependencies(FeatureKey("a"), (FeatureKey("a"),))

    assert any("cannot depend on itself" in e for e in errors)


@pytest.mark.asyncio
async def test_validate_dependencies_rejects_direct_cycle(service, definition_repo, lineage_repo):
    await definition_repo.upsert(_definition("a"))
    await definition_repo.upsert(_definition("b"))
    # b already depends on a
    await lineage_repo.add_edge(FeatureLineageEdge(feature_key=FeatureKey("b"), depends_on_feature_key=FeatureKey("a")))

    # now registering a -> depends on b would create a cycle (a->b->a)
    errors = await service.validate_dependencies(FeatureKey("a"), (FeatureKey("b"),))

    assert any("cycle" in e for e in errors)


@pytest.mark.asyncio
async def test_validate_dependencies_rejects_transitive_cycle(service, definition_repo, lineage_repo):
    for key in ("a", "b", "c"):
        await definition_repo.upsert(_definition(key))
    await lineage_repo.add_edge(FeatureLineageEdge(feature_key=FeatureKey("b"), depends_on_feature_key=FeatureKey("a")))
    await lineage_repo.add_edge(FeatureLineageEdge(feature_key=FeatureKey("c"), depends_on_feature_key=FeatureKey("b")))

    # a -> depends on c would create a->c->b->a cycle
    errors = await service.validate_dependencies(FeatureKey("a"), (FeatureKey("c"),))

    assert any("cycle" in e for e in errors)


@pytest.mark.asyncio
async def test_dependency_closure_is_transitive(service, definition_repo, lineage_repo):
    for key in ("a", "b", "c"):
        await definition_repo.upsert(_definition(key))
    await lineage_repo.add_edge(FeatureLineageEdge(feature_key=FeatureKey("a"), depends_on_feature_key=FeatureKey("b")))
    await lineage_repo.add_edge(FeatureLineageEdge(feature_key=FeatureKey("b"), depends_on_feature_key=FeatureKey("c")))

    closure = await service.dependency_closure(FeatureKey("a"))

    assert closure == {FeatureKey("b"), FeatureKey("c")}


@pytest.mark.asyncio
async def test_record_dependencies_adds_edges(service, definition_repo, lineage_repo):
    await definition_repo.upsert(_definition("a"))
    await definition_repo.upsert(_definition("b"))

    await service.record_dependencies(FeatureKey("a"), (FeatureKey("b"),))

    deps = await lineage_repo.list_dependencies(FeatureKey("a"))
    assert deps == [FeatureKey("b")]
