"""Sports-Analyst Explainability — `FootballExplanation` <-> `FootballExplanationModel`."""

from __future__ import annotations

from uuid import uuid4

from modules.predictions.domain.football_explanation import (
    AttributionMethod,
    ContextItem,
    ContextRole,
    CounterSignal,
    ExplanationStatus,
    FootballExplanation,
    KeyReason,
)
from modules.predictions.domain.value_objects import PredictionId
from modules.predictions.infrastructure.persistence.models import FootballExplanationModel


def _serialize_key_reason(reason: KeyReason) -> dict:
    return {
        "rank": reason.rank, "feature": reason.feature, "football_concept": reason.football_concept,
        "team": reason.team, "direction": reason.direction, "contribution": reason.contribution,
        "evidence": reason.evidence, "analysis": reason.analysis,
    }


def _deserialize_key_reason(data: dict) -> KeyReason:
    return KeyReason(
        rank=data["rank"], feature=data["feature"], football_concept=data["football_concept"],
        team=data.get("team"), direction=data["direction"], contribution=data["contribution"],
        evidence=data.get("evidence", ""), analysis=data.get("analysis", ""),
    )


def _serialize_counter_signal(signal: CounterSignal) -> dict:
    return {
        "feature": signal.feature, "football_concept": signal.football_concept,
        "contribution": signal.contribution, "analysis": signal.analysis,
    }


def _deserialize_counter_signal(data: dict) -> CounterSignal:
    return CounterSignal(
        feature=data["feature"], football_concept=data["football_concept"],
        contribution=data["contribution"], analysis=data.get("analysis", ""),
    )


def _serialize_context_item(item: ContextItem) -> dict:
    return {
        "type": item.type, "description": item.description,
        "model_contribution": item.model_contribution, "role": item.role.value,
    }


def _deserialize_context_item(data: dict) -> ContextItem:
    return ContextItem(
        type=data["type"], description=data["description"],
        model_contribution=data["model_contribution"], role=ContextRole(data["role"]),
    )


def football_explanation_to_model(
    prediction_id: PredictionId, explanation: FootballExplanation, model: FootballExplanationModel | None = None
) -> FootballExplanationModel:
    model = model or FootballExplanationModel(id=uuid4())
    model.prediction_id = prediction_id.value
    model.market_key = explanation.market_key
    model.status = explanation.status.value
    model.prediction_value = explanation.prediction_value
    model.probability = explanation.probability
    model.model_algorithm = explanation.model_algorithm
    model.attribution_method = explanation.attribution_method.value
    model.key_reasons = [_serialize_key_reason(r) for r in explanation.key_reasons]
    model.counter_signals = [_serialize_counter_signal(c) for c in explanation.counter_signals]
    model.context = [_serialize_context_item(c) for c in explanation.context]
    model.verdict = explanation.verdict
    model.match_profile = explanation.match_profile
    model.confidence_explanation = explanation.confidence_explanation
    model.bottom_line = explanation.bottom_line
    model.unavailable_reason = explanation.unavailable_reason
    model.prompt_version = explanation.prompt_version
    model.created_at = explanation.generated_at
    return model


def football_explanation_to_domain(model: FootballExplanationModel) -> FootballExplanation:
    return FootballExplanation(
        status=ExplanationStatus(model.status),
        market_key=model.market_key,
        prediction_value=model.prediction_value,
        probability=model.probability,
        model_algorithm=model.model_algorithm,
        attribution_method=AttributionMethod(model.attribution_method),
        key_reasons=tuple(_deserialize_key_reason(r) for r in (model.key_reasons or [])),
        counter_signals=tuple(_deserialize_counter_signal(c) for c in (model.counter_signals or [])),
        context=tuple(_deserialize_context_item(c) for c in (model.context or [])),
        verdict=model.verdict,
        match_profile=model.match_profile,
        confidence_explanation=model.confidence_explanation,
        bottom_line=model.bottom_line,
        unavailable_reason=model.unavailable_reason,
        prompt_version=model.prompt_version,
        generated_at=model.created_at,
    )
