"""In-memory `DatasetRepositoryPort` — the dev/offline-test/composition-wiring default
(docs/decisions.md ADR-008 mock-first/adapter-swap posture). Migration 0023 already created a
SQL `datasets` table for when a production need for persistence-across-restarts shows up; until
then this mirrors `PlattScalingCalibrator`'s same "real in-memory implementation, not a stub" posture.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.predictions.domain.dataset import Dataset, DatasetId
from modules.predictions.domain.value_objects import MarketId


@dataclass
class InMemoryDatasetRepository:
    _store: dict = field(default_factory=dict)  # DatasetId -> Dataset

    async def get(self, dataset_id: DatasetId) -> Dataset | None:
        return self._store.get(dataset_id)

    async def get_latest_version(self, market_id: MarketId) -> Dataset | None:
        matches = [d for d in self._store.values() if d.market_id == market_id]
        if not matches:
            return None
        return max(matches, key=lambda d: d.version)

    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[Dataset]:
        matches = sorted(
            (d for d in self._store.values() if d.market_id == market_id), key=lambda d: d.version, reverse=True
        )
        return matches[:limit]

    async def upsert(self, dataset: Dataset) -> Dataset:
        self._store[dataset.id] = dataset
        return dataset
