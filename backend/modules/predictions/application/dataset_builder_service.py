"""Dataset Builder (Milestone 9.1 Dataset Platform). Builds a `Dataset` exclusively from real
Prediction Pipeline output — `Prediction.feature_snapshot` (Milestone 9's Feature-to-Market
Registry-filtered Feature Store resolution) paired with its realized `PredictionOutcome`. No
other feature source is ever read directly, satisfying "No algorithm may bypass the Feature
Store" by construction: the only place `TrainingSample.features` comes from is a `feature_snapshot`
that was itself produced by `PredictionContextBuilder`/`FeatureMarketMappingService` (Milestone 9).

See `modules.predictions.domain.dataset` module docstring (ADR-052) for the classification-label
convention (`actual_value` == "positive"/"negative") this builder relies on.
"""

from __future__ import annotations

import hashlib
import json
import statistics as pystats
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.predictions.domain.dataset import (
    Dataset,
    DatasetId,
    DatasetLineage,
    DatasetQualityIssue,
    DatasetStatistics,
    DatasetStatus,
)
from modules.predictions.domain.value_objects import MarketId, TargetType
from modules.predictions.ports.ml_model import MIN_TRAINING_SAMPLES, TrainingSample
from modules.predictions.ports.repositories import (
    MarketRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)

_MISSING_RATE_ALERT_THRESHOLD = 0.5
_CLASS_IMBALANCE_ALERT_THRESHOLD = 0.9  # positive_rate above this (or below 1 - this) is severe


class MarketNotFoundError(KeyError):
    pass


def _label_from_outcome(target_type: TargetType, actual_value: str) -> float:
    if target_type is TargetType.CLASSIFICATION:
        return 1.0 if actual_value == "positive" else 0.0
    return float(actual_value)


def _content_hash(market_id: MarketId, samples: list[TrainingSample], feature_order: list[str]) -> str:
    payload = {
        "market_id": str(market_id),
        "feature_order": feature_order,
        "samples": [[sample.features.get(key, None) for key in feature_order] + [sample.label] for sample in samples],
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _compute_statistics(samples: list[TrainingSample], feature_order: list[str], target_type: TargetType) -> DatasetStatistics:
    n = len(samples)
    missing_rate = {
        key: sum(1 for s in samples if key not in s.features) / n if n else 0.0 for key in feature_order
    }
    mean: dict[str, float] = {}
    std: dict[str, float] = {}
    for key in feature_order:
        values = [s.features[key] for s in samples if key in s.features]
        if not values:
            mean[key] = 0.0
            std[key] = 0.0
            continue
        mean[key] = pystats.fmean(values)
        std[key] = pystats.pstdev(values) if len(values) > 1 else 0.0

    positive_rate = None
    if target_type is TargetType.CLASSIFICATION and n:
        positive_rate = sum(1 for s in samples if s.label >= 0.5) / n

    return DatasetStatistics(
        sample_count=n,
        feature_count=len(feature_order),
        positive_rate=positive_rate,
        missing_rate=missing_rate,
        mean=mean,
        std=std,
    )


def _detect_quality_issues(statistics: DatasetStatistics) -> tuple:
    issues = []
    if statistics.sample_count < MIN_TRAINING_SAMPLES:
        issues.append(DatasetQualityIssue.TOO_FEW_SAMPLES)
    if statistics.positive_rate is not None and (
        statistics.positive_rate >= _CLASS_IMBALANCE_ALERT_THRESHOLD
        or statistics.positive_rate <= 1.0 - _CLASS_IMBALANCE_ALERT_THRESHOLD
    ):
        issues.append(DatasetQualityIssue.SEVERE_CLASS_IMBALANCE)
    if any(rate >= _MISSING_RATE_ALERT_THRESHOLD for rate in statistics.missing_rate.values()):
        issues.append(DatasetQualityIssue.HIGH_MISSING_RATE)
    if any(value == 0.0 for value in statistics.std.values()) and statistics.sample_count > 1:
        issues.append(DatasetQualityIssue.ZERO_VARIANCE_FEATURE)
    return tuple(issues)


@dataclass
class DatasetBuilder:
    markets: MarketRepositoryPort
    predictions: PredictionRepositoryPort
    outcomes: PredictionOutcomeRepositoryPort

    async def build(self, market_id: MarketId, now: datetime, limit: int = 5000, next_version: int = 1) -> Dataset:
        market = await self.markets.get(market_id)
        if market is None:
            raise MarketNotFoundError(str(market_id))

        outcomes = await self.outcomes.list_by_market(market_id, limit=limit)
        samples: list[TrainingSample] = []
        source_prediction_ids: list[str] = []
        for outcome in outcomes:
            prediction = await self.predictions.get(outcome.prediction_id)
            if prediction is None:
                continue
            label = _label_from_outcome(market.target_type, outcome.actual_value)
            samples.append(TrainingSample(features=dict(prediction.feature_snapshot), label=label))
            source_prediction_ids.append(str(prediction.id))

        feature_order = sorted({key for sample in samples for key in sample.features})
        statistics = _compute_statistics(samples, feature_order, market.target_type)
        quality_issues = _detect_quality_issues(statistics)
        content_hash = _content_hash(market_id, samples, feature_order)

        lineage = DatasetLineage(
            market_id=market_id,
            source_prediction_ids=tuple(source_prediction_ids),
            feature_keys=tuple(feature_order),
            built_at=now,
        )

        return Dataset(
            id=DatasetId(uuid4()),
            market_id=market_id,
            version=next_version,
            content_hash=content_hash,
            samples=samples,
            statistics=statistics,
            lineage=lineage,
            quality_issues=quality_issues,
            status=DatasetStatus.DRAFT,
            created_at=now,
        )
