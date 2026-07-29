"""Prediction Engine (Milestone 9 Part 4): the orchestrator that runs the full pipeline stage
sequence after the Prediction Context Builder — Prediction Model -> Probability Calibration ->
Confidence Engine -> Explainability Engine -> a returned `Prediction`.

`generate()` is pure with respect to persistence: it returns a DRAFT `Prediction` domain object
and never calls a repository to store it. Caching, versioning, and audit-trail recording are a
thin wrapper's job on top of this engine (Milestone 9 task #134's Prediction Cache/Versioning/
Audit services) — the same "engine computes, a service on top persists" split already used by
`ConfidenceEngine.compute()` and `ExplainabilityEngine.explain()`.

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
from modules.predictions.application.prediction_context_builder import PredictionContextBuilder
from modules.predictions.application.predictor_registry import PredictorRegistry
from modules.predictions.domain.entities import Prediction
from modules.predictions.domain.value_objects import MarketId, ModelId, PredictionId, PredictionStatus
from modules.predictions.ports.calibrator import CalibratorPort
from modules.predictions.ports.repositories import (
    ModelEvaluationRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


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
    expected_kg_facts: int = 10
    stability_window: int = 5

    async def generate(
        self, market_key: str, entity_type: EntityType, entity_id: str, subject_ref: str, now: datetime
    ) -> Prediction:
        context = await self.context_builder.build(market_key, entity_type, entity_id, now)

        predictor = self.predictors.get(context.market.market_kind, context.market.market_key)
        predictor_output = await predictor.predict(
            context.market.market_kind, context.resolved_features, context.mapping_weights
        )
        calibrated_probability = await self.calibrator.calibrate(context.model.id, predictor_output.probability)

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
            value=predictor_output.value,
            probability=calibrated_probability,
            confidence=confidence,
            explanation=explanation,
            feature_snapshot=context.resolved_features,
            model_version=str(context.model.version),
            status=PredictionStatus.DRAFT,
            generated_at=now,
            data_freshness=now,
        )

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
