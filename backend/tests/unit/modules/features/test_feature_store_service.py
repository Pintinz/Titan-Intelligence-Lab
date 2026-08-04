from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import redis.exceptions

from modules.features.application.feature_store_service import (
    FeatureNotActiveError,
    FeatureNotFoundError,
    FeatureStoreService,
)
from modules.features.domain.entities import FeatureDefinition
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
    QualityFlag,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _definition(status=FeatureStatus.ACTIVE, expected_range=None, data_type=FeatureDataType.FLOAT) -> FeatureDefinition:
    return FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey("football.team.possession_pct"),
        name="Possession %",
        description="d",
        sport_code="football",
        category=FeatureCategory.TEAM,
        formula="possession_seconds / match_seconds",
        data_type=data_type,
        owner="data-team",
        entity_type=EntityType.TEAM,
        status=status,
        expected_range=expected_range,
    )


@pytest.fixture
def service(definition_repo, value_repo, online_store):
    return FeatureStoreService(definitions=definition_repo, offline=value_repo, online=online_store)


@pytest.mark.asyncio
async def test_write_requires_registered_feature(service):
    with pytest.raises(FeatureNotFoundError):
        await service.write("does.not.exist", EntityType.TEAM, "team-1", 0.5, T0)


@pytest.mark.asyncio
async def test_write_requires_active_status_by_default(service, definition_repo):
    await definition_repo.upsert(_definition(status=FeatureStatus.DRAFT))

    with pytest.raises(FeatureNotActiveError):
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.5, T0)


@pytest.mark.asyncio
async def test_write_allows_draft_when_require_active_is_false(service, definition_repo):
    await definition_repo.upsert(_definition(status=FeatureStatus.DRAFT))

    value = await service.write(
        "football.team.possession_pct", EntityType.TEAM, "team-1", 0.5, T0, require_active=False
    )

    assert value.value == 0.5


@pytest.mark.asyncio
async def test_write_flags_type_mismatch(service, definition_repo):
    await definition_repo.upsert(_definition())

    value = await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", "not-a-number", T0)

    assert value.quality_flags == (QualityFlag.TYPE_MISMATCH,)


@pytest.mark.asyncio
async def test_write_flags_out_of_range(service, definition_repo):
    await definition_repo.upsert(_definition(expected_range=(0.0, 1.0)))

    value = await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 1.5, T0)

    assert value.quality_flags == (QualityFlag.OUT_OF_RANGE,)


@pytest.mark.asyncio
async def test_write_ok_within_range(service, definition_repo):
    await definition_repo.upsert(_definition(expected_range=(0.0, 1.0)))

    value = await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.55, T0)

    assert value.quality_flags == (QualityFlag.OK,)


@pytest.mark.asyncio
async def test_write_persists_to_both_offline_and_online(service, definition_repo, value_repo, online_store):
    await definition_repo.upsert(_definition())

    await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)

    assert len(value_repo.store) == 1
    cached = await online_store.get(FeatureKey("football.team.possession_pct"), EntityType.TEAM, "team-1")
    assert cached is not None and cached.value == 0.6


@pytest.mark.asyncio
async def test_read_prefers_online_cache(service, definition_repo, online_store):
    await definition_repo.upsert(_definition())
    await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)
    # mutate the cached copy directly to prove read comes from online, not offline
    cached = await online_store.get(FeatureKey("football.team.possession_pct"), EntityType.TEAM, "team-1")
    from dataclasses import replace

    await online_store.set(replace(cached, value=0.99), ttl_seconds=60)

    read = await service.read("football.team.possession_pct", EntityType.TEAM, "team-1")

    assert read.value == 0.99


@pytest.mark.asyncio
async def test_read_falls_back_to_offline_on_cache_miss(service, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)
    # simulate cache eviction — online store is untouched but we read via a fresh empty online store
    empty_online = type(service.online)()
    service_with_empty_cache = FeatureStoreService(definitions=service.definitions, offline=value_repo, online=empty_online)

    read = await service_with_empty_cache.read("football.team.possession_pct", EntityType.TEAM, "team-1")

    assert read is not None
    assert read.value == 0.6


@pytest.mark.asyncio
async def test_read_returns_none_when_nothing_written(service, definition_repo):
    await definition_repo.upsert(_definition())

    assert await service.read("football.team.possession_pct", EntityType.TEAM, "team-1") is None


@dataclass
class _UnreachableOnlineFeatureStore:
    """Stands in for a Redis-backed online store whose connection is down — every call raises
    the same `redis.exceptions.RedisError` subclass a real dead connection would."""

    store: dict = field(default_factory=dict)

    async def get(self, feature_key, entity_type, entity_id):
        raise redis.exceptions.ConnectionError("connection refused")

    async def set(self, value, ttl_seconds):
        raise redis.exceptions.ConnectionError("connection refused")

    async def delete(self, feature_key, entity_type, entity_id):
        raise redis.exceptions.ConnectionError("connection refused")


@pytest.mark.asyncio
async def test_write_persists_offline_even_when_online_cache_is_unreachable(service, definition_repo, value_repo):
    """Audit fix 2026-08-02: a Redis outage during write() used to raise straight out of the
    method and roll back the whole (already-durable) offline write along with it. The durable
    record must survive a cache outage — that's the module's own documented contract."""
    await definition_repo.upsert(_definition())
    unreachable = FeatureStoreService(definitions=definition_repo, offline=value_repo, online=_UnreachableOnlineFeatureStore())

    value = await unreachable.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)

    assert value.value == 0.6
    assert len(value_repo.store) == 1


@pytest.mark.asyncio
async def test_read_falls_back_to_offline_when_online_cache_is_unreachable(service, definition_repo, value_repo):
    """A cache outage on read() must degrade exactly like a cache miss, not raise."""
    await definition_repo.upsert(_definition())
    healthy = FeatureStoreService(definitions=definition_repo, offline=value_repo, online=service.online)
    await healthy.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)

    unreachable = FeatureStoreService(definitions=definition_repo, offline=value_repo, online=_UnreachableOnlineFeatureStore())
    read = await unreachable.read("football.team.possession_pct", EntityType.TEAM, "team-1")

    assert read is not None
    assert read.value == 0.6


def test_is_stale():
    value = _write_value_stub()
    assert FeatureStoreService.is_stale(value, T0 + timedelta(hours=2), max_staleness_seconds=3600)
    assert not FeatureStoreService.is_stale(value, T0 + timedelta(minutes=30), max_staleness_seconds=3600)


def _write_value_stub():
    from modules.features.domain.entities import FeatureValue
    from modules.features.domain.value_objects import FeatureValueId

    return FeatureValue(
        id=FeatureValueId(uuid4()),
        feature_key=FeatureKey("football.team.possession_pct"),
        entity_type=EntityType.TEAM,
        entity_id="team-1",
        as_of=T0,
        value=0.5,
    )
