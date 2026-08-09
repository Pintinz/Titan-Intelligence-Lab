"""Error Memory (Continuous Outcome Learning Engine, 2026-08-08, spec §12) — read-only analytics
over real `Prediction`/`PredictionOutcome`/`ModelEvaluation` history, no new persistence of its
own. Every number here is computed fresh from stored facts each call; nothing is cached or
inferred beyond what those facts directly support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.predictions.application.calibration_reporting_service import CalibrationReportBuilder
from modules.predictions.application.dataset_builder_service import MarketNotFoundError
from modules.predictions.application.outcome_label_mapper import real_outcome_is_positive
from modules.predictions.domain.calibration import CalibrationMethod
from modules.predictions.domain.error_memory import (
    FeatureFailureAssociation,
    MarketPerformanceSummary,
    ModelVersionSummary,
    OverconfidenceSummary,
)
from modules.predictions.domain.value_objects import MarketId, TargetType
from modules.predictions.ports.repositories import (
    MarketRepositoryPort,
    ModelEvaluationRepositoryPort,
    ModelRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)


@dataclass
class ErrorMemoryService:
    markets: MarketRepositoryPort
    models: ModelRepositoryPort
    predictions: PredictionRepositoryPort
    outcomes: PredictionOutcomeRepositoryPort
    model_evaluations: ModelEvaluationRepositoryPort
    calibration_reports: CalibrationReportBuilder = field(default_factory=CalibrationReportBuilder)

    async def market_performance_ranking(
        self, sport_code: str | None = None, limit_per_market: int = 500
    ) -> list[MarketPerformanceSummary]:
        """"Which markets does the model perform best on?" — best first: classification markets
        rank by accuracy, regression markets by mean error, both real and directly measured."""
        markets = await self.markets.list_by_sport(sport_code) if sport_code else await self.markets.list_all()

        summaries = []
        for market in markets:
            outcomes = await self.outcomes.list_by_market(market.id, limit=limit_per_market)
            errors = [o.error for o in outcomes if o.error is not None]
            mean_error = sum(errors) / len(errors) if errors else None
            accuracy = None
            if market.target_type is TargetType.CLASSIFICATION and errors:
                accuracy = sum(1 for e in errors if e < 0.5) / len(errors)
            summaries.append(
                MarketPerformanceSummary(
                    market_id=market.id, market_key=market.market_key, sample_count=len(errors),
                    mean_error=mean_error, accuracy=accuracy,
                )
            )

        return sorted(
            summaries,
            key=lambda s: (
                -(s.accuracy if s.accuracy is not None else -1.0),
                s.mean_error if s.mean_error is not None else float("inf"),
            ),
        )

    async def feature_failure_association(self, market_id: MarketId, limit: int = 500) -> list[FeatureFailureAssociation]:
        """"Which features are associated with prediction failures?" — for every numeric feature
        this market's real predictions carried, compares its average value on outcomes that
        turned out correct (`error < 0.5`) against ones that turned out incorrect. `error` alone
        already tells us "right or wrong" (`OutcomeResolutionService`'s own convention); no label-
        polarity recovery needed here, unlike `overconfidence_summary`."""
        outcomes = await self.outcomes.list_by_market(market_id, limit=limit)

        correct: dict[str, list[float]] = {}
        incorrect: dict[str, list[float]] = {}
        for outcome in outcomes:
            if outcome.error is None:
                continue
            prediction = await self.predictions.get(outcome.prediction_id)
            if prediction is None:
                continue
            bucket = correct if outcome.error < 0.5 else incorrect
            for key, value in prediction.feature_snapshot.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    bucket.setdefault(key, []).append(float(value))

        associations = []
        for key in sorted(set(correct) | set(incorrect)):
            correct_values, incorrect_values = correct.get(key, []), incorrect.get(key, [])
            correct_mean = sum(correct_values) / len(correct_values) if correct_values else None
            incorrect_mean = sum(incorrect_values) / len(incorrect_values) if incorrect_values else None
            divergence = abs(correct_mean - incorrect_mean) if correct_mean is not None and incorrect_mean is not None else None
            associations.append(
                FeatureFailureAssociation(
                    feature_key=key, correct_mean=correct_mean, incorrect_mean=incorrect_mean,
                    divergence=divergence, correct_sample_count=len(correct_values),
                    incorrect_sample_count=len(incorrect_values),
                )
            )

        return sorted(associations, key=lambda a: -(a.divergence if a.divergence is not None else -1.0))

    async def overconfidence_summary(self, market_id: MarketId, now: datetime, limit: int = 500) -> OverconfidenceSummary:
        """"Is the model systematically overconfident?" — compares each prediction's stated
        probability against the REAL outcome polarity (`real_outcome_is_positive`, the same
        recovery `DatasetBuilder`/`CalibrationFittingService` already use), not just whether the
        prediction happened to be right — a market can be "right" 60% of the time while still
        being badly overconfident about each individual call."""
        market = await self.markets.get(market_id)
        if market is None:
            raise MarketNotFoundError(str(market_id))

        outcomes = await self.outcomes.list_by_market(market_id, limit=limit)
        samples: list[tuple[float, bool]] = []
        for outcome in outcomes:
            prediction = await self.predictions.get(outcome.prediction_id)
            if prediction is None:
                continue
            matches_positive = real_outcome_is_positive(market.market_key, prediction.value, outcome.error)
            if matches_positive is None:
                continue
            samples.append((prediction.probability, matches_positive))

        if not samples:
            return OverconfidenceSummary(
                market_id=market_id, sample_count=0, mean_predicted_probability=None,
                mean_actual_positive_rate=None, overconfidence_score=None, expected_calibration_error=None,
            )

        mean_predicted = sum(p for p, _ in samples) / len(samples)
        mean_actual = sum(1 for _, is_positive in samples if is_positive) / len(samples)
        report = self.calibration_reports.build(CalibrationMethod.NONE, samples, now)
        return OverconfidenceSummary(
            market_id=market_id, sample_count=len(samples), mean_predicted_probability=mean_predicted,
            mean_actual_positive_rate=mean_actual, overconfidence_score=mean_predicted - mean_actual,
            expected_calibration_error=report.expected_calibration_error,
        )

    async def model_version_ranking(self, market_id: MarketId) -> list[ModelVersionSummary]:
        """"Which model version performs best? Has performance improved or deteriorated?" — every
        model ever registered for this market, newest version first, alongside its latest offline
        `ModelEvaluation` (already recorded elsewhere in this platform, never re-derived here)."""
        models = await self.models.list_by_market(market_id)
        summaries = []
        for model in models:
            latest = await self.model_evaluations.get_latest(model.id)
            summaries.append(
                ModelVersionSummary(
                    model_id=model.id, model_key=model.model_key, version=model.version, status=model.status,
                    latest_metrics=latest.metrics if latest else None,
                    evaluated_at=latest.evaluated_at if latest else None,
                )
            )
        return sorted(summaries, key=lambda s: s.version, reverse=True)
