from __future__ import annotations

import pytest

from modules.predictions.application.dataset_splitter import InsufficientSamplesForSplitError, split
from modules.predictions.domain.dataset import SplitStrategy
from modules.predictions.ports.ml_model import TrainingSample


def _samples(n: int) -> list[TrainingSample]:
    return [TrainingSample(features={"x": float(i)}, label=float(i % 2)) for i in range(n)]


def test_train_test_split_is_reproducible_with_same_seed():
    samples = _samples(20)

    result_a = split(samples, SplitStrategy.TRAIN_TEST, test_ratio=0.25, seed=7)
    result_b = split(samples, SplitStrategy.TRAIN_TEST, test_ratio=0.25, seed=7)

    assert result_a.train == result_b.train
    assert result_a.test == result_b.test
    assert len(result_a.train) + len(result_a.test) == 20
    assert len(result_a.test) == 5


def test_train_test_split_different_seeds_can_differ():
    samples = _samples(20)
    result_a = split(samples, SplitStrategy.TRAIN_TEST, test_ratio=0.5, seed=1)
    result_b = split(samples, SplitStrategy.TRAIN_TEST, test_ratio=0.5, seed=2)
    assert result_a.train != result_b.train or result_a.test != result_b.test


def test_train_val_test_split_produces_three_disjoint_sets():
    samples = _samples(40)

    result = split(samples, SplitStrategy.TRAIN_VAL_TEST, val_ratio=0.2, test_ratio=0.2, seed=3)

    assert len(result.train) + len(result.validation) + len(result.test) == 40
    all_ids = [id(s) for s in (*result.train, *result.validation, *result.test)]
    assert len(set(all_ids)) == len(all_ids)


def test_holdout_preserves_chronological_order():
    samples = _samples(10)

    result = split(samples, SplitStrategy.HOLDOUT, holdout_ratio=0.3)

    assert result.train == tuple(samples[:7])
    assert result.test == tuple(samples[7:])


def test_rolling_window_produces_sliding_folds():
    samples = _samples(10)

    result = split(samples, SplitStrategy.ROLLING_WINDOW, window_size=4, test_size=2)

    assert len(result.folds) > 0
    first_train, first_test = result.folds[0]
    assert len(first_train) == 4
    assert len(first_test) == 2
    assert first_train == tuple(samples[:4])
    assert first_test == tuple(samples[4:6])


def test_rolling_window_raises_when_not_enough_samples():
    samples = _samples(3)
    with pytest.raises(InsufficientSamplesForSplitError):
        split(samples, SplitStrategy.ROLLING_WINDOW, window_size=4, test_size=2)


def test_walk_forward_expands_training_window_each_fold():
    samples = _samples(10)

    result = split(samples, SplitStrategy.WALK_FORWARD, min_train_size=4, step=2)

    sizes = [len(train) for train, _ in result.folds]
    assert sizes == sorted(sizes)  # strictly non-decreasing — expanding window
    assert sizes[0] == 4


def test_time_series_split_produces_expanding_folds():
    samples = _samples(30)

    result = split(samples, SplitStrategy.TIME_SERIES_SPLIT, n_splits=5)

    assert len(result.folds) == 5
    for train, test in result.folds:
        assert len(train) > 0
        assert len(test) > 0


def test_split_requires_at_least_two_samples():
    with pytest.raises(InsufficientSamplesForSplitError):
        split(_samples(1), SplitStrategy.TRAIN_TEST)
