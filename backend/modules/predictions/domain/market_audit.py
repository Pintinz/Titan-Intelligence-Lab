"""Predictive Signal Recovery charter, Phase 1 — the "market matrix" read-only audit record.

One `MarketAuditRecord` assembles, for a single market, every fact
`PredictiveSignalAuditService` can recover from existing repositories without ever training a
model or building a fresh `Dataset` itself (it reads the latest *already-persisted* `Dataset` via
`DatasetRepositoryPort.get_latest_version()` — `TrainingPreflightService`, injected separately,
remains the one place that legitimately rebuilds a dataset, for its own reproducibility check).

Every field is `Optional`/defaulted so a market that has never been trained — no dataset, no
Champion, no experiment — degrades gracefully to an honest "not yet" record instead of raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.predictions.application.training_preflight_service import PreflightCheck
from modules.predictions.domain.dataset import DatasetStatus
from modules.predictions.domain.value_objects import MarketKind, MarketStatus, ModelStatus, TargetType


@dataclass(frozen=True)
class MarketAuditRecord:
    market_key: str
    sport_code: str
    market_kind: MarketKind
    target_type: TargetType
    market_status: MarketStatus

    # --- dataset facts, from DatasetRepositoryPort.get_latest_version() only — never a fresh build ---
    has_persisted_dataset: bool = False
    dataset_version: int | None = None
    dataset_status: DatasetStatus | None = None
    dataset_built_at: datetime | None = None
    sample_count: int | None = None
    feature_count: int | None = None
    positive_rate: float | None = None  # classification only
    target_variance: float | None = None  # regression only
    missing_rate: dict = field(default_factory=dict)  # feature_key -> fraction missing
    earliest_reference_time: datetime | None = None
    latest_reference_time: datetime | None = None

    # --- feature provenance, from FeatureMarketMappingRepositoryPort + FeatureDefinitionRepositoryPort ---
    required_feature_keys: tuple[str, ...] = field(default_factory=tuple)
    optional_feature_keys: tuple[str, ...] = field(default_factory=tuple)
    unresolved_feature_keys: tuple[str, ...] = field(default_factory=tuple)  # no ACTIVE FeatureDefinition
    leakage_unsafe_required_keys: tuple[str, ...] = field(default_factory=tuple)  # POST_MATCH_ONLY among required
    unknown_provenance_keys: tuple[str, ...] = field(default_factory=tuple)  # UNKNOWN_PROVENANCE among required

    # --- preflight, from TrainingPreflightService.check() — None when the audit ran cheap-mode ---
    preflight_ready: bool | None = None
    preflight_checks: tuple[PreflightCheck, ...] | None = None

    # --- Champion + evaluation, from ModelRepositoryPort + ModelEvaluationRepositoryPort ---
    champion_model_key: str | None = None
    champion_version: int | None = None
    champion_algorithm: str | None = None
    champion_status: ModelStatus | None = None
    champion_is_genuinely_trained: bool | None = None
    champion_trained_at: datetime | None = None
    champion_latest_evaluation_metrics: dict = field(default_factory=dict)
    champion_latest_calibration_report: dict = field(default_factory=dict)
    champion_latest_evaluated_at: datetime | None = None

    # --- prediction/outcome volume, from PredictionRepositoryPort/PredictionOutcomeRepositoryPort.count_by_market() ---
    prediction_count: int | None = None
    outcome_count: int | None = None

    # --- latest model_selection Experiment, from ExperimentRepositoryPort.list_by_market() ---
    latest_experiment_id: str | None = None
    latest_experiment_created_at: datetime | None = None
    baseline_candidate_algorithms: tuple[str, ...] = field(default_factory=tuple)
    winner_is_baseline: bool | None = None
    winning_algorithm: str | None = None
    candidate_scores: dict = field(default_factory=dict)  # algorithm -> score (candidate.<algo> prefix stripped)
    ranking_metric: str | None = None
    ranking_value: float | None = None
