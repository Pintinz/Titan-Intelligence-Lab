"""Training Platform orchestrator (Milestone 9.1). Wires together, in order: dataset loading
(an already-built `Dataset`, not a fresh Feature Store read — "auto dataset loading" means
"don't make the caller manually assemble samples," not "bypass the Dataset Platform"), missing-
value imputation, outlier detection/removal, optional feature selection, `DatasetSplitter`, a
`PredictionModelPort.fit()` call (with early stopping wired through automatically when the split
produced a validation set), and evaluation on the held-out split.

GPU readiness (Milestone 9.1 "GPU-ready" requirement): every framework adapter's ``params`` dict
passes straight through to the underlying estimator constructor — `lightgbm.LGBMClassifier(device="gpu")`,
`xgboost.XGBClassifier(tree_method="gpu_hist")`, `catboost.CatBoostClassifier(task_type="GPU")` all
work today via that passthrough. No separate "GPU code path" exists to fabricate; this is the
honest, minimal-but-real form the requirement takes until a dedicated GPU worker pool exists.

Parallel training ("train N algorithms for a market concurrently") is `asyncio.gather` over
multiple `train()` calls at the call site (Automatic Model Selection, Milestone 9.1 task #164) —
nothing here is single-threaded-only, but this service itself trains exactly one model per call,
consistent with `PredictionModelPort.fit()` being a per-model contract.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from modules.predictions.application.dataset_registry_service import DatasetRegistryService
from modules.predictions.application.dataset_splitter import split
from modules.predictions.application.preprocessing import detect_outliers, impute_missing, select_features
from modules.predictions.domain.dataset import Dataset, SplitStrategy
from modules.predictions.domain.probability_metrics import log_loss
from modules.predictions.domain.value_objects import MarketId, TargetType
from modules.predictions.ports.ml_model import PredictionModelPort, TrainingMetrics, TrainingSample


class DatasetNotTrainableError(ValueError):
    pass


@dataclass(frozen=True)
class EvaluationMetrics:
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    mae: float | None = None
    rmse: float | None = None
    # Continuous Outcome Learning Engine (2026-08-08): the probability the fitted model assigned
    # to whichever class actually happened, averaged over the held-out test split — classification
    # only (None for regression, where there's no probability to score). This is what
    # `AutomaticModelSelectionService` now ranks candidates by (spec §8's priority order), and what
    # `ChallengerEvaluationService` scores a Challenger against its market's current Champion with.
    log_loss: float | None = None


@dataclass(frozen=True)
class TrainingRunResult:
    model: PredictionModelPort
    train_metrics: TrainingMetrics
    test_metrics: EvaluationMetrics
    feature_order: tuple[str, ...]
    selected_features: tuple[str, ...]
    samples_used: int
    outliers_removed: int


def _evaluate_classification(model: PredictionModelPort, test_samples: list[TrainingSample]) -> EvaluationMetrics:
    tp = fp = tn = fn = 0
    true_class_probabilities = []
    for sample in test_samples:
        probability = model.predict_one(sample.features).probability
        predicted_positive = probability >= 0.5
        actual_positive = sample.label >= 0.5
        true_class_probabilities.append(probability if actual_positive else 1.0 - probability)
        if predicted_positive and actual_positive:
            tp += 1
        elif predicted_positive and not actual_positive:
            fp += 1
        elif not predicted_positive and actual_positive:
            fn += 1
        else:
            tn += 1

    n = tp + fp + tn + fn
    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return EvaluationMetrics(
        accuracy=accuracy, precision=precision, recall=recall, f1=f1, log_loss=log_loss(true_class_probabilities)
    )


def _evaluate_multiclass(model: PredictionModelPort, test_samples: list[TrainingSample]) -> EvaluationMetrics:
    """Multiclass classification support (2026-08-06): `_evaluate_classification`'s tp/fp/tn/fn
    framing assumes exactly two classes (`label >= 0.5` as "positive") — meaningless once
    ``label`` is a class *index* (e.g. 0.0..36.0 for football.correct_score). Accuracy is instead
    real-label equality: decode both the model's predicted label and the sample's own true index
    through the same `model.class_labels` ordering both were encoded with, and compare directly.
    Precision/recall/f1 stay `None` here rather than fabricating a micro/macro-average nobody
    asked for. `log_loss` reads the probability the model's own `distribution` assigned to
    whichever class actually happened (2026-08-08) — every adapter populates `distribution` for a
    multiclass model, so this is real per-class probability, not a derived approximation."""
    n = len(test_samples)
    correct = 0
    true_class_probabilities = []
    for sample in test_samples:
        prediction = model.predict_one(sample.features)
        true_label = model.class_labels[int(sample.label)]
        if prediction.value == true_label:
            correct += 1
        true_class_probabilities.append(prediction.distribution.get(true_label, 0.0))
    return EvaluationMetrics(accuracy=correct / n if n else 0.0, log_loss=log_loss(true_class_probabilities))


def _evaluate_regression(model: PredictionModelPort, test_samples: list[TrainingSample]) -> EvaluationMetrics:
    errors = [model.predict_one(sample.features).raw_score - sample.label for sample in test_samples]
    if not errors:
        return EvaluationMetrics(mae=0.0, rmse=0.0)
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = (sum(e**2 for e in errors) / len(errors)) ** 0.5
    return EvaluationMetrics(mae=mae, rmse=rmse)


@dataclass
class TrainingPipelineService:
    async def train(
        self,
        model: PredictionModelPort,
        dataset: Dataset,
        split_strategy: SplitStrategy = SplitStrategy.TRAIN_TEST,
        impute_strategy: str = "zero",
        outlier_z_threshold: float | None = 3.0,
        feature_selection_top_k: int | None = None,
        feature_selection_method: str = "correlation",
        use_early_stopping: bool = True,
        on_checkpoint: Callable[[PredictionModelPort, TrainingMetrics], None] | None = None,
        **split_kwargs,
    ) -> TrainingRunResult:
        if not dataset.is_usable_for_training():
            raise DatasetNotTrainableError(
                f"dataset v{dataset.version} for market {dataset.market_id} is not APPROVED/usable for training "
                f"(status={dataset.status.value}, quality_issues={[i.value for i in dataset.quality_issues]})"
            )

        feature_order = list(dataset.lineage.feature_keys)
        samples = impute_missing(dataset.samples, feature_order, strategy=impute_strategy)

        outliers_removed = 0
        if outlier_z_threshold is not None:
            flagged = set(detect_outliers(samples, feature_order, z_threshold=outlier_z_threshold))
            if flagged:
                samples = [sample for i, sample in enumerate(samples) if i not in flagged]
                outliers_removed = len(flagged)

        selected_features = feature_order
        if feature_selection_top_k is not None:
            selected_features = select_features(
                samples, feature_order, feature_selection_top_k, method=feature_selection_method
            )
            samples = [
                TrainingSample(
                    features={key: s.features[key] for key in selected_features if key in s.features},
                    label=s.label,
                    reference_time=s.reference_time,  # Milestone 18: must survive for split() below
                )
                for s in samples
            ]

        split_result = split(samples, split_strategy, **split_kwargs)
        if split_result.folds:
            # Milestone 4 fix: ROLLING_WINDOW/WALK_FORWARD/TIME_SERIES_SPLIT report their real
            # per-round splits only in `.folds` — `.train` on a fold-based `DatasetSplit` is the
            # *entire* dataset (see `dataset_splitter.py`'s `_rolling_window`/`_walk_forward`/
            # `_time_series_split`, all `train=tuple(samples)`), meant for a caller that wants to
            # do a final fit after using folds for evaluation, not as this method's fit set —
            # fitting on it directly would train on data chronologically after the eval window.
            # Previously unhandled entirely: `test_samples` fell through to empty (`.test`/
            # `.validation` are never populated for these three strategies), so every fold-based
            # split silently produced "no evaluable test metric" for every candidate — caught by
            # `test_scheduled_retraining_orchestrator.py`/`test_model_selection_service.py`
            # failing once TIME_SERIES_SPLIT became `AutomaticModelSelectionService`'s default
            # (Rule 14). Use the last (most recent) fold: train on everything chronologically
            # before it, evaluate on it — the standard walk-forward "final validation" shape.
            train_samples, test_fold = split_result.folds[-1]
            train_samples = list(train_samples)
            test_samples = list(test_fold)
        else:
            train_samples = list(split_result.train)
            test_samples = list(split_result.test) or list(split_result.validation)
        validation_samples = list(split_result.validation) if use_early_stopping and split_result.validation else None

        train_metrics = await model.fit(train_samples, validation_samples=validation_samples)

        if on_checkpoint is not None:
            on_checkpoint(model, train_metrics)

        if test_samples:
            if model.target_type is not TargetType.CLASSIFICATION:
                test_metrics = _evaluate_regression(model, test_samples)
            elif model.class_labels:
                test_metrics = _evaluate_multiclass(model, test_samples)
            else:
                test_metrics = _evaluate_classification(model, test_samples)
        else:
            test_metrics = EvaluationMetrics()

        return TrainingRunResult(
            model=model,
            train_metrics=train_metrics,
            test_metrics=test_metrics,
            feature_order=tuple(feature_order),
            selected_features=tuple(selected_features),
            samples_used=len(samples),
            outliers_removed=outliers_removed,
        )


@dataclass
class RetrainingScheduler:
    """Training scheduler (Milestone 9.1) — decides *whether* a market needs retraining
    (drifted dataset, or a dataset older than ``max_dataset_age``). Actually *invoking* retraining
    on a schedule is Celery periodic-task wiring (reusing Milestone 5's scheduler infrastructure)
    at the composition layer, added alongside the Retraining API (task #170) — this class is the
    decision logic that task's endpoint/task calls, kept independently testable here."""

    dataset_registry: DatasetRegistryService
    max_dataset_age: timedelta = timedelta(days=7)

    async def should_retrain(self, market_id: MarketId, now: datetime) -> dict:
        latest = await self.dataset_registry.datasets.get_latest_version(market_id)
        if latest is None:
            return {"should_retrain": False, "reason": "no dataset built yet"}

        drift = await self.dataset_registry.detect_drift(market_id)
        age = now - latest.created_at if latest.created_at else None
        is_stale = age is not None and age > self.max_dataset_age

        return {
            "should_retrain": bool(drift.get("drift_detected")) or is_stale,
            "drift": drift,
            "dataset_age_days": age.days if age is not None else None,
            "is_stale": is_stale,
        }
