"""Dataset Splitter — the 6 named split strategies from the Milestone 9.1 Dataset Platform spec
("Train/Val/Test/Holdout/Rolling-Window/Walk-Forward datasets"). Pure functions over an ordered
sequence of `TrainingSample`s: `TRAIN_TEST`/`TRAIN_VAL_TEST` shuffle (seeded, for reproducibility —
the Dataset Platform's own "Reproducibility" requirement); `HOLDOUT`/`ROLLING_WINDOW`/
`WALK_FORWARD`/`TIME_SERIES_SPLIT` deliberately do not, because they exist specifically to respect
chronological order — callers are expected to pass samples in ascending chronological order for
those four (`DatasetBuilder` preserves whatever order its `PredictionOutcomeRepositoryPort` query
returned; if that isn't chronological for a given repository implementation, that's a caller-side
ordering concern, not this module's).
"""

from __future__ import annotations

import random

from modules.predictions.domain.dataset import DatasetSplit, SplitStrategy
from modules.predictions.ports.ml_model import TrainingSample


class InsufficientSamplesForSplitError(ValueError):
    pass


def split(samples: list[TrainingSample], strategy: SplitStrategy, **kwargs) -> DatasetSplit:
    if len(samples) < 2:
        raise InsufficientSamplesForSplitError(f"need >= 2 samples to split, got {len(samples)}")

    if strategy is SplitStrategy.TRAIN_TEST:
        return _train_test(samples, kwargs.get("test_ratio", 0.2), kwargs.get("seed", 42))
    if strategy is SplitStrategy.TRAIN_VAL_TEST:
        return _train_val_test(
            samples, kwargs.get("val_ratio", 0.15), kwargs.get("test_ratio", 0.15), kwargs.get("seed", 42)
        )
    if strategy is SplitStrategy.HOLDOUT:
        return _holdout(samples, kwargs.get("holdout_ratio", 0.2))
    if strategy is SplitStrategy.ROLLING_WINDOW:
        return _rolling_window(samples, kwargs.get("window_size", max(2, len(samples) // 4)), kwargs.get("test_size", 1))
    if strategy is SplitStrategy.WALK_FORWARD:
        return _walk_forward(samples, kwargs.get("min_train_size", max(2, len(samples) // 4)), kwargs.get("step", 1))
    if strategy is SplitStrategy.TIME_SERIES_SPLIT:
        return _time_series_split(samples, kwargs.get("n_splits", 5))
    raise ValueError(f"unsupported split strategy '{strategy}'")


def _train_test(samples: list[TrainingSample], test_ratio: float, seed: int) -> DatasetSplit:
    indices = list(range(len(samples)))
    random.Random(seed).shuffle(indices)
    cut = max(1, int(len(samples) * (1 - test_ratio)))
    train = tuple(samples[i] for i in indices[:cut])
    test = tuple(samples[i] for i in indices[cut:])
    return DatasetSplit(strategy=SplitStrategy.TRAIN_TEST, train=train, test=test)


def _train_val_test(samples: list[TrainingSample], val_ratio: float, test_ratio: float, seed: int) -> DatasetSplit:
    indices = list(range(len(samples)))
    random.Random(seed).shuffle(indices)
    n = len(samples)
    test_cut = max(1, int(n * (1 - test_ratio)))
    val_cut = max(1, int(test_cut * (1 - val_ratio)))
    train = tuple(samples[i] for i in indices[:val_cut])
    validation = tuple(samples[i] for i in indices[val_cut:test_cut])
    test = tuple(samples[i] for i in indices[test_cut:])
    return DatasetSplit(strategy=SplitStrategy.TRAIN_VAL_TEST, train=train, validation=validation, test=test)


def _holdout(samples: list[TrainingSample], holdout_ratio: float) -> DatasetSplit:
    cut = max(1, int(len(samples) * (1 - holdout_ratio)))
    return DatasetSplit(strategy=SplitStrategy.HOLDOUT, train=tuple(samples[:cut]), test=tuple(samples[cut:]))


def _rolling_window(samples: list[TrainingSample], window_size: int, test_size: int) -> DatasetSplit:
    folds = []
    i = 0
    while i + window_size + test_size <= len(samples):
        train_fold = tuple(samples[i : i + window_size])
        test_fold = tuple(samples[i + window_size : i + window_size + test_size])
        folds.append((train_fold, test_fold))
        i += test_size
    if not folds:
        raise InsufficientSamplesForSplitError(
            f"not enough samples for a rolling window of size {window_size} + test_size {test_size}"
        )
    return DatasetSplit(strategy=SplitStrategy.ROLLING_WINDOW, train=tuple(samples), folds=tuple(folds))


def _walk_forward(samples: list[TrainingSample], min_train_size: int, step: int) -> DatasetSplit:
    folds = []
    size = min_train_size
    while size + step <= len(samples):
        train_fold = tuple(samples[:size])
        test_fold = tuple(samples[size : size + step])
        folds.append((train_fold, test_fold))
        size += step
    if not folds:
        raise InsufficientSamplesForSplitError(
            f"not enough samples for walk-forward with min_train_size={min_train_size}, step={step}"
        )
    return DatasetSplit(strategy=SplitStrategy.WALK_FORWARD, train=tuple(samples), folds=tuple(folds))


def _time_series_split(samples: list[TrainingSample], n_splits: int) -> DatasetSplit:
    n = len(samples)
    fold_size = n // (n_splits + 1)
    if fold_size < 1:
        raise InsufficientSamplesForSplitError(f"not enough samples for {n_splits} time-series splits")
    folds = []
    for i in range(1, n_splits + 1):
        train_fold = tuple(samples[: fold_size * i])
        test_fold = tuple(samples[fold_size * i : fold_size * (i + 1)])
        if not test_fold:
            break
        folds.append((train_fold, test_fold))
    return DatasetSplit(strategy=SplitStrategy.TIME_SERIES_SPLIT, train=tuple(samples), folds=tuple(folds))
