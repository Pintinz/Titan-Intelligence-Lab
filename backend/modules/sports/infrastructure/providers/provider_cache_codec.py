"""JSON-safe codec for provider response DTOs (POST-M24 Phase 2 "move provider response cache to
shared Redis"). `SportsProviderRouter` used to hold cached responses in a process-local Python
`dict`, so the raw `Provider*Record` dataclasses (and their `datetime`/nested-dataclass fields)
never needed to survive serialization. Moving the cache behind `SyncCachePort` (Redis-backed in
production, see `modules.ingestion.infrastructure.cache.redis_sync_cache.RedisSyncCache`, which
already does its own `json.dumps`/`json.loads` against the Redis wire format) means a cached
value must be a *JSON-safe Python structure* before it reaches `SyncCachePort.set`, and get
reconstructed back into real dataclasses after `SyncCachePort.get` — this module is exactly that
conversion, kept separate from `RedisSyncCache` so that generic port stays generic (it's also used
for sync-run ETags/throttle counters, which are already plain JSON-safe values).

Deliberately a closed whitelist (`_TYPE_REGISTRY`), not a generic "import this dotted path"
deserializer — decoding an unrecognized type tag fails closed (`ProviderCacheDecodeError`) rather
than dynamically importing/instantiating an arbitrary class from a cached payload.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.ports.provider_gateway import (
    ProviderCoachRecord,
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderInjuryRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
    ProviderTransferRecord,
)

_TYPE_REGISTRY: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        ProviderRef,
        ProviderTeamRecord,
        ProviderFixtureRecord,
        ProviderCountryRecord,
        ProviderPlayerRecord,
        ProviderStandingRecord,
        ProviderTeamStatisticsRecord,
        ProviderOddsRecord,
        ProviderLineupSlotRecord,
        ProviderLineupRecord,
        ProviderInjuryRecord,
        ProviderTransferRecord,
        ProviderCoachRecord,
    )
}
_TYPE_KEY = "__provider_type__"
_DATETIME_KEY = "__datetime__"


class ProviderCacheDecodeError(RuntimeError):
    """Raised for a cached payload that doesn't match this codec's contract — a cache entry in
    this shape should never have been written by this codec, so fail closed rather than guess."""


def encode(value: Any) -> Any:
    """A provider-cacheable value (a DTO, a list/tuple of DTOs, `None`, or an already-plain
    value, e.g. the raw dicts a mock adapter's odds/stat payloads use) -> a JSON-safe Python
    structure (only `dict`/`list`/`str`/`int`/`float`/`bool`/`None`) that `SyncCachePort.set` can
    hand straight to `json.dumps`."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
        return {_TYPE_KEY: type(value).__name__, **fields}
    if isinstance(value, datetime):
        return {_DATETIME_KEY: value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    return value


def decode(raw: Any) -> Any:
    """Inverse of `encode` — reconstructs the original dataclasses/datetimes/tuples from the
    JSON-safe structure `SyncCachePort.get` returned. Raises `ProviderCacheDecodeError` for a
    payload this codec didn't write — fail closed rather than return a value silently missing
    its real type."""
    if isinstance(raw, dict):
        if _DATETIME_KEY in raw:
            return datetime.fromisoformat(raw[_DATETIME_KEY])
        type_name = raw.get(_TYPE_KEY)
        if type_name is None:
            return {key: decode(item) for key, item in raw.items()}
        cls = _TYPE_REGISTRY.get(type_name)
        if cls is None:
            raise ProviderCacheDecodeError(f"unrecognized cached provider type {type_name!r}")
        kwargs = {}
        for field in dataclasses.fields(cls):
            value = decode(raw.get(field.name))
            # `tuple[...]`-typed fields (e.g. ProviderLineupRecord.slots) come back as JSON
            # arrays (JSON has no tuple type) — restore the tuple so the reconstructed dataclass
            # matches the original's runtime shape (equality, hashability, ...).
            if isinstance(value, list) and isinstance(field.type, str) and field.type.strip().startswith("tuple"):
                value = tuple(value)
            kwargs[field.name] = value
        return cls(**kwargs)
    if isinstance(raw, list):
        return [decode(item) for item in raw]
    return raw
