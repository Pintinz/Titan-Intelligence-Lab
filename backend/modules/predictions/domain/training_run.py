"""Training Run domain (audit trail behind `ModelDefinition.training_run_ref`) — one row per
`AutomaticModelSelectionService.select_and_register_challenger()` call, persisting the winning
candidate's full training detail. Distinct from `Experiment` (`experiment_tracking_service.py`),
which records the cross-candidate benchmark comparison in a freeform config/metrics dict — this
is the structured, typed record of exactly what was trained: dataset, algorithm/framework, full
train/test metrics, feature order, sample counts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from modules.predictions.domain.dataset import DatasetId
from modules.predictions.domain.value_objects import MarketId, ModelId


@dataclass(frozen=True)
class TrainingRunId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class TrainingRun:
    id: TrainingRunId
    market_id: MarketId
    model_id: ModelId | None
    dataset_id: DatasetId | None
    algorithm: str
    framework: str
    train_metrics: dict
    test_metrics: dict
    feature_order: tuple[str, ...]
    selected_features: tuple[str, ...]
    samples_used: int
    outliers_removed: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
