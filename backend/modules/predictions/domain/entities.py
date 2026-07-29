"""Entities for the Prediction Intelligence Platform (Milestone 9).

Mirrors the `predictions` schema sketch from docs/database_schema.md §4
(`prediction_markets`, `models`, `predictions`, `prediction_outcomes`, `model_evaluations`,
`experiments`) plus `FeatureMarketMapping`/`ConfidenceBreakdown`/`ExplanationBundle`/
`PredictionAudit`, which that sketch didn't spell out as separate tables but the Milestone 9
spec's explicit field lists require.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.predictions.domain.explainability import ShapExplanation
from modules.predictions.domain.value_objects import (
    AuditAction,
    ExperimentId,
    FeatureMarketMappingId,
    MarketId,
    MarketKind,
    MarketStatus,
    ModelEvaluationId,
    ModelId,
    ModelStatus,
    PredictionAuditId,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)


@dataclass
class MarketDefinition:
    """One registered prediction market (docs/prediction_markets.md §1). Only a `PRODUCTION`
    market may participate in prediction generation — enforced by `PredictionEngine`, which
    refuses to run against anything else."""

    id: MarketId
    market_key: str  # e.g. "football.match_result" — unique
    sport_code: str
    name: str
    category: str  # e.g. "match_outcome", "team_performance" (docs/prediction_markets.md §3)
    market_kind: MarketKind
    target_type: TargetType
    description: str = ""
    min_historical_window_days: int = 0
    required_data_quality: float = 0.0  # minimum acceptable data-completeness score, 0-1
    explainability_required: bool = True
    confidence_threshold: float = 0.5  # minimum confidence to publish (not just compute) a prediction
    status: MarketStatus = MarketStatus.DRAFT
    owner: str = ""
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    deprecated_at: datetime | None = None

    def is_production(self) -> bool:
        return self.status is MarketStatus.PRODUCTION


@dataclass
class FeatureMarketMapping:
    """One (market, feature) edge in the Feature-to-Market Registry (docs/prediction_markets.md,
    Milestone 9 Part 3 "Cross-Sport Rules": "No prediction model may consume features outside
    its registered Feature-to-Market mapping.")."""

    id: FeatureMarketMappingId
    market_id: MarketId
    feature_key: str
    is_required: bool = True
    importance: float = 0.0  # 0-1, this feature's relative contribution to the market's prediction
    confidence_contribution: float = 0.0  # 0-1, how much this feature's own quality feeds overall confidence
    weight: float = 1.0  # raw scoring weight the generic predictor strategies apply


@dataclass
class ModelDefinition:
    """One trained/candidate model version for a market (docs/database_schema.md §4 `models`).
    Champion/Challenger promotion is `ModelRegistryService`'s job — this entity only records the
    resulting state, it doesn't enforce the single-champion invariant itself.

    Milestone 9.1 additive fields (docs/decisions.md ADR-053): every field below defaults to
    ``None``/empty so every existing `ModelRegistryService.register()` call site (weighted
    predictors registered without any of this) keeps working unchanged. "Rollback History" and
    "Audit History" (Milestone 9.1 Model Registry spec) are deliberately NOT duplicated here —
    `PredictionAudit` (keyed by ``model_id``) already records every registry mutation; adding a
    second history list here would just be two sources of truth for the same facts."""

    id: ModelId
    market_id: MarketId
    model_key: str  # e.g. "football.match_result.heuristic_logistic"
    version: int
    algorithm: str  # e.g. "heuristic_logistic_v1" — see docs/decisions.md for the v1 scope note
    status: ModelStatus = ModelStatus.CANDIDATE
    training_dataset_ref: str | None = None
    calibration_ref: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    promoted_at: datetime | None = None
    retired_at: datetime | None = None
    created_at: datetime | None = None
    framework: str | None = None  # e.g. "lightgbm" — modules.predictions.domain.ml_value_objects.MLFramework.value
    dataset_version: int | None = None  # the Dataset.version this model was trained against
    feature_versions: dict = field(default_factory=dict)  # feature_key -> FeatureDefinition.version at training time
    training_run_ref: str | None = None  # opaque pointer to the TrainingRunResult/experiment that produced this model
    calibration_report_ref: str | None = None  # opaque pointer to a persisted CalibrationReport (task #165)
    feature_importance_ref: str | None = None  # opaque pointer to persisted SHAP/importance artifacts (task #166)
    artifact_ref: str | None = None  # ModelArtifactStorePort ref for the serialized PredictionModelPort payload
    deployment_mode: str | None = None  # "shadow" | "canary" | "live" | None — finer-grained than `status`
    trained_at: datetime | None = None  # when fit() actually ran, distinct from `created_at` (registration time)


@dataclass
class ConfidenceBreakdown:
    """The nine named confidence factors (Milestone 9 Part 4 "CONFIDENCE"). ``composite`` is the
    plain mean of all nine — documented, not a magic number — matching the same
    "no unexplained scoring formula" posture as every other composite score in this codebase
    (e.g. `NewsImpactEngine.impact_score`, Milestone 8)."""

    feature_quality: float
    feature_freshness: float
    historical_accuracy: float
    knowledge_graph_completeness: float
    news_reliability: float
    community_reliability: float
    data_completeness: float
    model_reliability: float
    prediction_stability: float

    @property
    def composite(self) -> float:
        values = (
            self.feature_quality,
            self.feature_freshness,
            self.historical_accuracy,
            self.knowledge_graph_completeness,
            self.news_reliability,
            self.community_reliability,
            self.data_completeness,
            self.model_reliability,
            self.prediction_stability,
        )
        return sum(values) / len(values)


@dataclass
class ExplanationBundle:
    """Every field Milestone 9 Part 4 "EXPLAINABILITY" names, minus Prediction/Probability/
    Confidence themselves (those live on `Prediction`, not duplicated here)."""

    top_positive_features: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    top_negative_features: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    feature_importance: dict = field(default_factory=dict)  # feature_key -> importance (0-1)
    knowledge_graph_evidence: tuple[str, ...] = field(default_factory=tuple)
    news_contribution: tuple[str, ...] = field(default_factory=tuple)
    community_contribution: tuple[str, ...] = field(default_factory=tuple)
    ai_explanation: str = ""
    shap_explanation: ShapExplanation | None = None  # Milestone 9.1 — only set for ML-backed predictors


@dataclass
class Prediction:
    """One generated prediction (docs/database_schema.md §4 `predictions`). Never published
    without confidence, explanation, feature traceability (`feature_snapshot`), a model version,
    and — implicitly, via this entity's own persistence — an audit trail
    (Milestone 9 Part 4 "RULES")."""

    id: PredictionId
    market_id: MarketId
    model_id: ModelId
    subject_ref: str  # stringified fixture/match id this prediction is about
    value: str  # predicted outcome label or numeric value, stringified
    probability: float
    confidence: ConfidenceBreakdown
    explanation: ExplanationBundle
    feature_snapshot: dict  # feature_key -> value, exactly what was fed to the predictor
    model_version: str
    status: PredictionStatus = PredictionStatus.DRAFT
    generated_at: datetime | None = None
    data_freshness: datetime | None = None

    def is_published(self) -> bool:
        return self.status is PredictionStatus.PUBLISHED


@dataclass
class PredictionOutcome:
    """The realized result for a `Prediction`, once known (docs/database_schema.md §4
    `prediction_outcomes`) — feeds `historical_accuracy` (both `ConfidenceBreakdown`'s factor and
    `SourceReliabilityService`-style EWMA updates on the owning `ModelDefinition`)."""

    id: PredictionOutcomeId
    prediction_id: PredictionId
    actual_value: str
    error: float | None
    evaluated_at: datetime


@dataclass
class ModelEvaluation:
    """A point-in-time offline evaluation of a `ModelDefinition` (docs/database_schema.md §4
    `model_evaluations`) — the record a Champion/Challenger promotion decision cites."""

    id: ModelEvaluationId
    model_id: ModelId
    evaluated_at: datetime
    metrics: dict = field(default_factory=dict)
    calibration_report: dict = field(default_factory=dict)


@dataclass
class Experiment:
    """A documented Champion vs. Candidate benchmark (docs/prediction_markets.md §5) —
    "No market's production model changes without" one of these existing first."""

    id: ExperimentId
    market_id: MarketId
    config: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    decision: str | None = None  # "promoted" | "rejected" | "pending"
    created_at: datetime | None = None


@dataclass
class PredictionAudit:
    """One immutable audit entry — every prediction generation and every Admin Action
    (Milestone 9 Part 6) is recorded here, never updated or deleted after creation (same
    "immutable log" shape as `modules.identity`'s audit log, Milestone 6)."""

    id: PredictionAuditId
    action: AuditAction
    actor: str
    occurred_at: datetime
    prediction_id: PredictionId | None = None
    market_id: MarketId | None = None
    model_id: ModelId | None = None
    details: dict = field(default_factory=dict)
