"""Redis-backed distributed lock (docs/roadmap.md Milestone 5 "Redis Integration: Distributed
Locks") — prevents two sync workers from processing the same (sport, entity_kind, scope)
concurrently.

Deliberately hand-rolled with plain SET NX EX / GET / DEL rather than redis-py's built-in
``Redis.lock()`` helper: that helper releases via an EVALSHA Lua script, which ``fakeredis``
(our test double, see docs/decisions.md ADR-008) doesn't support, and this codebase has no
other use for Lua scripting that would justify requiring it. The tradeoff: release here is a
GET-then-DEL ownership check, not a single atomic operation — there's a narrow race window
where a lock could expire (TTL), get re-acquired by someone else, and then get wrongly deleted
by the original holder's stale release() call. Acceptable for this use case (sync-scope
mutual exclusion with second-scale operations against a lock TTL usually measured in minutes,
docs/ingestion/sync_orchestrator.py DEFAULT_LOCK_TTL_SECONDS) — not acceptable for a
correctness-critical lock, which this isn't.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from redis.asyncio import Redis

_KEY_PREFIX = "lock:"


@dataclass
class RedisDistributedLock:
    client: Redis
    _tokens: dict[str, str] = field(default_factory=dict)

    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        token = uuid4().hex
        acquired = await self.client.set(f"{_KEY_PREFIX}{key}", token, nx=True, ex=ttl_seconds)
        if acquired:
            self._tokens[key] = token
            return True
        return False

    async def release(self, key: str) -> None:
        token = self._tokens.pop(key, None)
        if token is None:
            return
        redis_key = f"{_KEY_PREFIX}{key}"
        current = await self.client.get(redis_key)
        if current == token:
            await self.client.delete(redis_key)
