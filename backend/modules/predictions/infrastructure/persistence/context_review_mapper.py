"""Gemini Prediction Reasoning Engine — `ContextualReview` <-> `PredictionContextReviewModel`.

Kept as its own module rather than folded into `mappers.py`: every nested value object here
carries real enum members (`Impact`/`Strength`/`PredictionReviewStatus`/...) that must be
explicitly `.value`-flattened for JSON storage and re-wrapped on read — enough distinct
serialization logic to warrant its own file rather than diluting `mappers.py`'s otherwise
flat, one-line-per-field mappings.
"""

from __future__ import annotations

from uuid import uuid4

from modules.predictions.domain.contextual_reasoning import (
    ConfidenceLevel,
    ContextualCategoryAssessment,
    ContextualReview,
    EvidenceQuality,
    EvidenceQualityReport,
    Impact,
    PredictionReconsideration,
    PredictionReviewStatus,
    ReconsiderationDirection,
    RiskFactor,
    StatisticalBaseline,
    Strength,
    SupportingFactor,
)
from modules.predictions.domain.value_objects import PredictionId
from modules.predictions.infrastructure.persistence.models import PredictionContextReviewModel


def _serialize_baseline(baseline: StatisticalBaseline) -> dict:
    return {
        "applicable": baseline.applicable, "available": baseline.available,
        "algorithm": baseline.algorithm, "probabilities": baseline.probabilities, "reason": baseline.reason,
    }


def _deserialize_baseline(data: dict) -> StatisticalBaseline:
    return StatisticalBaseline(
        applicable=data.get("applicable", False), available=data.get("available", False),
        algorithm=data.get("algorithm"), probabilities=data.get("probabilities"), reason=data.get("reason"),
    )


def _serialize_category(assessment: ContextualCategoryAssessment) -> dict:
    return {
        "impact": assessment.impact.value, "strength": assessment.strength.value,
        "score": assessment.score, "reason": assessment.reason,
    }


def _deserialize_category(data: dict) -> ContextualCategoryAssessment:
    return ContextualCategoryAssessment(
        impact=Impact(data["impact"]), strength=Strength(data["strength"]), score=data["score"], reason=data["reason"],
    )


def _serialize_factor(factor: SupportingFactor | RiskFactor) -> dict:
    return {
        "factor": factor.factor, "impact": factor.impact.value, "strength": factor.strength.value,
        "evidence": factor.evidence, "source_ids": list(factor.source_ids),
    }


def _deserialize_evidence_quality(data: dict) -> EvidenceQualityReport | None:
    if not data:
        return None
    return EvidenceQualityReport(
        overall=EvidenceQuality(data["overall"]), source_count=data["source_count"],
        timestamp_valid=data["timestamp_valid"], pre_event_only=data["pre_event_only"],
        conflicting_information=data["conflicting_information"],
    )


def context_review_to_model(
    prediction_id: PredictionId, review: ContextualReview, model: PredictionContextReviewModel | None = None
) -> PredictionContextReviewModel:
    model = model or PredictionContextReviewModel(id=uuid4())
    model.prediction_id = prediction_id.value
    model.market_key = review.market_key
    model.base_selection = review.base_selection
    model.base_probability = review.base_probability
    model.model_version = review.model_version
    model.statistical_baseline = _serialize_baseline(review.statistical_baseline)
    model.review_status = review.review_status.value
    model.overall_assessment = review.overall_assessment
    model.contextual_assessment = {k: _serialize_category(v) for k, v in review.contextual_assessment.items()}
    model.supporting_factors = [_serialize_factor(f) for f in review.supporting_factors]
    model.risk_factors = [_serialize_factor(f) for f in review.risk_factors]
    model.missing_context = list(review.missing_context)
    model.reconsideration_direction = review.reconsideration.direction.value if review.reconsideration else None
    model.reconsideration_reason = review.reconsideration.reason if review.reconsideration else None
    model.material_change = review.reconsideration.material_change if review.reconsideration else False
    model.context_confidence_level = review.confidence_level.value
    model.context_confidence_score = review.confidence_score
    model.evidence_quality = (
        {
            "overall": review.evidence_quality.overall.value, "source_count": review.evidence_quality.source_count,
            "timestamp_valid": review.evidence_quality.timestamp_valid,
            "pre_event_only": review.evidence_quality.pre_event_only,
            "conflicting_information": review.evidence_quality.conflicting_information,
        }
        if review.evidence_quality else {}
    )
    model.source_ids = list(review.source_ids)
    model.prediction_cutoff = review.prediction_cutoff
    model.prompt_version = review.prompt_version
    model.created_at = review.generated_at
    return model


def context_review_to_domain(model: PredictionContextReviewModel) -> ContextualReview:
    return ContextualReview(
        review_status=PredictionReviewStatus(model.review_status),
        overall_assessment=model.overall_assessment,
        confidence_level=ConfidenceLevel(model.context_confidence_level),
        confidence_score=model.context_confidence_score,
        market_key=model.market_key,
        base_selection=model.base_selection,
        base_probability=model.base_probability,
        model_version=model.model_version,
        statistical_baseline=_deserialize_baseline(model.statistical_baseline or {}),
        contextual_assessment={
            k: _deserialize_category(v) for k, v in (model.contextual_assessment or {}).items()
        },
        supporting_factors=tuple(
            SupportingFactor(
                factor=f["factor"], impact=Impact(f["impact"]), strength=Strength(f["strength"]),
                evidence=f["evidence"], source_ids=tuple(f.get("source_ids", [])),
            )
            for f in (model.supporting_factors or [])
        ),
        risk_factors=tuple(
            RiskFactor(
                factor=f["factor"], impact=Impact(f["impact"]), strength=Strength(f["strength"]),
                evidence=f["evidence"], source_ids=tuple(f.get("source_ids", [])),
            )
            for f in (model.risk_factors or [])
        ),
        missing_context=tuple(model.missing_context or []),
        reconsideration=(
            PredictionReconsideration(
                direction=ReconsiderationDirection(model.reconsideration_direction),
                material_change=model.material_change, reason=model.reconsideration_reason or "",
            )
            if model.reconsideration_direction else None
        ),
        evidence_quality=_deserialize_evidence_quality(model.evidence_quality or {}),
        source_ids=tuple(model.source_ids or []),
        prediction_cutoff=model.prediction_cutoff,
        prompt_version=model.prompt_version,
        generated_at=model.created_at,
    )
