"""Automatic Model Selection (Milestone 9.1): trains every candidate in a configurable roster
against the same approved `Dataset` via the EXISTING `TrainingPipelineService` (Milestone 9.1 task
#161), ranks candidates by their held-out test metric, and registers the winner as a CANDIDATE ->
CHALLENGER through the EXISTING `ModelRegistryService` (Milestone 9, extended additively in task
#163) — human approval to CHAMPION still goes through that service's own `promote_to_champion`,
untouched here. "Never hardcode algorithm selection" (Milestone 9.1 spec) is satisfied by ranking
real benchmark numbers, not by this service ever picking one algorithm by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.predictions.application.experiment_tracking_service import ExperimentTrackingService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.training_pipeline_service import TrainingPipelineService
from modules.predictions.domain.dataset import Dataset, SplitStrategy
from modules.predictions.domain.entities import ModelDefinition
from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.model_selection import CandidateSpec, ModelSelectionResult, NoViableCandidateError
from modules.predictions.domain.value_objects import MarketId, TargetType
from modules.predictions.infrastructure.ml.catboost_adapter import CatBoostAdapter
from modules.predictions.infrastructure.ml.lightgbm_adapter import LightGBMAdapter
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.infrastructure.ml.xgboost_adapter import XGBoostAdapter
from modules.predictions.ports.ml_model import (
    InsufficientTrainingDataError,
    PredictionModelPort,
    UnsupportedAlgorithmForTargetTypeError,
)

DEFAULT_CLASSIFICATION_CANDIDATES: tuple[CandidateSpec, ...] = (
    CandidateSpec(MLAlgorithm.LIGHTGBM_GBM, MLFramework.LIGHTGBM),
    CandidateSpec(MLAlgorithm.XGBOOST_GBM, MLFramework.XGBOOST),
    CandidateSpec(MLAlgorithm.CATBOOST_GBM, MLFramework.CATBOOST),
    CandidateSpec(MLAlgorithm.RANDOM_FOREST, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.EXTRA_TREES, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.LOGISTIC_REGRESSION, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.RIDGE, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.ELASTIC_NET, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.SVM, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.GAUSSIAN_NB, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.MLP, MLFramework.SKLEARN),
)

DEFAULT_REGRESSION_CANDIDATES: tuple[CandidateSpec, ...] = tuple(
    candidate
    for candidate in DEFAULT_CLASSIFICATION_CANDIDATES
    if candidate.algorithm not in (MLAlgorithm.LOGISTIC_REGRESSION, MLAlgorithm.GAUSSIAN_NB)
)


def _build_model(candidate: CandidateSpec, target_type: TargetType) -> PredictionModelPort:
    if candidate.framework is MLFramework.LIGHTGBM:
        return LightGBMAdapter(target_type=target_type, params=dict(candidate.params))
    if candidate.framework is MLFramework.XGBOOST:
        return XGBoostAdapter(target_type=target_type, params=dict(candidate.params))
    if candidate.framework is MLFramework.CATBOOST:
        return CatBoostAdapter(target_type=target_type, params=dict(candidate.params))
    return SklearnAdapter(algorithm=candidate.algorithm, target_type=target_type, params=dict(candidate.params))


def _ranking_metric_name(target_type: TargetType) -> str:
    return "accuracy" if target_type is TargetType.CLASSIFICATION else "mae"


def _ranking_value(target_type: TargetType, test_metrics) -> float | None:
    if target_type is TargetType.CLASSIFICATION:
        return test_metrics.accuracy
    return test_metrics.mae


def _is_better(target_type: TargetType, candidate_value: float, current_best: float) -> bool:
    if target_type is TargetType.CLASSIFICATION:
        return candidate_value > current_best  # higher accuracy wins
    return candidate_value < current_best  # lower MAE wins


@dataclass
class AutomaticModelSelectionService:
    training_pipeline: TrainingPipelineService
    model_registry: ModelRegistryService
    experiments: ExperimentTrackingService

    async def select(
        self,
        dataset: Dataset,
        target_type: TargetType,
        candidates: tuple[CandidateSpec, ...] | None = None,
        split_strategy: SplitStrategy = SplitStrategy.TRAIN_TEST,
        **split_kwargs,
    ) -> ModelSelectionResult:
        roster = candidates or (
            DEFAULT_CLASSIFICATION_CANDIDATES if target_type is TargetType.CLASSIFICATION else DEFAULT_REGRESSION_CANDIDATES
        )

        best: tuple[CandidateSpec, float, PredictionModelPort] | None = None
        skipped: list[tuple[CandidateSpec, str]] = []

        for candidate in roster:
            model = _build_model(candidate, target_type)
            try:
                result = await self.training_pipeline.train(model, dataset, split_strategy=split_strategy, **split_kwargs)
            except (InsufficientTrainingDataError, UnsupportedAlgorithmForTargetTypeError) as exc:
                skipped.append((candidate, str(exc)))
                continue

            value = _ranking_value(target_type, result.test_metrics)
            if value is None:
                skipped.append((candidate, "training produced no evaluable test metric"))
                continue

            if best is None or _is_better(target_type, value, best[1]):
                best = (candidate, value, result.model)

        if best is None:
            raise NoViableCandidateError(
                f"no candidate in the roster of {len(roster)} could be trained on dataset "
                f"v{dataset.version} for market {dataset.market_id} — skipped: {[(c.algorithm.value, r) for c, r in skipped]}"
            )

        winning_candidate, winning_value, winning_model = best
        return ModelSelectionResult(
            winning_candidate=winning_candidate,
            winning_model=winning_model,
            ranking_metric=_ranking_metric_name(target_type),
            ranking_value=winning_value,
            all_candidates=roster,
            skipped_candidates=tuple(skipped),
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
        split_strategy: SplitStrategy = SplitStrategy.TRAIN_TEST,
        **split_kwargs,
    ) -> tuple[ModelDefinition, ModelSelectionResult]:
        """Runs `select()`, registers the winner as CANDIDATE, immediately promotes it to
        CHALLENGER (offline benchmark already just ran), and records the full benchmark as an
        `Experiment` (Milestone 9's "no market's production model changes without one of these
        existing first" rule) — promotion to CHAMPION remains a separate, human-gated call to
        `model_registry.promote_to_champion()`."""
        selection = await self.select(dataset, target_type, candidates=candidates, split_strategy=split_strategy, **split_kwargs)

        model_def = await self.model_registry.register(
            market_id=market_id,
            model_key=f"{model_key_prefix}.{selection.winning_candidate.algorithm.value}",
            version=next_version,
            algorithm=selection.winning_candidate.algorithm.value,
            framework=selection.winning_candidate.framework.value,
            dataset_version=dataset.version,
            trained_at=now,
            now=now,
        )
        challenger = await self.model_registry.promote_to_challenger(model_def.id)

        await self.experiments.record_model_selection(market_id, selection, now)

        return challenger, selection
