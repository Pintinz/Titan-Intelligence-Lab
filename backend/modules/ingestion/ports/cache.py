"""Generic distributed cache port for the ingestion module — "Synchronization Cache" and
"Rate Limit Cache" (docs/roadmap.md Milestone 5 "Redis Integration"). Deliberately generic
(unlike ``modules.features.ports.online_store.OnlineFeatureStorePort``, which is typed to
``FeatureValue``) since ingestion caches heterogeneous things: sync results, provider ETags,
throttle counters.
"""

from __future__ import annotations

from typing import Any, Protocol


class SyncCachePort(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    async def delete(self, key: str) -> None: ...
