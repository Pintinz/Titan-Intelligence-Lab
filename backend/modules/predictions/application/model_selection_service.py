"""Automatic Model Selection (Milestone 9.1): trains every candidate in a configurable roster
against the same approved `Dataset` via the EXISTING `TrainingPipelineService` (Milestone 9.1 task
#161), ranks candidates by their held-out test metric, and registers the winner as a CANDIDATE ->
CHALLENGER through the EXISTING `ModelRegistryService` (Milestone 9, extended additively in task
#163) — human approval to CHAMPION still goes through that service's own `promote_to_champion`,
untouched here. "Never hardcode algorithm selection" (Milestone 9.1 spec) is satisfied by ranking
real benchmark numbers, not by this service ever picking one algorithm by name.

Audit finding (2026-08-02): registration previously left `artifact_ref` unset, so a Challenger's
actual fitted model was never persisted anywhere — `ModelLoaderService`/`TrainedModelPredictor`
(real, tested classes built specifically to serve a trained model in production) had nothing to
load, and every live prediction fell back to the generic weighted-formula predictors regardless
of what the Model Registry said. `select_and_register_challenger` now serializes the winning
model and saves it via `ModelArtifactStorePort` before registering, so a later Champion promotion
has a real artifact `PredictionEngine` can actually serve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.features.domain.value_objects import FeatureKey
from modules.features.ports.repositories import FeatureDefinitionRepositoryPort
from modules.predictions.application.experiment_tracking_service import ExperimentTrackingService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.training_pipeline_service import EvaluationMetrics, TrainingPipelineService
from modules.predictions.domain.dataset import Dataset, SplitStrategy
from modules.predictions.domain.entities import ModelDefinition
from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.model_selection import CandidateSpec, ModelSelectionResult, NoViableCandidateError
from modules.predictions.domain.training_run import TrainingRun, TrainingRunId
from modules.predictions.domain.value_objects import MarketId, TargetType
from modules.predictions.infrastructure.ml.catboost_adapter import CatBoostAdapter
from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import FootballGoalsPoissonAdapter
from modules.predictions.infrastructure.ml.lightgbm_adapter import LightGBMAdapter
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.infrastructure.ml.xgboost_adapter import XGBoostAdapter
from modules.predictions.ports.ml_model import (
    InsufficientTrainingDataError,
    ModelArtifactStorePort,
    PredictionModelPort,
    UnsupportedAlgorithmForTargetTypeError,
)
from modules.predictions.ports.training_run_repository import TrainingRunRepositoryPort

DEFAULT_CLASSIFICATION_CANDIDATES: tuple[CandidateSpec, ...] = (
    CandidateSpec(MLAlgorithm.LIGHTGBM_GBM, MLFramework.LIGHTGBM),
    CandidateSpec(MLAlgorithm.XGBOOST_GBM, MLFramework.XGBOOST),
    CandidateSpec(MLAlgorithm.CATBOOST_GBM, MLFramework.CATBOOST),
    CandidateSpec(MLAlgorithm.RANDOM_FOREST, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.EXTRA_TREES, MLFramework.SKLEARN),
    # Statistical baseline (charter: "every trainable market should have a simple statistical
    # baseline before an ML Champion can be promoted") — competes in the same roster as every ML
    # candidate rather than being assumed inferior; is_baseline only tags it for reporting.
    CandidateSpec(MLAlgorithm.LOGISTIC_REGRESSION, MLFramework.SKLEARN, is_baseline=True),
    CandidateSpec(MLAlgorithm.RIDGE, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.ELASTIC_NET, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.SVM, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.GAUSSIAN_NB, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.MLP, MLFramework.SKLEARN),
)

DEFAULT_REGRESSION_CANDIDATES: tuple[CandidateSpec, ...] = (
    CandidateSpec(MLAlgorithm.LIGHTGBM_GBM, MLFramework.LIGHTGBM),
    CandidateSpec(MLAlgorithm.XGBOOST_GBM, MLFramework.XGBOOST),
    CandidateSpec(MLAlgorithm.CATBOOST_GBM, MLFramework.CATBOOST),
    CandidateSpec(MLAlgorithm.RANDOM_FOREST, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.EXTRA_TREES, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.RIDGE, MLFramework.SKLEARN, is_baseline=True),
    CandidateSpec(MLAlgorithm.ELASTIC_NET, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.SVM, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.MLP, MLFramework.SKLEARN),
    # Statistical baselines proper (Milestone: statistical-baseline charter) — genuine count-shaped
    # GLMs, not just a plain linear model reused as a stand-in. Compete for real against the rest
    # of the roster; ranking is empirical, never assumed.
    CandidateSpec(MLAlgorithm.POISSON_GLM, MLFramework.SKLEARN, is_baseline=True),
    CandidateSpec(MLAlgorithm.TWEEDIE_GLM, MLFramework.SKLEARN, is_baseline=True),
)


def _build_model(
    candidate: CandidateSpec, target_type: TargetType, class_labels: tuple[str, ...] = ()
) -> PredictionModelPort:
    """``class_labels`` (multiclass classification support, 2026-08-06) is set on every candidate
    before `fit()` — empty for a binary-classification/regression market (every adapter's default),
    non-empty (the market's `MARKET_OUTCOME_CATALOG` label ordering) for a market like
    football.match_winner/football.correct_score with more than two real outcomes."""
    if candidate.framework is MLFramework.LIGHTGBM:
        return LightGBMAdapter(target_type=target_type, params=dict(candidate.params), class_labels=class_labels)
    if candidate.framework is MLFramework.XGBOOST:
        return XGBoostAdapter(target_type=target_type, params=dict(candidate.params), class_labels=class_labels)
    if candidate.framework is MLFramework.CATBOOST:
        return CatBoostAdapter(target_type=target_type, params=dict(candidate.params), class_labels=class_labels)
    if candidate.framework is MLFramework.POISSON_GOALS:
        return FootballGoalsPoissonAdapter(target_type=target_type, params=dict(candidate.params), class_labels=class_labels)
    return SklearnAdapter(
        algorithm=candidate.algorithm, target_type=target_type, params=dict(candidate.params), class_labels=class_labels
    )


def _ranking_metric_name(target_type: TargetType) -> str:
    # Continuous Outcome Learning Engine (2026-08-08): classification candidates now rank by log
    # loss, not accuracy — spec §8's priority order ("For probability predictions prioritize:
    # 1. Log Loss ...") applies to picking a winner among the roster exactly as much as it applies
    # to comparing a Challenger against the Champion (`model_comparison_service.py`), so both use
    # the identical metric. Regression has no probability to score, so it's unaffected — MAE stays.
    return "log_loss" if target_type is TargetType.CLASSIFICATION else "mae"


def _ranking_value(target_type: TargetType, test_metrics) -> float | None:
    if target_type is TargetType.CLASSIFICATION:
        return test_metrics.log_loss
    return test_metrics.mae


def _is_better(target_type: TargetType, candidate_value: float, current_best: float) -> bool:
    # Both metrics are now "lower is better" post log-loss switch — kept as an explicit branch
    # (rather than collapsing to one `<` everywhere) so a future metric with the opposite
    # direction doesn't have to fight this function's assumption silently.
    del target_type
    return candidate_value < current_best


def _evaluation_metrics_to_dict(metrics: EvaluationMetrics) -> dict:
    return {
        "accuracy": metrics.accuracy, "precision": metrics.precision, "recall": metrics.recall,
        "f1": metrics.f1, "mae": metrics.mae, "rmse": metrics.rmse, "log_loss": metrics.log_loss,
    }


@dataclass
class AutomaticModelSelectionService:
    training_pipeline: TrainingPipelineService
    model_registry: ModelRegistryService
    experiments: ExperimentTrackingService
    artifact_store: ModelArtifactStorePort
    # Milestone 4 provenance foundation — resolves `dataset.lineage.feature_keys` to their real
    # current `FeatureDefinition.version` at registration time, closing the bug where
    # `ModelDefinition.feature_versions` was silently dropped (see `select_and_register_challenger`).
    feature_definitions: FeatureDefinitionRepositoryPort | None = None
    # Training Run audit trail — the record behind `ModelDefinition.training_run_ref`. Optional
    # (defaults to `None`, matching this class's existing `feature_definitions` posture) so every
    # existing caller/test that doesn't pass it keeps working unchanged; when wired,
    # `select_and_register_challenger` persists a real `TrainingRun` row for the winning
    # candidate instead of leaving `training_run_ref` permanently unset.
    training_runs: TrainingRunRepositoryPort | None = None

    async def select(
        self,
        dataset: Dataset,
        target_type: TargetType,
        candidates: tuple[CandidateSpec, ...] | None = None,
        # Milestone 4 Rule 14: TRAIN_TEST (random shuffle) is non-compliant as the production
        # default for time-dependent sports data — TIME_SERIES_SPLIT respects sample order
        # instead. Explicitly passing `split_strategy=SplitStrategy.TRAIN_TEST` remains possible
        # for any caller (e.g. an existing test) that has a specific reason to.
        split_strategy: SplitStrategy = SplitStrategy.TIME_SERIES_SPLIT,
        **split_kwargs,
    ) -> ModelSelectionResult:
        roster = candidates or (
            DEFAULT_CLASSIFICATION_CANDIDATES if target_type is TargetType.CLASSIFICATION else DEFAULT_REGRESSION_CANDIDATES
        )

        best: tuple[CandidateSpec, float, PredictionModelPort] | None = None
        best_result = None
        skipped: list[tuple[CandidateSpec, str]] = []
        scored: list[tuple[CandidateSpec, float]] = []

        for candidate in roster:
            model = _build_model(candidate, target_type, dataset.lineage.class_labels)
            try:
                result = await self.training_pipeline.train(model, dataset, split_strategy=split_strategy, **split_kwargs)
            except (InsufficientTrainingDataError, UnsupportedAlgorithmForTargetTypeError) as exc:
                skipped.append((candidate, str(exc)))
                continue

            value = _ranking_value(target_type, result.test_metrics)
            if value is None:
                skipped.append((candidate, "training produced no evaluable test metric"))
                continue

            scored.append((candidate, value))
            if best is None or _is_better(target_type, value, best[1]):
                best = (candidate, value, result.model)
                best_result = result

        if best is None:
            raise NoViableCandidateError(
                f"no candidate in the roster of {len(roster)} could be trained on dataset "
                f"v{dataset.version} for market {dataset.market_id} — skipped: {[(c.algorithm.value, r) for c, r in skipped]}"
            )

        winning_candidate, winning_value, winning_model = best
        return ModelSelectionResult(
            winning_candidate=winning_candidate,
            winning_train_metrics=best_result.train_metrics,
            winning_test_metrics=_evaluation_metrics_to_dict(best_result.test_metrics),
            winning_feature_order=best_result.feature_order,
            winning_selected_features=best_result.selected_features,
            winning_samples_used=best_result.samples_used,
            winning_outliers_removed=best_result.outliers_removed,
            winning_model=winning_model,
            ranking_metric=_ranking_metric_name(target_type),
            ranking_value=winning_value,
            all_candidates=roster,
            skipped_candidates=tuple(skipped),
            candidate_scores=tuple(scored),
        )

    async def select_and_register_challenger(
        self,
        market_id: MarketId,
        dataset: Dataset,
        target_type: TargetType,
        model_key_prefix: str,
        next_version: int,
        now: datetime,
        candidates: tuple[CandidateSpec, ...] | None = None,
        # Milestone 4 Rule 14: TRAIN_TEST (random shuffle) is non-compliant as the production
        # default for time-dependent sports data — TIME_SERIES_SPLIT respects sample order
        # instead. Explicitly passing `split_strategy=SplitStrategy.TRAIN_TEST` remains possible
        # for any caller (e.g. an existing test) that has a specific reason to.
        split_strategy: SplitStrategy = SplitStrategy.TIME_SERIES_SPLIT,
        **split_kwargs,
    ) -> tuple[ModelDefinition, ModelSelectionResult]:
        """Runs `select()`, registers the winner as CANDIDATE, immediately promotes it to
        CHALLENGER (offline benchmark already just ran), and records the full benchmark as an
        `Experiment` (Milestone 9's "no market's production model changes without one of these
        existing first" rule) — promotion to CHAMPION remains a separate, human-gated call to
        `model_registry.promote_to_champion()`.

        The winning model's fitted weights are serialized and saved via `artifact_store` before
        registration, so `artifact_ref` is always real for a model this method produces — the
        gap that previously left `TrainedModelPredictor`/`ModelLoaderService` with nothing to
        load even after a human promoted a Challenger to Champion."""
        selection = await self.select(dataset, target_type, candidates=candidates, split_strategy=split_strategy, **split_kwargs)

        model_key = f"{model_key_prefix}.{selection.winning_candidate.algorithm.value}"
        artifact_ref = await self.artifact_store.save(
            f"{model_key}/v{next_version}.bin", selection.winning_model.serialize()
        )

        feature_versions = await self._resolve_feature_versions(dataset.lineage.feature_keys)

        # Training Run audit trail: the id is minted before registration so it can be handed to
        # `model_registry.register` as `training_run_ref` — `register()` already accepts this
        # opaque string, it just never had a real row backing it until this service was wired
        # with a `training_runs` repository.
        run_id = TrainingRunId(uuid4()) if self.training_runs is not None else None

        model_def = await self.model_registry.register(
            market_id=market_id,
            model_key=model_key,
            version=next_version,
            algorithm=selection.winning_candidate.algorithm.value,
            framework=selection.winning_candidate.framework.value,
            dataset_version=dataset.version,
            feature_versions=feature_versions,
            trained_at=now,
            now=now,
            artifact_ref=artifact_ref,
            training_run_ref=str(run_id.value) if run_id is not None else None,
        )
        challenger = await self.model_registry.promote_to_challenger(model_def.id)

        await self.experiments.record_model_selection(market_id, selection, now)

        if self.training_runs is not None and run_id is not None:
            # `started_at`/`completed_at` both reuse `now` — the caller's registration timestamp,
            # not measured wall-clock training duration (`TrainingPipelineService.train()` does
            # not instrument that today, and this method never fabricates a value it didn't
            # measure).
            run = TrainingRun(
                id=run_id,
                market_id=market_id,
                model_id=challenger.id,
                dataset_id=dataset.id,
                algorithm=selection.winning_candidate.algorithm.value,
                framework=selection.winning_candidate.framework.value,
                train_metrics=(
                    {
                        "sample_count": selection.winning_train_metrics.sample_count,
                        "metric_name": selection.winning_train_metrics.metric_name,
                        "metric_value": selection.winning_train_metrics.metric_value,
                        **selection.winning_train_metrics.extra,
                    }
                    if selection.winning_train_metrics is not None
                    else {}
                ),
                test_metrics=selection.winning_test_metrics,
                feature_order=selection.winning_feature_order,
                selected_features=selection.winning_selected_features,
                samples_used=selection.winning_samples_used,
                outliers_removed=selection.winning_outliers_removed,
                started_at=now,
                completed_at=now,
            )
            await self.training_runs.record(run)

        return challenger, selection

    async def _resolve_feature_versions(self, feature_keys: tuple[str, ...]) -> dict:
        """Real `feature_key -> FeatureDefinition.version` provenance, not fabricated. Returns
        `{}` (the previous, silently-wrong behavior's actual output shape) only when this
        service wasn't wired with a `feature_definitions` port — never guesses a version for a
        key it can't look up."""
        if self.feature_definitions is None:
            return {}
        versions: dict[str, int] = {}
        for key in feature_keys:
            definition = await self.feature_definitions.get(FeatureKey(key))
            if definition is not None:
                versions[key] = definition.version
        return versions
