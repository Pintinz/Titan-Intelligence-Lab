"""Prediction Engine (Milestone 9 Part 4): the orchestrator that runs the full pipeline stage
sequence after the Prediction Context Builder — Prediction Model -> Probability Calibration ->
Confidence Engine -> Explainability Engine -> a returned `Prediction`.

`generate()` is pure with respect to persistence: it returns a DRAFT `Prediction` domain object
and never calls a repository to store it. Caching, versioning, and audit-trail recording are a
thin wrapper's job on top of this engine (Milestone 9 task #134's Prediction Cache/Versioning/
Audit services) — the same "engine computes, a service on top persists" split already used by
`ConfidenceEngine.compute()` and `ExplainabilityEngine.explain()`.

Audit finding (2026-08-02): `generate()` previously always resolved its predictor from the
generic `PredictorRegistry` (the 3 weighted-formula strategies), ignoring `context.model`
entirely except as bookkeeping metadata stamped onto the resulting `Prediction` — even after
`AutomaticModelSelectionService` correctly trains and registers a real Challenger, and a human
promotes it to Champion, nothing ever served it. `_resolve_predictor` now prefers a real trained
model — loaded via `ModelLoaderService` and wrapped in `TrainedModelPredictor` — whenever the
market's Champion has a real `artifact_ref`, falling back to the `PredictorRegistry` exactly as
before for every market whose Champion is a placeholder (no artifact, e.g. the legacy
`football.match_result.heuristic` row) or when `model_loader` isn't wired at all. Any failure
loading/deserializing a real artifact falls back the same way — an artifact problem must never
break prediction generation when a safe formula-based path exists.

Three of the six cross-module confidence factors `PredictionContextBuilder` deliberately doesn't
gather are computed here from real, already-available signals, each with a documented proxy for
the "not enough history yet" case (same posture as every other honestly-scoped v1 metric in this
codebase, ADR-008):

- `historical_accuracy` — mean of ``1 - error`` across the market's recent `PredictionOutcome`
  rows (by convention, `error` is 0.0 for a correct classification-shaped outcome, 1.0 for
  incorrect, or a normalized absolute error for a regression-shaped one). Neutral 0.5 when the
  market has no outcome history yet — an unproven market, not a penalized one.
- `model_reliability` — the champion model's latest `ModelEvaluation.metrics["reliability"]`.
  Neutral 0.5 when no evaluation has been recorded yet.
- `prediction_stability` — 1 minus twice the standard deviation of this subject+market's most
  recent published probabilities (stddev of 0.5, the maximum possible spread on [0, 1], drives
  stability to 0). A single prior prediction (or none) can't have disagreed with anything yet, so
  stability defaults to 1.0, not the neutral 0.5 used elsewhere — absence of repetition is not
  evidence of instability.

The remaining two (`knowledge_graph_completeness`, `news_reliability`/`community_reliability`)
reuse the exact same Milestone 8 `IntelligenceRetrievalService.retrieve_all()` call
`ExplainabilityEngine` also makes (once each, independently — each engine stays self-contained
and testable on its own): KG completeness is the retrieved knowledge-graph fact count against a
configurable expected-fact baseline; news/community reliability are the mean
`IntelligenceRetrievalDocument.confidence` per modality, neutral 0.5 with no documents retrieved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.features.domain.value_objects import EntityType
from modules.intelligence.application.intelligence_retrieval_service import IntelligenceRetrievalService
from modules.intelligence.ports.retrieval import IntelligenceRetrievalDocument
from modules.predictions.application.confidence_engine import ConfidenceEngine, ConfidenceInputs
from modules.predictions.application.explainability_engine import ExplainabilityEngine
from modules.predictions.application.outcome_label_mapper import (
    map_generic_distribution_to_real_labels,
    map_generic_value_to_real_label,
)
from modules.predictions.application.prediction_context_builder import PredictionContext, PredictionContextBuilder
from modules.predictions.application.predictor_registry import PredictorRegistry
from modules.predictions.domain.entities import Prediction
from modules.predictions.domain.value_objects import MarketId, ModelId, PredictionId, PredictionStatus, TargetType
from modules.predictions.ports.predictor import PredictorOutput
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.infrastructure.predictors.ml_predictor import TrainedModelPredictor
from modules.predictions.ports.calibrator import CalibratorPort
from modules.predictions.ports.predictor import PredictorPort
from modules.predictions.ports.repositories import (
    ModelEvaluationRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _calibrate_distribution(
    distribution: dict[str, float], calibration_key: str, raw_probability: float, calibrated_probability: float
) -> dict[str, float]:
    """Rescales a predictor's raw per-outcome distribution (Universal Probability Engine) so
    ``calibration_key`` — the *specific outcome `raw_probability` is P(...) of*, which for a
    two-sided weighted predictor is always P("positive") regardless of which side actually wins
    (see `_shape_outcome`'s docstring) — carries the calibrated probability
    `ProbabilityCalibrationEngine` (Part 4) already produced for it, proportionally
    redistributing the remaining probability mass across every other outcome so the distribution
    still sums to 1. Only that one outcome has a real calibration mapping fitted for it —
    `CalibratorPort.calibrate()` calibrates one probability at a time — so this keeps every other
    entry's *relative* shape from the predictor's own raw estimate rather than inventing a
    per-outcome calibration that was never fitted."""
    if not distribution or calibration_key not in distribution:
        return dict(distribution)
    remaining_raw_mass = 1.0 - raw_probability
    remaining_calibrated_mass = max(0.0, 1.0 - calibrated_probability)
    other_keys = [key for key in distribution if key != calibration_key]
    result = {calibration_key: calibrated_probability}
    if remaining_raw_mass > 1e-9:
        scale = remaining_calibrated_mass / remaining_raw_mass
        for key in other_keys:
            result[key] = distribution[key] * scale
    else:
        # All raw mass sat on this outcome (a degenerate/near-certain raw estimate) — nothing to
        # scale proportionally, so split whatever calibrated mass remains evenly across the rest.
        share = remaining_calibrated_mass / len(other_keys) if other_keys else 0.0
        for key in other_keys:
            result[key] = share
    return result


@dataclass
class PredictionEngine:
    context_builder: PredictionContextBuilder
    predictors: PredictorRegistry
    calibrator: CalibratorPort
    confidence_engine: ConfidenceEngine
    explainability_engine: ExplainabilityEngine
    retrieval: IntelligenceRetrievalService
    outcomes: PredictionOutcomeRepositoryPort
    model_evaluations: ModelEvaluationRepositoryPort
    predictions: PredictionRepositoryPort
    model_loader: ModelLoaderService | None = None
    expected_kg_facts: int = 10
    stability_window: int = 5

    async def generate(
        self, market_key: str, entity_type: EntityType, entity_id: str, subject_ref: str, now: datetime
    ) -> Prediction:
        context = await self.context_builder.build(market_key, entity_type, entity_id, now)

        predictor = await self._resolve_predictor(context)
        predictor_output = await predictor.predict(
            context.market.market_kind, context.resolved_features, context.mapping_weights
        )
        # `calibrated_probability` is P("positive") for the two-sided weighted predictors — see
        # `_shape_outcome`'s docstring — never assume it's P(the eventual `value`); `_shape_outcome`
        # derives the real published `probability` (P(the winning `value`)) from the distribution
        # it builds. Still computed/stored for a REGRESSION market (e.g.
        # `basketball.player_points_prop`) — `Prediction.probability` stays a required field every
        # other consumer already reads — but a REGRESSION market's frontend surface reads
        # `confidence_interval`/`expected_error` instead, never this value.
        calibrated_probability = await self.calibrator.calibrate(context.model.id, predictor_output.probability)
        value, probability, probability_distribution, confidence_interval, expected_error = await self._shape_outcome(
            context, predictor_output, calibrated_probability
        )

        documents = await self.retrieval.retrieve_all(subject_ref)
        confidence = self.confidence_engine.compute(
            ConfidenceInputs(
                features=context.feature_confidence_inputs,
                historical_accuracy=await self._historical_accuracy(context.market.id),
                knowledge_graph_completeness=self._kg_completeness(documents),
                news_reliability=self._average_confidence(documents, "news"),
                community_reliability=self._average_confidence(documents, "community"),
                model_reliability=await self._model_reliability(context.model.id),
                prediction_stability=await self._prediction_stability(subject_ref, context.market.id),
            )
        )

        explanation = await self.explainability_engine.explain(
            subject_ref, market_key, predictor_output, calibrated_probability
        )

        return Prediction(
            id=PredictionId(uuid4()),
            market_id=context.market.id,
            model_id=context.model.id,
            subject_ref=subject_ref,
            value=value,
            probability=probability,
            confidence=confidence,
            explanation=explanation,
            feature_snapshot=context.resolved_features,
            model_version=str(context.model.version),
            status=PredictionStatus.DRAFT,
            generated_at=now,
            data_freshness=now,
            probability_distribution=probability_distribution,
            confidence_interval=confidence_interval,
            expected_error=expected_error,
        )

    async def _shape_outcome(
        self, context: PredictionContext, predictor_output: PredictorOutput, calibrated_probability: float
    ) -> tuple[str, float, dict[str, float], tuple[float, float] | None, float | None]:
        """Splits `Prediction`'s CLASSIFICATION-vs-REGRESSION field groups (Universal Probability
        Engine) by the market's own `TargetType` — the one place that decision gets made, so every
        `MarketKind` predictor stays agnostic to it and just reports its raw estimate. Returns
        ``(value, probability, probability_distribution, confidence_interval, expected_error)``.

        ``predictor_output.probability``/``calibrated_probability`` are NOT always P(the winning
        ``value``) — for the two-sided weighted predictors (`WeightedLogisticPredictor`,
        `WeightedLinearPredictor`) they're always P("positive") regardless of which side actually
        wins, by design: `CalibrationFittingService` fits the calibrator against exactly that
        convention (pairs `Prediction.probability` with "was the real outcome positive", not
        "did the prediction match"), so the calibration math below must stay anchored to whichever
        raw distribution entry the calibrator actually calibrated — found by matching
        ``predictor_output.probability`` back to its distribution key, not by assuming it's
        ``predictor_output.value``. `WeightedOrdinalPredictor`/`PoissonScorePredictor`'s
        argmax-shaped output makes those two the same key anyway, so this is a no-op for them.

        The returned ``probability`` — what gets published as `Prediction.probability` and shown
        as the AI Verdict's headline confidence — is deliberately read back OUT of the calibrated
        distribution at ``value``'s own key, so it always means "confidence in the outcome actually
        published," never "confidence in the positive side" regardless of which side won."""
        if context.market.target_type is TargetType.REGRESSION:
            expected_error, confidence_interval = await self._regression_uncertainty(
                context.market.id, predictor_output.raw_score
            )
            return f"{predictor_output.raw_score:.4f}", calibrated_probability, {}, confidence_interval, expected_error

        mapped_value = map_generic_value_to_real_label(context.market.market_key, predictor_output.value)
        mapped_distribution = map_generic_distribution_to_real_labels(
            context.market.market_key, predictor_output.distribution
        )
        raw_calibration_key = next(
            (key for key, probability in predictor_output.distribution.items() if probability == predictor_output.probability),
            predictor_output.value,
        )
        mapped_calibration_key = map_generic_value_to_real_label(context.market.market_key, raw_calibration_key)
        probability_distribution = _calibrate_distribution(
            mapped_distribution, mapped_calibration_key, predictor_output.probability, calibrated_probability
        )
        verdict_probability = probability_distribution.get(mapped_value, calibrated_probability)
        return mapped_value, verdict_probability, probability_distribution, None, None

    async def _regression_uncertainty(
        self, market_id: MarketId, predicted_value: float
    ) -> tuple[float | None, tuple[float, float] | None]:
        """Historical-MAE-based expected error / confidence interval for a `TargetType.REGRESSION`
        market — reuses the same `PredictionOutcome.error` convention `_historical_accuracy` reads
        (`domain/dataset.py`: "the normalized absolute error for a REGRESSION target"). Both are
        `None` until the market has at least two evaluated outcomes to estimate spread from — an
        honest gap, never a fabricated interval."""
        outcomes = await self.outcomes.list_by_market(market_id, limit=200)
        errors = [outcome.error for outcome in outcomes if outcome.error is not None]
        if len(errors) < 2:
            return None, None
        expected_error = sum(errors) / len(errors)
        return expected_error, (predicted_value - expected_error, predicted_value + expected_error)

    async def _resolve_predictor(self, context: PredictionContext) -> PredictorPort:
        """Prefers the market's real CHAMPION model when one has actually been trained (a real
        `artifact_ref` exists) — loaded via `ModelLoaderService` and served through
        `TrainedModelPredictor`. Falls back to the generic formula-predictor registry for a
        placeholder Champion (no artifact), an unrecognized/corrupt artifact, or when
        `model_loader` was never wired — a trained-model problem must never break generation."""
        if self.model_loader is not None and context.model.artifact_ref:
            try:
                model = await self.model_loader.load(
                    context.model.id,
                    context.model.framework or "",
                    context.model.algorithm,
                    context.market.target_type,
                    context.model.artifact_ref,
                )
                return TrainedModelPredictor(market_kind=context.market.market_kind, model=model)
            except Exception:  # noqa: BLE001 — any artifact-loading failure falls back, never breaks generation
                pass
        return self.predictors.get(context.market.market_kind, context.market.market_key)

    async def _historical_accuracy(self, market_id: MarketId) -> float:
        outcomes = await self.outcomes.list_by_market(market_id, limit=200)
        if not outcomes:
            return 0.5
        correctness = [1.0 - _clamp(outcome.error if outcome.error is not None else 0.0) for outcome in outcomes]
        return sum(correctness) / len(correctness)

    async def _model_reliability(self, model_id: ModelId) -> float:
        evaluation = await self.model_evaluations.get_latest(model_id)
        if evaluation is None:
            return 0.5
        return _clamp(float(evaluation.metrics.get("reliability", 0.5)))

    async def _prediction_stability(self, subject_ref: str, market_id: MarketId) -> float:
        recent = await self.predictions.list_by_subject(subject_ref, market_id)
        if len(recent) < 2:
            return 1.0
        probabilities = [prediction.probability for prediction in recent[: self.stability_window]]
        mean = sum(probabilities) / len(probabilities)
        variance = sum((p - mean) ** 2 for p in probabilities) / len(probabilities)
        return _clamp(1.0 - 2 * (variance**0.5))

    def _kg_completeness(self, documents: tuple[IntelligenceRetrievalDocument, ...]) -> float:
        kg_facts = sum(1 for document in documents if document.modality == "knowledge_graph")
        return min(kg_facts / self.expected_kg_facts, 1.0)

    def _average_confidence(
        self, documents: tuple[IntelligenceRetrievalDocument, ...], modality: str, default: float = 0.5
    ) -> float:
        matches = [document.confidence for document in documents if document.modality == modality]
        if not matches:
            return default
        return _clamp(sum(matches) / len(matches))
