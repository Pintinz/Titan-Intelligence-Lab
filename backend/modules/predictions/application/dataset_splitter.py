"""Dataset Splitter — the 6 named split strategies from the Milestone 9.1 Dataset Platform spec
("Train/Val/Test/Holdout/Rolling-Window/Walk-Forward datasets"). Pure functions over a sequence of
`TrainingSample`s: `TRAIN_TEST`/`TRAIN_VAL_TEST` shuffle (seeded, for reproducibility — the Dataset
Platform's own "Reproducibility" requirement), order-independent by design.

`HOLDOUT`/`ROLLING_WINDOW`/`WALK_FORWARD`/`TIME_SERIES_SPLIT` exist specifically to respect
chronological order, so they never trust caller-supplied order (Milestone 18 fix — see
docs/milestone18_verification_report.md): each sorts its input ascending by
`TrainingSample.reference_time` before slicing, and fails closed (`MissingTemporalReferenceError`)
if any sample lacks that field, rather than silently falling back to positional/input order. This
replaces the pre-Milestone-18 contract, which merely documented "callers are expected to pass
samples in ascending chronological order" without enforcing or even checking it — the exact gap
Milestone 17 found `DatasetBuilder`/`PredictionOutcomeRepositoryPort` silently violating (samples
arrived in `evaluated_at DESC` order, the opposite of what every one of these four strategies
assumed).
"""

from __future__ import annotations

import random

from modules.predictions.domain.dataset import DatasetSplit, SplitStrategy
from modules.predictions.ports.ml_model import TrainingSample

_TEMPORAL_STRATEGIES = frozenset(
    {SplitStrategy.HOLDOUT, SplitStrategy.ROLLING_WINDOW, SplitStrategy.WALK_FORWARD, SplitStrategy.TIME_SERIES_SPLIT}
)


class InsufficientSamplesForSplitError(ValueError):
    pass


class MissingTemporalReferenceError(ValueError):
    """Raised when a temporal (order-sensitive) split strategy is requested but one or more
    samples has no `reference_time`. Fails closed rather than falling back to whatever positional
    order the caller happened to pass — a caller-supplied order is never trusted as chronological,
    which is exactly the assumption that produced the Milestone 17 defect."""


def _chronological(samples: list[TrainingSample]) -> list[TrainingSample]:
    missing = sum(1 for s in samples if s.reference_time is None)
    if missing:
        raise MissingTemporalReferenceError(
            f"{missing} of {len(samples)} samples have no reference_time — a temporal split "
            "strategy cannot establish chronological order without it."
        )
    # Stable sort: samples sharing an identical reference_time keep their relative input order —
    # deterministic given a deterministic input list, and does not manufacture leakage across a
    # fold boundary any more than an arbitrary tie-break would (Milestone 18 §8).
    return sorted(samples, key=lambda s: s.reference_time)


def split(samples: list[TrainingSample], strategy: SplitStrategy, **kwargs) -> DatasetSplit:
    if len(samples) < 2:
        raise InsufficientSamplesForSplitError(f"need >= 2 samples to split, got {len(samples)}")

    if strategy is SplitStrategy.TRAIN_TEST:
        return _train_test(samples, kwargs.get("test_ratio", 0.2), kwargs.get("seed", 42))
    if strategy is SplitStrategy.TRAIN_VAL_TEST:
        return _train_val_test(
            samples, kwargs.get("val_ratio", 0.15), kwargs.get("test_ratio", 0.15), kwargs.get("seed", 42)
        )

    if strategy in _TEMPORAL_STRATEGIES:
        samples = _chronological(samples)

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


def _assert_chronological(train: tuple[TrainingSample, ...], test: tuple[TrainingSample, ...]) -> None:
    """The required temporal invariant (Milestone 18 §4): max(train.reference_time) <=
    min(test.reference_time). Holds by construction given `_chronological`'s sort plus contiguous
    slicing below — this is a fail-closed correctness proof, not a workaround; it is never expected
    to fire, and is never weakened to tolerate messy data."""
    if train and test:
        assert train[-1].reference_time <= test[0].reference_time, (
            "temporal split invariant violated: a training observation occurred after a "
            "validation/test observation"
        )


def _holdout(samples: list[TrainingSample], holdout_ratio: float) -> DatasetSplit:
    cut = max(1, int(len(samples) * (1 - holdout_ratio)))
    train, test = tuple(samples[:cut]), tuple(samples[cut:])
    _assert_chronological(train, test)
    return DatasetSplit(strategy=SplitStrategy.HOLDOUT, train=train, test=test)


def _rolling_window(samples: list[TrainingSample], window_size: int, test_size: int) -> DatasetSplit:
    folds = []
    i = 0
    while i + window_size + test_size <= len(samples):
        train_fold = tuple(samples[i : i + window_size])
        test_fold = tuple(samples[i + window_size : i + window_size + test_size])
        _assert_chronological(train_fold, test_fold)
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
        _assert_chronological(train_fold, test_fold)
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
        _assert_chronological(train_fold, test_fold)
        folds.append((train_fold, test_fold))
    return DatasetSplit(strategy=SplitStrategy.TIME_SERIES_SPLIT, train=tuple(samples), folds=tuple(folds))
