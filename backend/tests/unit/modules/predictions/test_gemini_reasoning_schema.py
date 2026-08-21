"""Gemini Prediction Reasoning Engine — schema validation (spec Phase 2i). `extra="forbid"` on
every nested model is the actual leakage guard here: a hallucinated field like
`official_probability` must fail validation outright, not silently pass through as if TitanIQ
condoned Gemini emitting a replacement probability."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from modules.predictions.infrastructure.gemini_reasoning_schema import GeminiReasoningResponseSchema

_VALID_PAYLOAD = {
    "prediction_review": {
        "status": "SUPPORTED",
        "overall_assessment": "Confirmed lineup strengthens the home attacking signal.",
        "confidence": {"level": "MEDIUM", "score": 0.6},
    },
    "contextual_assessment": {
        "lineups": {
            "impact": "POSITIVE",
            "strength": "MEDIUM",
            "score": 0.6,
            "reason": "Confirmed starting lineup includes the top scorer.",
        }
    },
    "supporting_factors": [
        {
            "factor": "Confirmed lineup",
            "impact": "POSITIVE",
            "strength": "MEDIUM",
            "evidence": "Starting XI confirmed with top scorer included.",
            "source_ids": ["lineup-1"],
        }
    ],
    "risk_factors": [],
    "missing_context": [],
    "prediction_reconsideration": {
        "direction": "SUPPORTS_BASE_PREDICTION",
        "material_change": False,
        "reason": "Evidence agrees with the base prediction; no material change.",
    },
    "evidence_quality": {
        "overall": "MEDIUM",
        "source_count": 1,
        "timestamp_valid": True,
        "pre_event_only": True,
        "conflicting_information": False,
    },
}


def _payload(**overrides) -> dict:
    import copy

    payload = copy.deepcopy(_VALID_PAYLOAD)
    payload.update(overrides)
    return payload


def test_valid_payload_parses_into_matching_domain_values():
    parsed = GeminiReasoningResponseSchema.model_validate(_VALID_PAYLOAD)

    assert parsed.prediction_review.status.value == "SUPPORTED"
    assert parsed.prediction_review.confidence.score == 0.6
    assert parsed.contextual_assessment["lineups"].impact.value == "POSITIVE"
    assert parsed.supporting_factors[0].source_ids == ("lineup-1",)
    assert parsed.prediction_reconsideration.direction.value == "SUPPORTS_BASE_PREDICTION"
    assert parsed.evidence_quality.source_count == 1


def test_missing_required_top_level_field_raises():
    payload = _payload()
    del payload["prediction_reconsideration"]

    with pytest.raises(ValidationError):
        GeminiReasoningResponseSchema.model_validate(payload)


def test_missing_nested_required_field_raises():
    payload = _payload()
    del payload["prediction_review"]["confidence"]

    with pytest.raises(ValidationError):
        GeminiReasoningResponseSchema.model_validate(payload)


def test_invalid_enum_value_raises():
    payload = _payload()
    payload["prediction_review"]["status"] = "TOTALLY_CONFIRMED"

    with pytest.raises(ValidationError):
        GeminiReasoningResponseSchema.model_validate(payload)


def test_hallucinated_top_level_field_is_rejected():
    """The exact failure mode the absolute rules prohibit: Gemini inventing a replacement
    probability field. `extra="forbid"` must reject the whole payload, not just ignore the key."""
    payload = _payload(official_probability=0.91)

    with pytest.raises(ValidationError):
        GeminiReasoningResponseSchema.model_validate(payload)


def test_hallucinated_nested_field_is_rejected():
    payload = _payload()
    payload["prediction_review"]["invented_field"] = "should not exist"

    with pytest.raises(ValidationError):
        GeminiReasoningResponseSchema.model_validate(payload)


def test_supporting_factors_capped_at_five():
    payload = _payload()
    payload["supporting_factors"] = [
        {
            "factor": f"factor {i}", "impact": "POSITIVE", "strength": "LOW",
            "evidence": "evidence", "source_ids": [],
        }
        for i in range(6)
    ]

    with pytest.raises(ValidationError):
        GeminiReasoningResponseSchema.model_validate(payload)


def test_confidence_score_out_of_range_raises():
    payload = _payload()
    payload["prediction_review"]["confidence"]["score"] = 1.5

    with pytest.raises(ValidationError):
        GeminiReasoningResponseSchema.model_validate(payload)


def test_empty_contextual_assessment_and_missing_context_are_valid():
    """A market/sport with genuinely no contextual categories to assess (e.g. table_tennis) must
    validate cleanly with empty collections — this is not the same as a schema failure."""
    payload = _payload(contextual_assessment={}, missing_context=["news", "injuries"])

    parsed = GeminiReasoningResponseSchema.model_validate(payload)

    assert parsed.contextual_assessment == {}
    assert parsed.missing_context == ("news", "injuries")


def test_insufficient_context_status_still_requires_full_shape():
    """INSUFFICIENT_CONTEXT is a legitimate status value, not a shortcut past the schema — the
    mock adapter's own insufficient-context branch must still produce a fully valid payload."""
    payload = _payload()
    payload["prediction_review"]["status"] = "INSUFFICIENT_CONTEXT"
    payload["prediction_reconsideration"]["direction"] = "INSUFFICIENT_EVIDENCE"

    parsed = GeminiReasoningResponseSchema.model_validate(payload)

    assert parsed.prediction_review.status.value == "INSUFFICIENT_CONTEXT"
