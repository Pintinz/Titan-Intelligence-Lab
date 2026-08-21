"""Sports-Analyst Explainability — domain contract for the attribution-grounded, Gemini-narrated
football explanation. Distinct from `modules.predictions.domain.contextual_reasoning`'s
`ContextualReview` (a different feature: "does new evidence change the base prediction"). This
module answers "why did the model predict this" — real model attribution translated into
football-analyst language, never the other way around (§34: PREDICTION -> ATTRIBUTION ->
EVIDENCE -> EXPLANATION, never EXPLANATION -> PREDICTION).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ExplanationStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    VALIDATION_FAILED = "validation_failed"


class ContextRole(str, Enum):
    """Whether a piece of gathered context actually influenced the model, or is only available
    as background (§22: existence of context does NOT mean it influenced the model)."""

    MODEL_DRIVER = "model_driver"
    SUPPORTING_CONTEXT = "supporting_context"
    CONTEXT_ONLY = "context_only"


class AttributionMethod(str, Enum):
    LINEAR_COEFFICIENT = "linear_coefficient"
    SHAP = "shap"
    HEURISTIC_IMPORTANCE = "heuristic_importance"  # multiclass fallback — see service docstring
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class KeyReason:
    rank: int
    feature: str
    football_concept: str
    team: str | None
    direction: str  # "supports" | "opposes"
    contribution: float
    evidence: str
    analysis: str = ""  # filled in by Gemini; empty until narrated


@dataclass(frozen=True)
class CounterSignal:
    feature: str
    football_concept: str
    contribution: float
    analysis: str = ""


@dataclass(frozen=True)
class ContextItem:
    type: str
    description: str
    model_contribution: float
    role: ContextRole


@dataclass(frozen=True)
class NarratedEvidence:
    """One real, verified evidence item (`contextual_reasoning.EvidenceItem`) paired with
    Gemini's/the mock's narration of it — the Sports-Analyst Explainability Upgrade's per-item
    injury/news/lineup detail (spec §5/§6/§17), as opposed to `ContextItem`'s per-category
    rollup. `source_id` always traces back to a real supplied `EvidenceItem`; narration for a
    `source_id` this explanation never supplied is dropped, never trusted (§13 — Gemini may
    summarize evidence, never invent it)."""

    source_id: str
    category: str
    summary: str
    entity_ref: str | None
    source_name: str | None
    published_at: datetime | None
    analysis: str = ""


@dataclass(frozen=True)
class ScorelineAlternative:
    score: str
    probability: float


@dataclass(frozen=True)
class ScorelineReasoning:
    """Correct-Score-only deep reasoning (spec §2/§3/§4) — every number here is read straight off
    `Prediction.probability_distribution`/`feature_snapshot`; only the `*_case`/`alternative_
    comparison` prose is Gemini's. `None` for every other market."""

    selected_score: str
    selected_probability: float
    expected_home_goals: float | None
    expected_away_goals: float | None
    alternatives: tuple[ScorelineAlternative, ...] = field(default_factory=tuple)
    home_goal_case: str = ""
    away_goal_case: str = ""
    alternative_comparison: str = ""


@dataclass(frozen=True)
class FootballExplanation:
    status: ExplanationStatus
    market_key: str
    prediction_value: str
    probability: float
    model_algorithm: str
    attribution_method: AttributionMethod
    key_reasons: tuple[KeyReason, ...] = field(default_factory=tuple)
    counter_signals: tuple[CounterSignal, ...] = field(default_factory=tuple)
    context: tuple[ContextItem, ...] = field(default_factory=tuple)
    verdict: str = ""
    match_profile: str = ""
    confidence_explanation: str = ""
    bottom_line: str = ""
    # Sports-Analyst Explainability Upgrade — additive fields (spec §1/§5/§6/§11/§12). All default
    # to an empty/None "not applicable to this market or Gemini unavailable" state, so a caller
    # built before this upgrade (or a degraded UNAVAILABLE explanation) sees exactly the same
    # shape as before with these fields simply empty.
    market_analysis: str = ""
    scoreline_reasoning: ScorelineReasoning | None = None
    injury_evidence: tuple[NarratedEvidence, ...] = field(default_factory=tuple)
    news_evidence: tuple[NarratedEvidence, ...] = field(default_factory=tuple)
    lineup_evidence: tuple[NarratedEvidence, ...] = field(default_factory=tuple)
    context_quality: str = ""
    unavailable_reason: str | None = None
    subject_ref: str = ""
    model_id: str | None = None
    prompt_version: str = ""
    generated_at: datetime | None = None
    # "gemini" | "mock" | "cached" | "unavailable" — which narrator actually produced this
    # explanation's prose, disclosed rather than left indistinguishable (the mock adapter itself
    # deliberately never labels its own output "mock" in-band, per ADR-008, so this is the one
    # honest place that distinction has to live). "cached" means a prior call's result was reused
    # verbatim — its own original source was not carried into the cache entry.
    narration_source: str = "unavailable"

    @property
    def primary_reasons(self) -> tuple[KeyReason, ...]:
        """The top 2 `key_reasons` by rank (already sorted by real |contribution| — see
        `_split_reasons`) — a real, derived split, not a second ranking. §16's "primary vs
        secondary drivers" distinction without inventing a second attribution pass."""
        return self.key_reasons[:2]

    @property
    def supporting_reasons(self) -> tuple[KeyReason, ...]:
        return self.key_reasons[2:]
