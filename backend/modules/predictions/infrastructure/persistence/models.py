"""SQLAlchemy models for the `predictions` schema (Milestone 9, docs/database_schema.md §4,
docs/prediction_markets.md). Client-side Python defaults throughout — the async-refresh-after-
flush pitfall documented in docs/decisions.md ADR-007, avoided the same way every other module's
persistence layer already does.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, MetaData, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="predictions")


class Base(DeclarativeBase):
    metadata = metadata


class MarketDefinitionModel(Base):
    __tablename__ = "prediction_markets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    sport_code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(64), index=True)
    market_kind: Mapped[str] = mapped_column(String(32))
    target_type: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text, default="")
    min_historical_window_days: Mapped[int] = mapped_column(Integer, default=0)
    required_data_quality: Mapped[float] = mapped_column(Float, default=0.0)
    explainability_required: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    owner: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Milestone 9.2 additive fields — see modules.predictions.domain.market_outcome_registry.
    outcome_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allowed_values: Mapped[list | None] = mapped_column(JSON, nullable=True)
    resolver_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gemini_prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeatureMarketMappingModel(Base):
    __tablename__ = "feature_market_mappings"
    __table_args__ = (UniqueConstraint("market_id", "feature_key", name="uq_feature_market_mapping"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_markets.id"), index=True)
    feature_key: Mapped[str] = mapped_column(String(200), index=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    importance: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_contribution: Mapped[float] = mapped_column(Float, default=0.0)
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class ModelDefinitionModel(Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("model_key", "version", name="uq_model_key_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_markets.id"), index=True)
    model_key: Mapped[str] = mapped_column(String(200), index=True)
    version: Mapped[int] = mapped_column(Integer)
    algorithm: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="candidate", index=True)
    training_dataset_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    calibration_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Milestone 9.1 additive columns (docs/decisions.md ADR-053) — all nullable, every M9 row keeps working.
    framework: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dataset_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    training_run_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    calibration_report_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    feature_importance_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deployment_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Milestone 4 provenance foundation (docs/milestone4_verification_report.md) — "PROVENANCE_
    # VERIFIED" | "PROVENANCE_UNVERIFIED". Defaults every existing and future row to unverified;
    # a model earns PROVENANCE_VERIFIED only after an explicit trace (dataset -> feature version
    # -> training run -> model) confirms its training data's point-in-time provenance. Never
    # silently upgraded — see scripts/trace_football_champion_provenance.py.
    provenance_status: Mapped[str] = mapped_column(String(24), default="PROVENANCE_UNVERIFIED")
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PredictionModel(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_markets.id"), index=True)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"), index=True)
    subject_ref: Mapped[str] = mapped_column(String(200), index=True)
    value: Mapped[str] = mapped_column(String(200))
    probability: Mapped[float] = mapped_column(Float)
    confidence: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_freshness: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # See modules.predictions.domain.entities.Prediction.prediction_cutoff docstring — the
    # persisted leakage boundary, nullable only because rows from before this column existed have
    # none (migration 0047 backfills them from generated_at, the value they actually used).
    prediction_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Universal Probability Engine (2026-08-02) — see modules.predictions.domain.entities.Prediction
    # docstring for the CLASSIFICATION-vs-REGRESSION field-group split these five columns store.
    probability_distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_interval_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_interval_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    # See modules.predictions.domain.entities.Prediction.predictor_provenance docstring — real
    # prod incident audit (2026-08-23): "trained_model" | "formula_fallback", nullable only
    # because rows from before this column existed have no recorded provenance (never inferred
    # after the fact — that's exactly the conflation this column exists to close).
    predictor_provenance: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # See modules.predictions.domain.entities.Prediction.calibration_status docstring — Section 31
    # audit fix (2026-08-23): "calibrated" | "uncalibrated", nullable for the same
    # before-this-column-existed reason as predictor_provenance above.
    calibration_status: Mapped[str | None] = mapped_column(String(32), nullable=True)


class PredictionOutcomeModel(Base):
    __tablename__ = "prediction_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    prediction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("predictions.id"), unique=True, index=True)
    actual_value: Mapped[str] = mapped_column(String(200))
    error: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PredictionContextReviewModel(Base):
    """Gemini Prediction Reasoning Engine — one persisted `ContextualReview` per prediction
    (`unique=True` on `prediction_id`: a fresh `review()` call overwrites the prior row for the
    same prediction rather than accumulating history, matching this being a "current assessment"
    concept, not an append-only audit log like `PredictionAuditModel`)."""

    __tablename__ = "prediction_context_reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    prediction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("predictions.id"), unique=True, index=True)
    market_key: Mapped[str] = mapped_column(String(200), index=True)
    base_selection: Mapped[str] = mapped_column(String(200))
    base_probability: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(32))
    statistical_baseline: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(32))
    overall_assessment: Mapped[str] = mapped_column(Text, default="")
    contextual_assessment: Mapped[dict] = mapped_column(JSON, default=dict)
    supporting_factors: Mapped[list] = mapped_column(JSON, default=list)
    risk_factors: Mapped[list] = mapped_column(JSON, default=list)
    missing_context: Mapped[list] = mapped_column(JSON, default=list)
    reconsideration_direction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reconsideration_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    material_change: Mapped[bool] = mapped_column(Boolean, default=False)
    context_confidence_level: Mapped[str] = mapped_column(String(16))
    context_confidence_score: Mapped[float] = mapped_column(Float)
    evidence_quality: Mapped[dict] = mapped_column(JSON, default=dict)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    prediction_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FootballExplanationModel(Base):
    """Sports-Analyst Explainability — one persisted `FootballExplanation` per prediction
    (`unique=True` on `prediction_id`, same "current assessment, overwritten on re-explain"
    posture as `PredictionContextReviewModel`)."""

    __tablename__ = "prediction_football_explanations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    prediction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("predictions.id"), unique=True, index=True)
    market_key: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(32))
    prediction_value: Mapped[str] = mapped_column(String(200))
    probability: Mapped[float] = mapped_column(Float)
    model_algorithm: Mapped[str] = mapped_column(String(64), default="")
    attribution_method: Mapped[str] = mapped_column(String(32))
    key_reasons: Mapped[list] = mapped_column(JSON, default=list)
    counter_signals: Mapped[list] = mapped_column(JSON, default=list)
    context: Mapped[list] = mapped_column(JSON, default=list)
    verdict: Mapped[str] = mapped_column(Text, default="")
    match_profile: Mapped[str] = mapped_column(Text, default="")
    confidence_explanation: Mapped[str] = mapped_column(Text, default="")
    bottom_line: Mapped[str] = mapped_column(Text, default="")
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelEvaluationModel(Base):
    __tablename__ = "model_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"), index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    calibration_report: Mapped[dict] = mapped_column(JSON, default=dict)


class ExperimentModel(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_markets.id"), index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PredictionAuditModel(Base):
    __tablename__ = "prediction_audits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(200))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("predictions.id"), nullable=True, index=True)
    market_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prediction_markets.id"), nullable=True, index=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("models.id"), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


# --- Milestone 9.1 Enterprise ML Platform tables --------------------------------------------


class DatasetModel(Base):
    """Dataset Platform (task #160). ``samples`` is the full `TrainingSample` list as JSONB — an
    honest v1 choice (matches this codebase's "documented, real, not overengineered" posture);
    object-storage-backed sample payloads for very large datasets are future work, not fabricated
    now."""

    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("market_id", "version", name="uq_dataset_market_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_markets.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    samples: Mapped[list] = mapped_column(JSON, default=list)
    statistics: Mapped[dict] = mapped_column(JSON, default=dict)
    lineage: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_issues: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrainingRunModel(Base):
    """Training Platform run record (task #161) — one row per `TrainingPipelineService.train()`
    call, the audit trail behind a `ModelDefinition.training_run_ref`."""

    __tablename__ = "training_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_markets.id"), index=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("models.id"), nullable=True, index=True)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id"), nullable=True, index=True)
    algorithm: Mapped[str] = mapped_column(String(64))
    framework: Mapped[str] = mapped_column(String(32))
    train_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    test_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_order: Mapped[list] = mapped_column(JSON, default=list)
    selected_features: Mapped[list] = mapped_column(JSON, default=list)
    samples_used: Mapped[int] = mapped_column(Integer, default=0)
    outliers_removed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalibrationReportModel(Base):
    """Calibration Reporting (task #165) — one row per `CalibrationReportBuilder.build()` call,
    the persisted record a `ModelDefinition.calibration_report_ref` points to."""

    __tablename__ = "calibration_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"), index=True)
    method: Mapped[str] = mapped_column(String(32))
    sample_count: Mapped[int] = mapped_column(Integer)
    expected_calibration_error: Mapped[float] = mapped_column(Float)
    brier_score: Mapped[float] = mapped_column(Float)
    reliability_curve: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CalibrationParametersModel(Base):
    """Phase 3 audit fix — `PlattScalingCalibrator` was an in-memory-only, per-process singleton:
    a `fit()` call in one process (e.g. a Celery worker) never reached another process's own
    calibrator instance (e.g. the API server), silently leaving live inference on the unfitted
    identity transform. One row per model — the durable store `calibrate()` now reads through on
    a cache miss, and `fit()` now writes to, so a fit reaches every process regardless of which
    one ran it."""

    __tablename__ = "calibration_parameters"

    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"), primary_key=True)
    a: Mapped[float] = mapped_column(Float, default=1.0)
    b: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    fitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChallengerEvaluationModel(Base):
    """Continuous Outcome Learning Engine — one row per `ChallengerEvaluationService.evaluate()`
    call. Phase 3 audit finding: this record previously lived only in
    `InMemoryModelComparisonRepository`, wiped on every worker restart, unlike every other
    experiment/comparison artifact in this schema — this table closes that gap."""

    __tablename__ = "challenger_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_markets.id"), index=True)
    challenger_model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    champion_model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("models.id"), nullable=True)
    challenger_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    champion_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verdict: Mapped[str] = mapped_column(String(32))
    decisive_metric: Mapped[str] = mapped_column(String(64))
    holdout_sample_count: Mapped[int] = mapped_column(Integer)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class FeatureImportanceReportModel(Base):
    """SHAP Explainability (task #166) — persisted global importance snapshot a
    `ModelDefinition.feature_importance_ref` points to. Per-instance local SHAP values are
    computed on demand (`SHAPExplainerService.explain_instance`), not persisted per prediction."""

    __tablename__ = "feature_importance_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"), index=True)
    global_importance: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LatencySampleModel(Base):
    """Model Monitoring (task #167) — backs a SQL `LatencySampleRepositoryPort` implementation
    (the in-memory one is what tests/dev use today; this table is ready for when one is wired)."""

    __tablename__ = "latency_samples"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_markets.id"), index=True)
    duration_ms: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RetrainingJobModel(Base):
    """`RetrainingScheduler.should_retrain()` decisions (task #161) — an audit trail of every
    retraining decision, not just the latest one."""

    __tablename__ = "retraining_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prediction_markets.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    trigger_reason: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelArtifactModel(Base):
    """Model Serving (task #168) — artifact *registry* metadata only; the serialized model bytes
    themselves live wherever `ModelArtifactStorePort` put them (local filesystem in dev), not in
    this row (docs/decisions.md ADR-008 adapter-swap posture applied to storage location)."""

    __tablename__ = "model_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"), index=True)
    storage_ref: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PredictionCreditModel(Base):
    """Mobile V1 monetization — one row per user, `user_id` unique (no FK across schemas to
    `identity.users`, matching this app's existing convention of not FK-ing across module
    schemas; the router only ever writes/reads this keyed off an authenticated `User.id`)."""

    __tablename__ = "prediction_credits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)
    available_predictions: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_free_predictions_used: Mapped[int] = mapped_column(Integer, default=0)
    rewarded_predictions_granted: Mapped[int] = mapped_column(Integer, default=0)
    rewarded_ads_completed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PredictionRewardEventModel(Base):
    """The reward ledger (Phase 6) — `provider_event_id`'s unique constraint is the actual
    idempotency guarantee (Phase 5): a duplicate insert fails at the DB layer regardless of any
    application-level check, so a replayed AdMob SSV callback can never grant credits twice even
    under concurrent duplicate delivery."""

    __tablename__ = "prediction_reward_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    provider: Mapped[str] = mapped_column(String(32))
    reward_type: Mapped[str] = mapped_column(String(64))
    credits_granted: Mapped[int] = mapped_column(Integer)
    provider_event_id: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="granted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("provider_event_id", name="uq_prediction_reward_event_provider_event"),)
