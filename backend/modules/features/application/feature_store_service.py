"""Unified read/write facade over the offline (Postgres, audited) and online (Redis, low-
latency) feature stores (docs/feature_catalog.md §7). Writes always go to both — offline first,
since it's the durable record; online is a cache and losing it just means the next read falls
back to offline. Reads prefer online, falling back to offline on a cache miss.

Audit fix (2026-08-02): the online cache write was never actually wrapped to honor this module's
own documented "losing it just means falling back to offline" contract — a Redis connection
failure raised straight out of `write()` and rolled back the whole (already-durable) offline
write along with it. Now caught narrowly (`redis.exceptions.RedisError`, the base class covering
connection/timeout failures) and skipped: the durable record is already written by the time the
cache write is attempted, so a cache outage degrades reads (next read falls back to offline, per
this module's own docstring), it must never lose a write.

Phase 2 audit fix (2026-08-18): catching the exception stopped the write from being lost, but did
nothing about the *latency* — every `write()` call independently re-attempted a fresh Redis
connection and paid the full `socket_connect_timeout` (2s) before falling back, with no memory of
"Redis was just unreachable a moment ago." `EntityReconciliationService.reconcile_fixture`
(football) calls into several calculators that each write multiple features per fixture — with
Redis down, a single fixture reconciliation was measured taking ~12s (6 features × ~2s each) that
should take milliseconds, turning a normal historical resync (hundreds of fixtures) into a
multi-hour operation that looked indistinguishable from an infinite hang when observed for only a
few minutes at a time. `circuit_breaker` (optional, same `CircuitBreaker` class
`SportsProviderRouter` already uses for provider calls — no new breaker implementation) now
short-circuits `online.set()` entirely once Redis has failed a few times in a row, instead of
paying the full timeout on every single subsequent call; it self-heals (`HALF_OPEN` -> `CLOSED`)
the same way the existing provider circuit breaker already does, so a Redis that comes back
up is used again automatically. `None` (the default) preserves every existing caller/test's
behavior exactly as before this fix — this is purely an opt-in latency guard, not a behavior
change to what gets written or when a write is considered to have succeeded."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import redis.exceptions

from modules.admin.application.circuit_breaker import CircuitBreaker
from modules.features.domain.entities import FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureDataType, FeatureKey, QualityFlag, FeatureValueId
from modules.features.ports.online_store import OnlineFeatureStorePort
from modules.features.ports.repositories import FeatureDefinitionRepositoryPort, FeatureValueRepositoryPort

_ONLINE_STORE_BREAKER_KEY = "feature_store:online"


class FeatureNotFoundError(KeyError):
    pass


class FeatureNotActiveError(ValueError):
    pass


_TYPE_CHECKS = {
    FeatureDataType.INT: lambda v: isinstance(v, int) and not isinstance(v, bool),
    FeatureDataType.FLOAT: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    FeatureDataType.BOOL: lambda v: isinstance(v, bool),
    FeatureDataType.STRING: lambda v: isinstance(v, str),
    FeatureDataType.CATEGORICAL: lambda v: isinstance(v, str),
}


@dataclass
class FeatureStoreService:
    definitions: FeatureDefinitionRepositoryPort
    offline: FeatureValueRepositoryPort
    online: OnlineFeatureStorePort
    # Phase 2 audit fix — see module docstring. Optional/defaulted so every existing caller/test
    # keeps working unchanged; production wiring (composition.py) passes the same process-wide
    # CircuitBreaker instance SportsProviderRouter already uses, keyed separately.
    circuit_breaker: CircuitBreaker | None = None

    async def write(
        self,
        feature_key: str,
        entity_type: EntityType,
        entity_id: str,
        value: float | int | str | bool,
        as_of: datetime,
        *,
        require_active: bool = True,
    ) -> FeatureValue:
        key = feature_key if isinstance(feature_key, FeatureKey) else FeatureKey(feature_key)
        definition = await self.definitions.get(key)
        if definition is None:
            raise FeatureNotFoundError(str(key))
        if require_active and not definition.is_consumable():
            raise FeatureNotActiveError(
                f"'{key}' is {definition.status.value}, not ACTIVE — cannot write production values"
            )

        record = FeatureValue(
            id=FeatureValueId(uuid4()),
            feature_key=key,
            entity_type=entity_type,
            entity_id=entity_id,
            as_of=as_of,
            value=value,
            quality_flags=self._validate(definition, value),
        )
        await self.offline.record(record)  # durable record written regardless of quality flags
        if self.circuit_breaker is None or self.circuit_breaker.allow_request(_ONLINE_STORE_BREAKER_KEY, as_of):
            try:
                await self.online.set(record, ttl_seconds=definition.online_ttl_seconds)
                if self.circuit_breaker is not None:
                    self.circuit_breaker.record_success(_ONLINE_STORE_BREAKER_KEY)
            except redis.exceptions.RedisError:
                # cache unavailable — the durable offline record above already succeeded
                if self.circuit_breaker is not None:
                    self.circuit_breaker.record_failure(_ONLINE_STORE_BREAKER_KEY, as_of)
        # else: breaker OPEN — skip the attempt entirely rather than re-paying the connect
        # timeout on a Redis we already know is down; degrades exactly like a caught
        # RedisError (offline record already durable), just without the latency.
        return record

    async def read(
        self, feature_key: str, entity_type: EntityType, entity_id: str
    ) -> FeatureValue | None:
        key = feature_key if isinstance(feature_key, FeatureKey) else FeatureKey(feature_key)
        try:
            cached = await self.online.get(key, entity_type, entity_id)
        except redis.exceptions.RedisError:
            cached = None  # cache unavailable — degrades exactly like a cache miss
        if cached is not None:
            return cached
        return await self.offline.get_latest(key, entity_type, entity_id)

    async def read_as_of(
        self, feature_key: str, entity_type: EntityType, entity_id: str, as_of: datetime
    ) -> FeatureValue | None:
        """Milestone 4 point-in-time retrieval — the counterpart to `read()` for historical
        reconstruction (backtesting, training-dataset assembly, re-deriving what a past
        prediction should have seen). Deliberately bypasses `online` entirely: the Redis cache
        only ever holds the single most-recent value per key (`online.set`/`.get` have no
        version/as-of dimension), so it can never safely answer "what did we know at time T" —
        going straight to the offline store's `get_as_of` is the only correct path here, not an
        optimization left on the table. Historical feature reconstruction must call this, not
        `read()`, whenever a specific timestamp — not "now" — is the actual question."""
        key = feature_key if isinstance(feature_key, FeatureKey) else FeatureKey(feature_key)
        return await self.offline.get_as_of(key, entity_type, entity_id, as_of)

    @staticmethod
    def is_stale(value: FeatureValue, now: datetime, max_staleness_seconds: int) -> bool:
        return (now - value.as_of).total_seconds() > max_staleness_seconds

    def _validate(self, definition, value) -> tuple[QualityFlag, ...]:
        type_check = _TYPE_CHECKS[definition.data_type]
        if not type_check(value):
            return (QualityFlag.TYPE_MISMATCH,)
        if definition.expected_range is not None and isinstance(value, (int, float)):
            low, high = definition.expected_range
            if value < low or value > high:
                return (QualityFlag.OUT_OF_RANGE,)
        return (QualityFlag.OK,)
