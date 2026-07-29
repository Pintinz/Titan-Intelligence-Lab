"""Tests FeatureStoreEnrichmentService against the same in-memory fakes
tests/unit/modules/features/conftest.py already defines for testing FeatureRegistrationService/
FeatureStoreService directly — reusing that module's own established test doubles rather than
introducing a second way to fake the Feature Store's ports."""

from __future__ import annotations

from datetime import datetime, timezone

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.features.domain.value_objects import EntityType, FeatureKey
from modules.intelligence.application.feature_store_enrichment_service import (
    FEATURE_CATALOG,
    FeatureStoreEnrichmentService,
)
from tests.unit.modules.features.conftest import (
    InMemoryFeatureDefinitionRepository,
    InMemoryFeatureLineageRepository,
    InMemoryFeatureValueRepository,
    InMemoryFeatureVersionRepository,
    InMemoryOnlineFeatureStore,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _service() -> FeatureStoreEnrichmentService:
    definitions = InMemoryFeatureDefinitionRepository()
    lineage_service = FeatureLineageService(lineage=InMemoryFeatureLineageRepository(), definitions=definitions)
    registration = FeatureRegistrationService(
        definitions=definitions, versions=InMemoryFeatureVersionRepository(), lineage=lineage_service
    )
    store = FeatureStoreService(
        definitions=definitions, offline=InMemoryFeatureValueRepository(), online=InMemoryOnlineFeatureStore()
    )
    return FeatureStoreEnrichmentService(registration=registration, store=store)


async def test_ensure_registered_creates_every_catalog_feature_as_active():
    service = _service()

    await service.ensure_registered(T0)

    for feature_key in FEATURE_CATALOG:
        definition = await service.registration.definitions.get(FeatureKey(feature_key))
        assert definition is not None
        assert definition.status.value == "active"


async def test_ensure_registered_is_idempotent():
    service = _service()

    await service.ensure_registered(T0)
    await service.ensure_registered(T0)  # second call must not raise or duplicate

    definitions = await service.registration.definitions.list_all()
    assert len(definitions) == len(FEATURE_CATALOG)


async def test_publish_injury_impact_writes_active_feature_value():
    service = _service()
    await service.ensure_registered(T0)

    value = await service.publish_injury_impact("player-1", 0.8, T0)

    assert value.value == 0.8
    assert value.entity_type == EntityType.PLAYER
    assert value.entity_id == "player-1"


async def test_publish_source_reliability_writes_team_scoped_value():
    service = _service()
    await service.ensure_registered(T0)

    value = await service.publish_source_reliability("team-1", 0.65, T0)

    assert value.entity_type == EntityType.TEAM
    assert value.value == 0.65


async def test_publish_weather_impact_is_venue_scoped():
    service = _service()
    await service.ensure_registered(T0)

    value = await service.publish_weather_impact("venue-1", 0.4, T0)

    assert value.entity_type == EntityType.VENUE


async def test_publish_fails_before_registration():
    service = _service()

    from modules.features.application.feature_store_service import FeatureNotFoundError

    try:
        await service.publish_injury_impact("player-1", 0.5, T0)
        assert False, "expected FeatureNotFoundError"
    except FeatureNotFoundError:
        pass


async def test_every_named_publisher_round_trips():
    service = _service()
    await service.ensure_registered(T0)

    results = []
    results.append(await service.publish_injury_impact("p1", 0.5, T0))
    results.append(await service.publish_transfer_stability("t1", 0.5, T0))
    results.append(await service.publish_manager_stability("t1", 0.5, T0))
    results.append(await service.publish_community_momentum("t1", 0.2, T0))
    results.append(await service.publish_news_momentum("t1", 0.2, T0))
    results.append(await service.publish_squad_availability("t1", 0.9, T0))
    results.append(await service.publish_media_pressure("t1", 0.3, T0))
    results.append(await service.publish_travel_fatigue("t1", 0.1, T0))
    results.append(await service.publish_weather_impact("v1", 0.1, T0))
    results.append(await service.publish_source_reliability("t1", 0.7, T0))

    assert len(results) == len(FEATURE_CATALOG)
    assert all(r is not None for r in results)
