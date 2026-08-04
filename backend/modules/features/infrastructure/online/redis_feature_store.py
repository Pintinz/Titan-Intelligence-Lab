"""Redis-backed OnlineFeatureStorePort implementation. Accepts any client implementing the
``redis.asyncio.Redis`` interface — production wires a real one; tests wire
``fakeredis.aioredis.FakeRedis`` so the real adapter code is what gets exercised, not a parallel
test-only implementation (same pattern as mock-vs-real provider adapters, docs/decisions.md
ADR-008, just applied to a cache instead of an external API)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis, from_url

from modules.features.domain.entities import FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureKey, FeatureValueId, QualityFlag
from modules.features.infrastructure.persistence.mappers import decode_feature_value, encode_feature_value


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TITANIQ_REDIS_")

    url: str


@lru_cache
def get_redis_settings() -> RedisSettings:
    return RedisSettings()  # type: ignore[call-arg]  # raises if TITANIQ_REDIS_URL is unset


def build_redis_client(url: str | None = None) -> Redis:
    """A short connect/command timeout matters here specifically because this client backs a
    store this module's own docstring calls "just a cache" — `FeatureStoreService` already
    degrades gracefully on `redis.exceptions.RedisError` (writes stay durable via the offline
    store, reads fall back to it), but redis-py's default has no timeout at all, so an
    unreachable Redis (the common local-dev state — no local Redis running) silently turns every
    write/read into a multi-second stall instead of the fast, cheap failure the fallback path is
    built for."""
    return from_url(
        url or get_redis_settings().url, decode_responses=True,
        socket_connect_timeout=2, socket_timeout=2,
    )


def _cache_key(feature_key: FeatureKey, entity_type: EntityType, entity_id: str) -> str:
    return f"feature:{feature_key.value}:{entity_type.value}:{entity_id}"


class RedisFeatureStore:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get(
        self, feature_key: FeatureKey, entity_type: EntityType, entity_id: str
    ) -> FeatureValue | None:
        raw = await self._client.get(_cache_key(feature_key, entity_type, entity_id))
        if raw is None:
            return None
        payload = json.loads(raw)
        return FeatureValue(
            id=FeatureValueId(uuid.UUID(payload["id"])),
            feature_key=feature_key,
            entity_type=entity_type,
            entity_id=entity_id,
            as_of=datetime.fromisoformat(payload["as_of"]),
            value=decode_feature_value(payload["value"]),
            quality_flags=tuple(QualityFlag(f) for f in payload["quality_flags"]),
        )

    async def set(self, value: FeatureValue, ttl_seconds: int) -> None:
        payload = {
            "id": str(value.id.value),
            "as_of": value.as_of.isoformat(),
            "value": encode_feature_value(value.value),
            "quality_flags": [f.value for f in value.quality_flags],
        }
        await self._client.set(
            _cache_key(value.feature_key, value.entity_type, value.entity_id),
            json.dumps(payload),
            ex=ttl_seconds,
        )

    async def delete(self, feature_key: FeatureKey, entity_type: EntityType, entity_id: str) -> None:
        await self._client.delete(_cache_key(feature_key, entity_type, entity_id))
