"""Tests the real RedisFeatureStore adapter against fakeredis — the actual adapter code runs,
only the transport is faked (docs/decisions.md ADR-008 pattern, applied to a cache)."""

from datetime import datetime, timezone
from uuid import uuid4

import fakeredis
import pytest

from modules.features.domain.entities import FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureKey, FeatureValueId, QualityFlag
from modules.features.infrastructure.online.redis_feature_store import RedisFeatureStore

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def store(redis_client):
    return RedisFeatureStore(client=redis_client)


def _value(value=0.6) -> FeatureValue:
    return FeatureValue(
        id=FeatureValueId(uuid4()),
        feature_key=FeatureKey("football.team.possession_pct"),
        entity_type=EntityType.TEAM,
        entity_id="team-1",
        as_of=T0,
        value=value,
        quality_flags=(QualityFlag.OK,),
    )


@pytest.mark.asyncio
async def test_get_returns_none_for_missing_key(store):
    result = await store.get(FeatureKey("football.team.possession_pct"), EntityType.TEAM, "team-1")

    assert result is None


@pytest.mark.asyncio
async def test_set_then_get_round_trips(store):
    value = _value(0.72)

    await store.set(value, ttl_seconds=60)
    fetched = await store.get(value.feature_key, value.entity_type, value.entity_id)

    assert fetched is not None
    assert fetched.value == pytest.approx(0.72)
    assert fetched.as_of == T0
    assert fetched.quality_flags == (QualityFlag.OK,)


@pytest.mark.asyncio
async def test_set_applies_ttl(store, redis_client):
    value = _value()

    await store.set(value, ttl_seconds=120)

    ttl = await redis_client.ttl(f"feature:{value.feature_key.value}:{value.entity_type.value}:{value.entity_id}")
    assert 0 < ttl <= 120


@pytest.mark.asyncio
async def test_delete_removes_entry(store):
    value = _value()
    await store.set(value, ttl_seconds=60)

    await store.delete(value.feature_key, value.entity_type, value.entity_id)

    assert await store.get(value.feature_key, value.entity_type, value.entity_id) is None


@pytest.mark.asyncio
async def test_different_entities_are_stored_independently(store):
    await store.set(_value(0.3), ttl_seconds=60)
    other = FeatureValue(
        id=FeatureValueId(uuid4()),
        feature_key=FeatureKey("football.team.possession_pct"),
        entity_type=EntityType.TEAM,
        entity_id="team-2",
        as_of=T0,
        value=0.8,
    )
    await store.set(other, ttl_seconds=60)

    team1 = await store.get(FeatureKey("football.team.possession_pct"), EntityType.TEAM, "team-1")
    team2 = await store.get(FeatureKey("football.team.possession_pct"), EntityType.TEAM, "team-2")

    assert team1.value == pytest.approx(0.3)
    assert team2.value == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_preserves_value_type_across_round_trip(store):
    int_value = FeatureValue(
        id=FeatureValueId(uuid4()),
        feature_key=FeatureKey("football.player.goals_season"),
        entity_type=EntityType.PLAYER,
        entity_id="player-1",
        as_of=T0,
        value=17,
    )

    await store.set(int_value, ttl_seconds=60)
    fetched = await store.get(int_value.feature_key, int_value.entity_type, int_value.entity_id)

    assert fetched.value == 17
    assert isinstance(fetched.value, int)
