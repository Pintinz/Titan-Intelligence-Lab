"""Gemini Prediction Reasoning Engine — domain contract (additive to, not a replacement for,
`ExplanationBundle`/`ExplainabilityEngine`). `ExplainabilityEngine` narrates *why the Champion's
own features* produced its verdict; this module is a second, independent structured assessment of
whether *current external evidence* (news/injuries/transfers/lineups, filtered to what was
knowable before the prediction cutoff) supports, weakens, or doesn't materially change that
verdict. Gemini never outputs a probability here — `ContextualReview.confidence_score` is
explicitly confidence *in the contextual assessment itself*, never an outcome probability (see
each field's docstring below for the exact distinction).

Every enum matches the "Gemini Prediction Reasoning & Evidence Engine" contract precisely — this
is the schema `GeminiReasoningResponseSchema` (Pydantic, `modules.intelligence.infrastructure
.gemini_reasoning_schema`) validates Gemini's raw JSON against, so this module and that one must
stay in lockstep. `ContextualReview` itself is sport-agnostic: `contextual_assessment` is a plain
`dict[str, ContextualCategoryAssessment]` keyed by whatever categories
`context_categories.SPORT_CONTEXT_CATEGORIES` names for the sport in play, not a fixed
football-shaped set of fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Impact(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class Strength(str, Enum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class PredictionReviewStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    WEAKLY_SUPPORTED = "WEAKLY_SUPPORTED"
    NEUTRAL = "NEUTRAL"
    CHALLENGED = "CHALLENGED"
    STRONGLY_CHALLENGED = "STRONGLY_CHALLENGED"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class ReconsiderationDirection(str, Enum):
    SUPPORTS_BASE_PREDICTION = "SUPPORTS_BASE_PREDICTION"
    WEAKENS_BASE_PREDICTION = "WEAKENS_BASE_PREDICTION"
    MIXED = "MIXED"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ConfidenceLevel(str, Enum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class EvidenceQuality(str, Enum):
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


@dataclass(frozen=True)
class StatisticalBaseline:
    """A live (never training-time/backtest) statistical baseline for this exact fixture and
    market — see `StatisticalBaselineProvider`. `applicable=False` means this market has no
    statistical-baseline family at all (e.g. `football.first_half_winner`); `applicable=True,
    available=False` means the family exists but no trained baseline model exists yet for this
    market (`reason` is then one of `BASELINE_DATA_INSUFFICIENT`/`BASELINE_NOT_TRAINED`) — never
    fabricated in either case."""

    applicable: bool
    available: bool
    algorithm: str | None = None
    probabilities: dict[str, float] | None = None
    reason: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    """One accepted piece of context — already passed `LiveEvidenceGatherer`'s cutoff/provenance
    filter by the time it reaches here. `source_id` is what Gemini is instructed to cite in
    `source_ids` fields (never a URL/source name it invents itself)."""

    source_id: str
    category: str  # "news" | "injuries" | "transfers" | "lineups" — whatever this sport declares
    summary: str
    entity_ref: str | None = None
    source_name: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None


@dataclass(frozen=True)
class SupportingFactor:
    factor: str
    impact: Impact
    strength: Strength
    evidence: str
    source_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RiskFactor:
    factor: str
    impact: Impact
    strength: Strength
    evidence: str
    source_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContextualCategoryAssessment:
    impact: Impact
    strength: Strength
    score: float
    reason: str


@dataclass(frozen=True)
class PredictionReconsideration:
    direction: ReconsiderationDirection
    material_change: bool
    reason: str


@dataclass(frozen=True)
class EvidenceQualityReport:
    overall: EvidenceQuality
    source_count: int
    timestamp_valid: bool
    pre_event_only: bool
    conflicting_information: bool


@dataclass(frozen=True)
class ContextualReview:
    """The full structured assessment persisted per `(prediction_id)` and exposed via the API's
    `contextual_review` field. `confidence_score`/`confidence_level` are Gemini's confidence *in
    this contextual assessment* — never an outcome probability, and never rendered as one on the
    frontend (see `ContextualReviewPanel`'s own docstring)."""

    review_status: PredictionReviewStatus
    overall_assessment: str
    confidence_level: ConfidenceLevel
    confidence_score: float

    market_key: str
    base_selection: str
    base_probability: float
    model_version: str

    statistical_baseline: StatisticalBaseline
    contextual_assessment: dict[str, ContextualCategoryAssessment] = field(default_factory=dict)
    supporting_factors: tuple[SupportingFactor, ...] = field(default_factory=tuple)
    risk_factors: tuple[RiskFactor, ...] = field(default_factory=tuple)
    missing_context: tuple[str, ...] = field(default_factory=tuple)
    reconsideration: PredictionReconsideration | None = None
    evidence_quality: EvidenceQualityReport | None = None
    source_ids: tuple[str, ...] = field(default_factory=tuple)

    prediction_cutoff: datetime | None = None
    prompt_version: str = "TITANIQ_GEMINI_REASONING_V1"
    generated_at: datetime | None = None
    # "gemini" | "mock" | "cached" | "unavailable" — see `FootballExplanation.narration_source`
    # for why this is disclosed rather than left indistinguishable.
    narration_source: str = "unavailable"
