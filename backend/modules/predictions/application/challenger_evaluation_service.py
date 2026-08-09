"""Candidate-vs-Champion comparison (Continuous Outcome Learning Engine, 2026-08-08) — scores a
freshly-trained Challenger against its market's current Champion on the SAME held-out sample set,
using the exact priority order `AutomaticModelSelectionService` now ranks its own roster by (log
loss, then Brier score, then calibration error — `model_comparison.py`'s own docstring explains
why this isn't a bare "Deploy"). ``holdout_samples`` is the caller's responsibility
(`ScheduledRetrainingOrchestrator._comparison_holdout`) — this service only ever scores what it's
handed, never builds or splits a dataset itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from modules.predictions.domain.calibration import CalibrationMethod
from modules.predictions.domain.model_comparison import ChallengerEvaluation, ComparisonMetrics, ComparisonVerdict
from modules.predictions.domain.probability_metrics import log_loss
from modules.predictions.domain.value_objects import ChallengerEvaluationId, MarketId, ModelId, TargetType
from modules.predictions.application.calibration_reporting_service import CalibrationReportBuilder
from modules.predictions.ports.ml_model import PredictionModelPort, TrainingSample

# A model must beat the other by more than this relative fraction on the decisive metric before
# the comparison declares a winner — otherwise two models scoring e.g. 0.601 vs. 0.599 log loss on
# a modest holdout would flip the verdict on sampling noise alone. 1% mirrors the kind of margin a
# human reviewing an A/B test would actually trust.
MIN_RELATIVE_IMPROVEMENT = 0.01

_METRIC_PRIORITY = ("log_loss", "brier_score", "expected_calibration_error")


def _relative_compare(champion_value: float, challenger_value: float) -> int:
    """+1 if the challenger meaningfully beats the champion, -1 if the champion meaningfully beats
    the challenger, 0 if the two are within the noise band (defer to the next metric)."""
    if champion_value <= 0:
        return -1 if challenger_value > champion_value else 0
    relative_change = (champion_value - challenger_value) / champion_value
    if relative_change > MIN_RELATIVE_IMPROVEMENT:
        return 1
    if relative_change < -MIN_RELATIVE_IMPROVEMENT:
        return -1
    return 0


def _verdict_from_cmp(cmp: int) -> ComparisonVerdict:
    if cmp > 0:
        return ComparisonVerdict.CHALLENGER_BETTER
    if cmp < 0:
        return ComparisonVerdict.CHAMPION_BETTER
    return ComparisonVerdict.INCONCLUSIVE


def _decide(
    target_type: TargetType, champion: ComparisonMetrics | None, challenger: ComparisonMetrics
) -> tuple[ComparisonVerdict, str]:
    if champion is None:
        return ComparisonVerdict.INCONCLUSIVE, "none"

    if target_type is TargetType.REGRESSION:
        if champion.mae is None or challenger.mae is None:
            return ComparisonVerdict.INCONCLUSIVE, "mae"
        return _verdict_from_cmp(_relative_compare(champion.mae, challenger.mae)), "mae"

    for metric_name in _METRIC_PRIORITY:
        champion_value = getattr(champion, metric_name)
        challenger_value = getattr(challenger, metric_name)
        if champion_value is None or challenger_value is None:
            continue
        cmp = _relative_compare(champion_value, challenger_value)
        if cmp != 0:
            return _verdict_from_cmp(cmp), metric_name
    return ComparisonVerdict.INCONCLUSIVE, "log_loss"


@dataclass
class ChallengerEvaluationService:
    calibration_reports: CalibrationReportBuilder = field(default_factory=CalibrationReportBuilder)

    def score(self, model: PredictionModelPort, target_type: TargetType, samples: list[TrainingSample], now: datetime) -> ComparisonMetrics:
        """Scores one fitted model on ``samples`` — public so a caller (e.g. a future backtest
        report) can reuse the identical scoring logic without going through a full comparison."""
        if target_type is TargetType.REGRESSION:
            if not samples:
                return ComparisonMetrics()
            errors = [abs(model.predict_one(s.features).raw_score - s.label) for s in samples]
            return ComparisonMetrics(mae=sum(errors) / len(errors))

        if model.class_labels:
            # Multiclass: only log loss generalizes without inventing a binary reduction.
            probabilities = [
                model.predict_one(s.features).distribution.get(model.class_labels[int(s.label)], 0.0)
                for s in samples
            ]
            return ComparisonMetrics(log_loss=log_loss(probabilities))

        true_class_probabilities = []
        reliability_samples = []
        for sample in samples:
            probability = model.predict_one(sample.features).probability
            actual_positive = sample.label >= 0.5
            true_class_probabilities.append(probability if actual_positive else 1.0 - probability)
            reliability_samples.append((probability, actual_positive))

        report = self.calibration_reports.build(CalibrationMethod.NONE, reliability_samples, now)
        return ComparisonMetrics(
            log_loss=log_loss(true_class_probabilities),
            brier_score=report.brier_score,
            expected_calibration_error=report.expected_calibration_error,
        )

    def evaluate(
        self,
        market_id: MarketId,
        target_type: TargetType,
        challenger_model_id: ModelId,
        challenger: PredictionModelPort,
        champion_model_id: ModelId | None,
        champion: PredictionModelPort | None,
        holdout_samples: list[TrainingSample],
        now: datetime,
    ) -> ChallengerEvaluation:
        challenger_metrics = self.score(challenger, target_type, holdout_samples, now)
        champion_metrics = self.score(champion, target_type, holdout_samples, now) if champion is not None else None
        verdict, decisive_metric = _decide(target_type, champion_metrics, challenger_metrics)

        return ChallengerEvaluation(
            id=ChallengerEvaluationId(uuid4()),
            market_id=market_id,
            challenger_model_id=challenger_model_id,
            champion_model_id=champion_model_id,
            challenger_metrics=challenger_metrics,
            champion_metrics=champion_metrics,
            verdict=verdict,
            decisive_metric=decisive_metric,
            holdout_sample_count=len(holdout_samples),
            evaluated_at=now,
        )
