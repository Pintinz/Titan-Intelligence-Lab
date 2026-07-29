"""Dataset Platform domain (Milestone 9.1). A `Dataset` is a versioned, hashed, lineage-tracked
snapshot of `TrainingSample`s built exclusively from real Prediction Pipeline output — never a
bypass of the Feature Store (docs/decisions.md ADR-052: "No algorithm may bypass the Feature
Store" is satisfied here by building samples from `Prediction.feature_snapshot`, which is itself
always the market's Feature-to-Market-Registry-filtered resolution of real Feature Store values,
never a raw/ad-hoc feature read).

**ADR-052 label convention**: for a `TargetType.CLASSIFICATION` market, `PredictionOutcome.actual_value`
is expected to literally be `"positive"`/`"negative"` — the same generic two-sided convention
`WeightedLogisticPredictor`/`TrainedModelPredictor` already produce as `PredictorOutput.value`
(docs/decisions.md — data-driven market registry; `infrastructure/predictors/weighted_scoring.py`
docstring explicitly defers per-market real-label translation to a layer that doesn't exist yet).
Until that per-market translation layer exists, outcome recording follows the same convention by
symmetry — the Dataset Builder does not invent a third convention. For `TargetType.REGRESSION`,
`actual_value` is the stringified continuous realized value, parsed with `float()` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID

from modules.predictions.domain.value_objects import MarketId
from modules.predictions.ports.ml_model import TrainingSample


class DatasetStatus(str, Enum):
    """Draft -> Validated -> Approved -> Archived, mirroring `MarketDefinition`'s lifecycle
    shape (Milestone 9) rather than inventing a new state-machine convention."""

    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    ARCHIVED = "archived"


class SplitStrategy(str, Enum):
    """The 6 dataset split kinds the Milestone 9.1 Dataset Platform spec names by name."""

    TRAIN_TEST = "train_test"
    TRAIN_VAL_TEST = "train_val_test"
    HOLDOUT = "holdout"
    ROLLING_WINDOW = "rolling_window"
    WALK_FORWARD = "walk_forward"
    TIME_SERIES_SPLIT = "time_series_split"


class DatasetQualityIssue(str, Enum):
    TOO_FEW_SAMPLES = "too_few_samples"
    SEVERE_CLASS_IMBALANCE = "severe_class_imbalance"
    HIGH_MISSING_RATE = "high_missing_rate"
    ZERO_VARIANCE_FEATURE = "zero_variance_feature"


@dataclass(frozen=True)
class DatasetId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class DatasetStatistics:
    """Per-dataset descriptive statistics — the Dataset Platform's own "Statistics" requirement,
    and the input `DriftDetectionService` (application layer) compares two of across time."""

    sample_count: int
    feature_count: int
    positive_rate: float | None  # classification only; None for regression datasets
    missing_rate: dict[str, float] = field(default_factory=dict)  # feature_key -> fraction of samples missing it
    mean: dict[str, float] = field(default_factory=dict)
    std: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetLineage:
    """Which real Prediction Pipeline records a dataset's samples were traced back to — the
    Dataset Platform's "Lineage" requirement."""

    market_id: MarketId
    source_prediction_ids: tuple[str, ...]
    feature_keys: tuple[str, ...]
    built_at: datetime


@dataclass
class Dataset:
    id: DatasetId
    market_id: MarketId
    version: int
    content_hash: str
    samples: list[TrainingSample]
    statistics: DatasetStatistics
    lineage: DatasetLineage
    quality_issues: tuple[DatasetQualityIssue, ...] = field(default_factory=tuple)
    status: DatasetStatus = DatasetStatus.DRAFT
    created_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None

    def is_usable_for_training(self) -> bool:
        return self.status is DatasetStatus.APPROVED and DatasetQualityIssue.TOO_FEW_SAMPLES not in self.quality_issues


@dataclass(frozen=True)
class DatasetSplit:
    """The result of `DatasetSplitter.split()` — always has ``train``; ``validation``/``test``
    are empty for split strategies that don't produce them (e.g. plain `HOLDOUT`)."""

    strategy: SplitStrategy
    train: tuple[TrainingSample, ...]
    validation: tuple[TrainingSample, ...] = field(default_factory=tuple)
    test: tuple[TrainingSample, ...] = field(default_factory=tuple)
    folds: tuple[tuple[tuple[TrainingSample, ...], tuple[TrainingSample, ...]], ...] = field(default_factory=tuple)
