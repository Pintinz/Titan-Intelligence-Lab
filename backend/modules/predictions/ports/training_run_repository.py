"""Training Run repository port — concrete implementation lives in
modules/predictions/infrastructure/persistence, matching every other Milestone 9 repository port.
"""

from __future__ import annotations

from typing import Protocol

from modules.predictions.domain.training_run import TrainingRun, TrainingRunId
from modules.predictions.domain.value_objects import MarketId


class TrainingRunRepositoryPort(Protocol):
    async def record(self, run: TrainingRun) -> TrainingRun: ...
    async def get(self, run_id: TrainingRunId) -> TrainingRun | None: ...
    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[TrainingRun]: ...
