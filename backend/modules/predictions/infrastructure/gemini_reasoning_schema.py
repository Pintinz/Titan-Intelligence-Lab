"""Gemini Prediction Reasoning Engine — strict schema validation of Gemini's raw JSON output.

The first Pydantic validation of any LLM output in this codebase (`GeminiAdapter`'s other
methods all do manual `json.loads()` + dict `.get()` with silent defaults). Lives here, in
`modules.predictions`, not `modules.intelligence` — the schema is shaped by the predictions
domain contract (`modules.predictions.domain.contextual_reasoning`), and `GeminiAdapter
.assess_prediction_context()` stays a pure text-in/text-out passthrough like every other method
on that port; this module is where the payload actually gets interpreted and enforced.

`model_config = ConfigDict(extra="forbid")` on every nested model — a hallucinated extra key
(e.g. an invented `"official_probability"` field, the exact failure mode the absolute rules
prohibit) fails validation outright rather than silently passing through.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from modules.predictions.domain.contextual_reasoning import (
    ConfidenceLevel,
    EvidenceQuality,
    Impact,
    PredictionReviewStatus,
    ReconsiderationDirection,
    Strength,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfidenceSchema(_Strict):
    level: ConfidenceLevel
    score: float = Field(ge=0.0, le=1.0)


class ContextualCategorySchema(_Strict):
    impact: Impact
    strength: Strength
    score: float = Field(ge=0.0, le=1.0)
    reason: str


class SupportingFactorSchema(_Strict):
    factor: str
    impact: Impact
    strength: Strength
    evidence: str
    source_ids: tuple[str, ...] = ()


class RiskFactorSchema(_Strict):
    factor: str
    impact: Impact
    strength: Strength
    evidence: str
    source_ids: tuple[str, ...] = ()


class ReconsiderationSchema(_Strict):
    direction: ReconsiderationDirection
    material_change: bool
    reason: str


class EvidenceQualitySchema(_Strict):
    overall: EvidenceQuality
    source_count: int = Field(ge=0)
    timestamp_valid: bool
    pre_event_only: bool
    conflicting_information: bool


class PredictionReviewSchema(_Strict):
    status: PredictionReviewStatus
    overall_assessment: str
    confidence: ConfidenceSchema


class GeminiReasoningResponseSchema(_Strict):
    """The exact top-level JSON shape `TITANIQ_GEMINI_REASONING_V1` instructs Gemini to return.
    Deliberately does NOT include `base_prediction`/`statistical_baseline` fields — those are
    supplied BY TitanIQ in the request payload and must never be echoed back as if Gemini could
    modify them; only Gemini's own assessment fields are validated here."""

    prediction_review: PredictionReviewSchema
    contextual_assessment: dict[str, ContextualCategorySchema] = Field(default_factory=dict)
    supporting_factors: tuple[SupportingFactorSchema, ...] = Field(default=(), max_length=5)
    risk_factors: tuple[RiskFactorSchema, ...] = Field(default=(), max_length=5)
    missing_context: tuple[str, ...] = ()
    prediction_reconsideration: ReconsiderationSchema
    evidence_quality: EvidenceQualitySchema
