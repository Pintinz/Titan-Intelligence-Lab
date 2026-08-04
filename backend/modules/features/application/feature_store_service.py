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
this module's own docstring), it must never lose a write."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import redis.exceptions

from modules.features.domain.entities import FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureDataType, FeatureKey, QualityFlag, FeatureValueId
from modules.features.ports.online_store import OnlineFeatureStorePort
from modules.features.ports.repositories import FeatureDefinitionRepositoryPort, FeatureValueRepositoryPort


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
        try:
            await self.online.set(record, ttl_seconds=definition.online_ttl_seconds)
        except redis.exceptions.RedisError:
            pass  # cache unavailable — the durable offline record above already succeeded
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
