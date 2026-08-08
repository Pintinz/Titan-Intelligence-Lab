"""Dataset Platform domain (Milestone 9.1). A `Dataset` is a versioned, hashed, lineage-tracked
snapshot of `TrainingSample`s built exclusively from real Prediction Pipeline output — never a
bypass of the Feature Store (docs/decisions.md ADR-052: "No algorithm may bypass the Feature
Store" is satisfied here by building samples from `Prediction.feature_snapshot`, which is itself
always the market's Feature-to-Market-Registry-filtered resolution of real Feature Store values,
never a raw/ad-hoc feature read).

**Label convention (updated Milestone 9.2 Phase 2/3)**: for a `TargetType.CLASSIFICATION` market,
`PredictionOutcome.actual_value` is a human-readable real-world fact (e.g. `"btts_yes"`,
`"home_win"`, `"HOME_WIN"`) — never the generic `"positive"`/`"negative"` this module originally
assumed (ADR-052's original convention, obsoleted once `outcome_label_mapper.py` and
`OutcomeResolutionService` started recording real domain labels instead of the generic predictor's
bare output). The Dataset Builder recovers the real positive/negative training label from
`outcome.error` (whether the recorded prediction matched the real outcome) combined with
`real_label_is_positive(market.market_key, prediction.value)` (what the prediction itself claimed) —
see `dataset_builder_service._label_from_outcome`. For `TargetType.REGRESSION`, `actual_value` is
the stringified continuous realized value, parsed with `float()` directly.

**Multiclass classification (2026-08-06)**: a market whose `MARKET_OUTCOME_CATALOG` entry declares
more than two `allowed_values` (e.g. `football.match_winner`'s HOME_WIN/DRAW/AWAY_WIN,
`football.correct_score`'s 37-cell scoreline grid) has no binary polarity to recover at all — for
these, `_label_from_outcome` instead recovers the sample's label as the float index of
`outcome.actual_value` within that canonical `allowed_values` ordering (already the market's own
real label, produced directly by a `THREE_WAY_MARKET_RESOLVERS`/`GRID_MARKET_RESOLVERS` resolver in
`outcome_resolution_service.py` — no polarity mapping needed). `DatasetLineage.class_labels` carries
that same ordering forward so `AutomaticModelSelectionService` can set it on each trained-model
adapter before `fit()`, letting `predict_one()` decode a predicted index back to the real label.
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
    class_labels: tuple[str, ...] = field(default_factory=tuple)
    """(Multiclass classification support, 2026-08-06) The market's real label space in canonical
    order, from `MARKET_OUTCOME_CATALOG[market_key].allowed_values` — populated only when the
    market is a classification market with more than two outcomes; empty (the default) for every
    binary-classification or regression dataset, unchanged from before this support existed."""


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
