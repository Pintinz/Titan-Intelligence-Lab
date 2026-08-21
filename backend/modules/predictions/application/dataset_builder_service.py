"""Dataset Builder (Milestone 9.1 Dataset Platform). Builds a `Dataset` exclusively from real
Prediction Pipeline output — `Prediction.feature_snapshot` (Milestone 9's Feature-to-Market
Registry-filtered Feature Store resolution) paired with its realized `PredictionOutcome`. No
other feature source is ever read directly, satisfying "No algorithm may bypass the Feature
Store" by construction: the only place `TrainingSample.features` comes from is a `feature_snapshot`
that was itself produced by `PredictionContextBuilder`/`FeatureMarketMappingService` (Milestone 9).

See `modules.predictions.domain.dataset` module docstring for the classification-label recovery
this builder relies on (`_label_from_outcome`) — `PredictionOutcome.actual_value` is a real-world
fact string (e.g. `"btts_yes"`), not the generic `"positive"`/`"negative"` an earlier version of
this module assumed; the real training label is recovered via `outcome.error` +
`real_label_is_positive`, not string-matched off `actual_value` directly. (Multiclass classification
support, 2026-08-06): for a market with more than two `MARKET_OUTCOME_CATALOG` outcomes, the label
is instead the real label's index within that catalog's own ordering — see the domain module's
updated docstring.
"""

from __future__ import annotations

import hashlib
import json
import statistics as pystats
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.predictions.application.outcome_label_mapper import real_outcome_is_positive
from modules.predictions.domain.dataset import (
    Dataset,
    DatasetId,
    DatasetLineage,
    DatasetQualityIssue,
    DatasetStatistics,
    DatasetStatus,
)
from modules.predictions.domain.entities import Prediction
from modules.predictions.domain.market_outcome_registry import MARKET_OUTCOME_CATALOG
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


def _label_from_outcome(
    target_type: TargetType,
    market_key: str,
    prediction: Prediction,
    actual_value: str,
    error: float | None,
    class_labels: tuple[str, ...] = (),
) -> float | None:
    """Returns the real training label, or ``None`` when it can't be honestly recovered (never a
    fabricated guess). For a multiclass market (``class_labels`` non-empty — more than two
    `MARKET_OUTCOME_CATALOG` outcomes, e.g. football.match_winner/football.correct_score):
    ``actual_value`` is already the market's own real label, produced directly by a
    `THREE_WAY_MARKET_RESOLVERS`/`GRID_MARKET_RESOLVERS` resolver — the label is just that value's
    index within ``class_labels``, honestly skipped (`None`) if it somehow isn't one of the
    market's own declared values. For a binary CLASSIFICATION market: `real_outcome_is_positive`
    recovers the real outcome's own polarity from what the prediction claimed plus whether that
    claim matched reality — see that function's docstring. For REGRESSION, unchanged from before:
    `actual_value` is the stringified continuous realized value."""
    if target_type is TargetType.CLASSIFICATION:
        if class_labels:
            try:
                return float(class_labels.index(actual_value))
            except ValueError:
                return None
        matches_positive = real_outcome_is_positive(market_key, prediction.value, error)
        if matches_positive is None:
            return None
        return 1.0 if matches_positive else 0.0
    return float(actual_value)


def _content_hash(market_id: MarketId, samples: list[TrainingSample], feature_order: list[str]) -> str:
    payload = {
        "market_id": str(market_id),
        "feature_order": feature_order,
        # Milestone 18: reference_time is included since it now determines split membership for
        # every temporal strategy — two datasets with identical features/labels but different
        # reference_times can split completely differently, so the hash must reflect that.
        "samples": [
            [sample.features.get(key, None) for key in feature_order] + [sample.label, sample.reference_time]
            for sample in samples
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _compute_statistics(
    samples: list[TrainingSample], feature_order: list[str], target_type: TargetType, is_multiclass: bool = False
) -> DatasetStatistics:
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

    # Multiclass labels are class indices (0.0, 1.0, 2.0, ...), not a 0/1 polarity — "positive_rate"
    # and its SEVERE_CLASS_IMBALANCE reading are a binary-only concept that would misfire on an
    # index encoding (e.g. flagging "severe imbalance" just because most fitted indices cluster
    # low), so multiclass datasets honestly report no positive_rate at all (2026-08-06).
    positive_rate = None
    if target_type is TargetType.CLASSIFICATION and n and not is_multiclass:
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

        # Multiclass classification support (2026-08-06): a market with more than two declared
        # outcomes (football.match_winner's 3-way, football.correct_score's 37-cell grid) has no
        # binary polarity to recover — its canonical MARKET_OUTCOME_CATALOG ordering becomes the
        # class-index label space instead. Every existing binary/regression market keeps
        # class_labels empty, exactly as before this support existed.
        outcome_spec = MARKET_OUTCOME_CATALOG.get(market.market_key)
        class_labels: tuple[str, ...] = ()
        if market.target_type is TargetType.CLASSIFICATION and outcome_spec is not None and len(outcome_spec.allowed_values) > 2:
            class_labels = tuple(outcome_spec.allowed_values)

        outcomes = await self.outcomes.list_by_market(market_id, limit=limit)
        samples: list[TrainingSample] = []
        source_prediction_ids: list[str] = []
        for outcome in outcomes:
            prediction = await self.predictions.get(outcome.prediction_id)
            if prediction is None:
                continue
            label = _label_from_outcome(
                market.target_type, market.market_key, prediction, outcome.actual_value, outcome.error, class_labels
            )
            if label is None:
                continue  # can't honestly recover a training label for this outcome — skip, never fabricate
            # Milestone 18: reference_time = the real-world moment this outcome's label became
            # knowable — the authoritative timestamp dataset_splitter.split() sorts by for every
            # temporal strategy (never the DB query order, which is descending and was the
            # Milestone 17 defect's root cause).
            samples.append(
                TrainingSample(
                    features=dict(prediction.feature_snapshot),
                    label=label,
                    reference_time=outcome.evaluated_at,
                    # Statistical-baseline charter, Phase 3 — unconditional copy-through, harmlessly
                    # None for every market except football's 12 goals/score markets (see
                    # PredictionOutcome.raw_home_goals/raw_away_goals's own docstring).
                    raw_home_goals=outcome.raw_home_goals,
                    raw_away_goals=outcome.raw_away_goals,
                )
            )
            source_prediction_ids.append(str(prediction.id))

        feature_order = sorted({key for sample in samples for key in sample.features})
        statistics = _compute_statistics(samples, feature_order, market.target_type, is_multiclass=bool(class_labels))
        quality_issues = _detect_quality_issues(statistics)
        content_hash = _content_hash(market_id, samples, feature_order)

        lineage = DatasetLineage(
            market_id=market_id,
            source_prediction_ids=tuple(source_prediction_ids),
            feature_keys=tuple(feature_order),
            built_at=now,
            class_labels=class_labels,
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
