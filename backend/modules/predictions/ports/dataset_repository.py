"""Dataset Platform repository port (Milestone 9.1). Concrete implementation lives in
modules/predictions/infrastructure/persistence, matching every other Milestone 9 repository port.
"""

from __future__ import annotations

from typing import Protocol

from modules.predictions.domain.dataset import Dataset, DatasetId
from modules.predictions.domain.value_objects import MarketId


class DatasetRepositoryPort(Protocol):
    async def get(self, dataset_id: DatasetId) -> Dataset | None: ...
    async def get_latest_version(self, market_id: MarketId) -> Dataset | None: ...
    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[Dataset]: ...
    async def upsert(self, dataset: Dataset) -> Dataset: ...
