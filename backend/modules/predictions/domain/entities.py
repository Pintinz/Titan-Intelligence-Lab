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
from uuid import UUID

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
    OutcomeType,
    PredictionAuditId,
    PredictionCreditId,
    PredictionId,
    PredictionOutcomeId,
    PredictionRewardEventId,
    PredictionStatus,
    TargetType,
)

# Mobile V1 monetization (AdMob rewarded-prediction unlock, no billing) — see
# PredictionCreditService for the enforcement logic. Free-tier constants live here, not scattered
# across the router/service, since both need the exact same numbers.
INITIAL_FREE_PREDICTIONS = 5
REWARDED_AD_CREDIT_GRANT = 2


class PredictionCreditExhaustedError(Exception):
    """Raised by `PredictionCreditRepositoryPort.consume()` when a user has 0 available
    predictions — the router turns this into HTTP 402 with a machine-readable
    `PREDICTION_CREDIT_REQUIRED` body, never a bare 500."""


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
    # Milestone 9.2 (Market Registry & Prediction Domain Normalization) additive fields — every
    # existing `MarketRegistryService.register()` call site (market_seeding.py x4 sports) keeps
    # working unchanged, same posture as the 9.1 `ModelDefinition` fields above. `outcome_type`/
    # `allowed_values` are the market's real-world answer space (see
    # `modules.predictions.domain.market_outcome_registry`); `resolver_key` is a stable string ref
    # into that same registry's resolver table, never a live callable (matches the opaque-ref
    # pattern `training_run_ref`/`artifact_ref` already use on `ModelDefinition`).
    outcome_type: OutcomeType | None = None
    allowed_values: tuple[str, ...] = field(default_factory=tuple)
    resolver_key: str | None = None
    gemini_prompt_template: str | None = None

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
    # Forensic audit §15 "Model Artifact Integrity" — sha256 hex digest of the exact bytes saved to
    # `artifact_ref` at training time (`ModelLoaderService.compute_artifact_checksum`). `None` for
    # any model registered before this field existed, or by a path not yet updated to compute one
    # — `ModelLoaderService.load()` only verifies when a checksum is actually present, it never
    # treats "no checksum recorded" as itself a failure.
    artifact_checksum: str | None = None
    deployment_mode: str | None = None  # "shadow" | "canary" | "live" | None — finer-grained than `status`
    trained_at: datetime | None = None  # when fit() actually ran, distinct from `created_at` (registration time)
    # Milestone 4 provenance foundation — "PROVENANCE_VERIFIED" | "PROVENANCE_UNVERIFIED" |
    # "PROVENANCE_COMPROMISED". The third value is a forensic-audit addition (Critical Fix #1,
    # §10 "Contaminated Model Policy"): written only by `scripts/assess_training_integrity.py`,
    # never invented as a default, when at least one feature key this model's market actually
    # consumes (per `FeatureMarketMapping`) has a confirmed point-in-time violation in the offline
    # feature store (`scripts/scan_feature_leakage.py`) — i.e. a real, non-hypothetical reason to
    # distrust this specific model's training data, not a blanket "everything old is suspect."
    # `PROVENANCE_VERIFIED` still means what Milestone 4 defined: an explicitly human-reviewed,
    # independently-traceable training lineage. `PROVENANCE_COMPROMISED` is a stronger, narrower
    # claim than "unverified" — it says the training data was actively checked and found bad, not
    # merely never checked — so `ModelRegistryService.promote_to_champion` refuses it outright
    # (see `is_training_compromised`) rather than merely leaving it un-promoted by omission.
    provenance_status: str = "PROVENANCE_UNVERIFIED"

    def is_training_compromised(self) -> bool:
        return self.provenance_status == "PROVENANCE_COMPROMISED"

    def is_genuinely_trained(self) -> bool:
        """Milestone 4 status honesty (Rule 13): a handful of markets (e.g.
        `football.first_half_winner`) only have a placeholder Champion — model_key like
        "*.heuristic_logistic", `algorithm="heuristic_logistic_v1"`, `artifact_ref=None`,
        `trained_at=None` — registered solely to unblock `PredictionContextBuilder` (which raises
        `NoChampionModelError` only when a market has *no* Champion at all) rather than a genuinely
        fit-and-validated model. `artifact_ref is not None` is the existing, already-load-bearing
        signal for "was this actually trained": `PredictionEngine._resolve_predictor` already
        requires it before using a trained model instead of falling back to the generic formula
        predictor. Reused here rather than adding a new field, since it already partitions the 19
        current football Champions into exactly the real 14 vs. the placeholder 5."""
        return self.artifact_ref is not None


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
    (Milestone 9 Part 4 "RULES").

    Universal Probability Engine (2026-08-02) additive fields, gated by the market's own
    `TargetType` in `PredictionEngine.generate()` — a `Prediction` never populates both groups:

    - `probability_distribution` — every outcome's calibrated probability for a
      `TargetType.CLASSIFICATION` market (including `CORRECT_SCORE`-shaped ones, where it's a
      ranked Top-N scoreline distribution), keyed by the market's real outcome labels. ``value``/
      ``probability`` above remain the single winning outcome and its probability — this is the
      full picture behind that pick, what a frontend renders as "Alternative Outcomes". Empty for
      a `TargetType.REGRESSION` market (no discrete outcome space to distribute over).
    - `confidence_interval`/`expected_error` — populated only for a `TargetType.REGRESSION`
      market, where ``value`` is the predicted continuous number itself, not a classification
      label, and a single probability was never a meaningful thing to publish for it (Universal
      Probability Engine spec: "regression markets return Prediction / Confidence Interval /
      Expected Error / Reliability, not a fake probability" — "Reliability" is
      `confidence.model_reliability`, already tracked, not duplicated here). Both are `None` when
      the market has no `PredictionOutcome` history yet to derive them from — an honest gap, never
      a fabricated interval."""

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
    # The leakage boundary this prediction was actually generated against — every feature read
    # and every evidence item (news/injury/transfer/lineup) gathered for this prediction must be
    # dated at or before this instant. Distinct from `generated_at` in *meaning* even though both
    # are set to the same `now` at live-generation time: `generated_at` records when generation
    # happened, `prediction_cutoff` records the temporal boundary that generation respected — the
    # field a leakage audit/test binds to, and the one a future historical-reconstruction caller
    # would set to something earlier than wall-clock `now`.
    prediction_cutoff: datetime | None = None
    probability_distribution: dict = field(default_factory=dict)  # real label -> calibrated probability
    confidence_interval: tuple[float, float] | None = None  # (low, high), regression markets only
    expected_error: float | None = None  # historical MAE for this market, regression markets only
    # Real prod incident audit (2026-08-23): `model_id`/`model_version` above always name the
    # market's Champion, even on the run where `PredictionEngine._resolve_predictor` fell back to
    # the generic formula predictor because the Champion's own artifact failed to load — nothing
    # previously recorded which predictor actually produced `value`/`probability`, so the API
    # could only ever report the Champion, misattributing formula-computed predictions as
    # ML-computed. Set explicitly at generation time, one of "trained_model" | "formula_fallback";
    # `None` only for predictions generated before this field existed — never inferred after the
    # fact from `model_id` alone, since that's exactly the conflation this field exists to close.
    predictor_provenance: str | None = None
    # Forensic audit §3/§13 — WHY `predictor_provenance` is "formula_fallback", when it is. One of
    # "NO_ARTIFACT_REGISTERED" (a placeholder Champion — never trained at all), "ARTIFACT_LOAD_FAILURE"
    # (missing/unreachable artifact store), "ARTIFACT_INTEGRITY_MISMATCH" (checksum mismatch — see
    # `ArtifactIntegrityError`), "ARTIFACT_DESERIALIZE_FAILURE" (corrupt/incompatible payload), or
    # "UNKNOWN_ARTIFACT_ERROR" for anything else. `None` whenever `predictor_provenance ==
    # "trained_model"` (no fallback occurred) or for predictions generated before this field existed.
    fallback_reason: str | None = None
    # Section 31 audit fix (2026-08-23), extended by Phase 4 (Calibration Integrity, 2026-08-25):
    # whether `self.probability` actually passed through a genuinely fitted, fresh calibration, or
    # an identity/untrusted pass-through. One of "UNFITTED" (no calibration has ever been fitted
    # for this model — identity pass-through), "FITTED" (a fresh fit was applied, or the Champion's
    # own artifact already bakes in calibration via `ModelDefinition.calibration_ref`), "STALE" (a
    # fit exists but is older than the configured staleness window — still applied, but flagged),
    # or "INVALID" (a fit exists but produced a non-finite probability — discarded, identity used
    # instead). `None` only for predictions generated before this field existed, or with the legacy
    # "calibrated"/"uncalibrated" values from before this four-state vocabulary existed — never
    # inferred after the fact for either. Same "never claim more than actually happened" posture as
    # `predictor_provenance` — the API must not call a raw pass-through "calibrated" just because a
    # calibrator object was wired.
    calibration_status: str | None = None
    # Phase 4 (Calibration Integrity, 2026-08-25) — the predictor's pre-calibration probability for
    # `value` (same "P(the published value)" semantic as `probability` above, computed the same
    # way but with the identity/no-op calibration applied instead of whatever `calibration_status`
    # describes). Lets a caller show "raw vs. calibrated" distinctly instead of only ever seeing
    # the already-calibrated number. `None` only for predictions generated before this field
    # existed.
    raw_probability: float | None = None
    # Phase 4 — how many real (raw_probability, actual_outcome) samples backed the calibration
    # fit named by `calibration_status`, from `CalibratorPort.get_metadata()`. `None` when
    # `calibration_status` is "UNFITTED", or for a model-baked calibration (`calibration_ref` on
    # the model itself — its own training-time sample count isn't tracked as calibration metadata
    # here), or for predictions generated before this field existed.
    calibration_sample_count: int | None = None
    # Phase 4 — when that calibration fit was produced. Same nullability posture as
    # `calibration_sample_count` above; together they're what a caller needs to judge whether a
    # "FITTED"/"STALE" status is still trustworthy.
    calibration_fitted_at: datetime | None = None

    def is_published(self) -> bool:
        return self.status is PredictionStatus.PUBLISHED


@dataclass
class PredictionOutcome:
    """The realized result for a `Prediction`, once known (docs/database_schema.md §4
    `prediction_outcomes`) — feeds `historical_accuracy` (both `ConfidenceBreakdown`'s factor and
    `SourceReliabilityService`-style EWMA updates on the owning `ModelDefinition`).

    `raw_home_goals`/`raw_away_goals` (statistical-baseline charter, Phase 3): the real final-score
    goal counts, populated only by the resolvers backing football's 12 goals/score markets
    (`outcome_resolution_service.py`'s GRID and binary branches) — `None` for every other market.
    Exists so a genuine Poisson model can fit λ_home/λ_away directly, instead of the derived 0/1
    classification label every other candidate in the roster reads."""

    id: PredictionOutcomeId
    prediction_id: PredictionId
    actual_value: str
    error: float | None
    evaluated_at: datetime
    raw_home_goals: int | None = None
    raw_away_goals: int | None = None


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


@dataclass
class PredictionCredit:
    """One row per user — a persistent, server-authoritative balance, not a rolling window like
    `modules.billing.UsageCounter` (that resets per `window_key`; this never resets on its own,
    only grows via a verified rewarded-ad grant or shrinks via a successful generation).
    `lifetime_free_predictions_used`/`rewarded_predictions_granted`/`rewarded_ads_completed` are
    pure lifetime counters for display/analytics — `available_predictions` is the only field that
    actually gates access."""

    id: PredictionCreditId
    user_id: UUID
    available_predictions: int
    lifetime_free_predictions_used: int
    rewarded_predictions_granted: int
    rewarded_ads_completed: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PredictionRewardEvent:
    """One immutable ledger row per rewarded-ad completion (or attempted duplicate) — the
    idempotency + audit record Phase 6/Phase 5 require. `provider_event_id` (the AdMob SSV
    callback's `transaction_id`) carries a real unique constraint at the DB layer
    (`uq_prediction_reward_event_provider_event`); a duplicate submission fails that constraint
    and is reported back as `created=False` rather than raising past the caller, so a retried or
    replayed callback is always safe."""

    id: PredictionRewardEventId
    user_id: UUID
    provider: str
    reward_type: str
    credits_granted: int
    provider_event_id: str
    status: str
    created_at: datetime | None = None
