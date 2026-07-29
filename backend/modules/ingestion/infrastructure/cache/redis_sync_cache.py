"""Redis-backed generic cache (docs/roadmap.md Milestone 5 "Redis Integration: Distributed
Cache, TTL Policies, Synchronization Cache, Rate Limit Cache"). Same pattern as
``modules.features.infrastructure.online.redis_feature_store.RedisFeatureStore``
(docs/decisions.md ADR-008 applied to a cache) — real ``redis.asyncio`` code, tested against
``fakeredis`` so it runs in CI without a live Redis instance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

_KEY_PREFIX = "synccache:"


@dataclass
class RedisSyncCache:
    client: Redis

    async def get(self, key: str) -> Any | None:
        raw = await self.client.get(f"{_KEY_PREFIX}{key}")
        return None if raw is None else json.loads(raw)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self.client.set(f"{_KEY_PREFIX}{key}", json.dumps(value), ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self.client.delete(f"{_KEY_PREFIX}{key}")
