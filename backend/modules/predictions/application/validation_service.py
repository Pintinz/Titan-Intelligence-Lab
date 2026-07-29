"""Cross-Validation orchestrator — the 9 Validation Strategies (Milestone 9.1). `cross_validate()`
builds folds per `ValidationStrategy`, fits ``model_factory``'s model on each fold's training
split, and evaluates on that fold's test split, returning per-fold + aggregate metrics.

``model_factory`` is called with the fold's training samples and returns a `PredictionModelPort`:
for the 8 non-nested strategies it's expected to return a *fresh, unfitted* model which this
function then calls `.fit()` on; for `NESTED_CV`, pass ``caller_fits_model=True`` and have
``model_factory`` itself run an inner hyperparameter search (Automatic Model Selection, task #164)
against the outer fold's training samples and return an *already-fitted* model — that's what makes
the CV "nested": the inner search only ever sees that outer fold's own training data, never the
outer test fold.
"""

from __future__ import annotations

import random
import statistics as pystats
from collections.abc import Callable

from modules.predictions.application.dataset_splitter import split as dataset_split
from modules.predictions.domain.dataset import SplitStrategy
from modules.predictions.domain.validation import CrossValidationResult, FoldResult, ValidationStrategy
from modules.predictions.domain.value_objects import TargetType
from modules.predictions.ports.ml_model import PredictionModelPort, TrainingSample


class InsufficientSamplesForValidationError(ValueError):
    pass


def _metric_for(model: PredictionModelPort, test_samples: list[TrainingSample]) -> tuple[str, float]:
    if model.target_type is TargetType.CLASSIFICATION:
        correct = sum(
            1 for s in test_samples if (model.predict_one(s.features).probability >= 0.5) == (s.label >= 0.5)
        )
        return "accuracy", correct / len(test_samples)
    errors = [abs(model.predict_one(s.features).raw_score - s.label) for s in test_samples]
    return "mae", sum(errors) / len(errors)


def _k_fold_indices(n: int, k: int, seed: int = 42) -> list[list[int]]:
    indices = list(range(n))
    random.Random(seed).shuffle(indices)
    folds: list[list[int]] = [[] for _ in range(k)]
    for i, idx in enumerate(indices):
        folds[i % k].append(idx)
    return folds


def _stratified_k_fold_indices(samples: list[TrainingSample], k: int, seed: int = 42) -> list[list[int]]:
    by_label: dict[float, list[int]] = {}
    for i, sample in enumerate(samples):
        by_label.setdefault(sample.label, []).append(i)

    folds: list[list[int]] = [[] for _ in range(k)]
    for label_indices in by_label.values():
        shuffled = list(label_indices)
        random.Random(seed).shuffle(shuffled)
        for i, idx in enumerate(shuffled):
            folds[i % k].append(idx)
    return folds


def _folds_from_indices(samples: list[TrainingSample], fold_indices: list[list[int]]) -> list[tuple[list, list]]:
    pairs = []
    for fold in fold_indices:
        test_set = set(fold)
        test_samples = [samples[i] for i in fold]
        train_samples = [s for i, s in enumerate(samples) if i not in test_set]
        pairs.append((train_samples, test_samples))
    return pairs


def _build_folds(samples: list[TrainingSample], strategy: ValidationStrategy, **kwargs) -> list[tuple[list, list]]:
    n = len(samples)

    if strategy is ValidationStrategy.HOLDOUT:
        result = dataset_split(samples, SplitStrategy.HOLDOUT, holdout_ratio=kwargs.get("holdout_ratio", 0.2))
        return [(list(result.train), list(result.test))]

    if strategy is ValidationStrategy.K_FOLD:
        fold_indices = _k_fold_indices(n, kwargs.get("k", 5), seed=kwargs.get("seed", 42))
        return _folds_from_indices(samples, fold_indices)

    if strategy is ValidationStrategy.STRATIFIED_K_FOLD:
        fold_indices = _stratified_k_fold_indices(samples, kwargs.get("k", 5), seed=kwargs.get("seed", 42))
        return _folds_from_indices(samples, fold_indices)

    if strategy in (ValidationStrategy.REPEATED_K_FOLD, ValidationStrategy.NESTED_CV):
        k = kwargs.get("k", kwargs.get("outer_k", 5))
        n_repeats = kwargs.get("n_repeats", 2) if strategy is ValidationStrategy.REPEATED_K_FOLD else 1
        pairs = []
        for repeat in range(n_repeats):
            fold_indices = _k_fold_indices(n, k, seed=kwargs.get("seed", 42) + repeat)
            pairs.extend(_folds_from_indices(samples, fold_indices))
        return pairs

    if strategy is ValidationStrategy.LEAVE_ONE_OUT:
        return [([s for j, s in enumerate(samples) if j != i], [samples[i]]) for i in range(n)]

    if strategy is ValidationStrategy.TIME_SERIES_SPLIT:
        result = dataset_split(samples, SplitStrategy.TIME_SERIES_SPLIT, n_splits=kwargs.get("n_splits", 5))
        return [(list(train), list(test)) for train, test in result.folds]

    if strategy is ValidationStrategy.ROLLING_WINDOW:
        result = dataset_split(
            samples,
            SplitStrategy.ROLLING_WINDOW,
            window_size=kwargs.get("window_size", max(2, n // 4)),
            test_size=kwargs.get("test_size", 1),
        )
        return [(list(train), list(test)) for train, test in result.folds]

    if strategy is ValidationStrategy.WALK_FORWARD:
        result = dataset_split(
            samples,
            SplitStrategy.WALK_FORWARD,
            min_train_size=kwargs.get("min_train_size", max(2, n // 4)),
            step=kwargs.get("step", 1),
        )
        return [(list(train), list(test)) for train, test in result.folds]

    raise ValueError(f"unsupported validation strategy '{strategy}'")


async def cross_validate(
    model_factory: Callable[[list[TrainingSample]], PredictionModelPort],
    samples: list[TrainingSample],
    strategy: ValidationStrategy,
    caller_fits_model: bool = False,
    **kwargs,
) -> CrossValidationResult:
    if len(samples) < 2:
        raise InsufficientSamplesForValidationError(f"need >= 2 samples to validate, got {len(samples)}")

    fold_pairs = _build_folds(samples, strategy, **kwargs)

    fold_results = []
    for i, (train_samples, test_samples) in enumerate(fold_pairs):
        if not train_samples or not test_samples:
            continue

        if caller_fits_model:
            model = await model_factory(train_samples)
        else:
            model = model_factory(train_samples)
            await model.fit(train_samples)

        metric_name, metric_value = _metric_for(model, test_samples)
        fold_results.append(
            FoldResult(fold_index=i, metric_name=metric_name, metric_value=metric_value, sample_count=len(test_samples))
        )

    if not fold_results:
        raise InsufficientSamplesForValidationError(
            f"strategy '{strategy.value}' produced no usable folds for {len(samples)} samples"
        )

    values = [f.metric_value for f in fold_results]
    mean_metric = pystats.fmean(values)
    std_metric = pystats.pstdev(values) if len(values) > 1 else 0.0

    return CrossValidationResult(
        strategy=strategy, fold_results=tuple(fold_results), mean_metric=mean_metric, std_metric=std_metric
    )
