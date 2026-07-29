"""Online feature store port — low-latency (Redis-backed in production) read cache for feature
values. Never the source of truth; see FeatureValue docstring. A value here always has a TTL —
there is no "permanent" online entry, since staleness must always be bounded
(docs/feature_catalog.md §7 "Freshness Rules")."""

from __future__ import annotations

from typing import Protocol

from modules.features.domain.entities import FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureKey


class OnlineFeatureStorePort(Protocol):
    async def get(
        self, feature_key: FeatureKey, entity_type: EntityType, entity_id: str
    ) -> FeatureValue | None: ...

    async def set(self, value: FeatureValue, ttl_seconds: int) -> None: ...

    async def delete(self, feature_key: FeatureKey, entity_type: EntityType, entity_id: str) -> None: ...
