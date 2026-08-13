from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from modules.predictions.application.dataset_splitter import (
    InsufficientSamplesForSplitError,
    MissingTemporalReferenceError,
    split,
)
from modules.predictions.domain.dataset import SplitStrategy
from modules.predictions.ports.ml_model import TrainingSample

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _samples(n: int) -> list[TrainingSample]:
    """Non-temporal helper (TRAIN_TEST/TRAIN_VAL_TEST) — no reference_time needed."""
    return [TrainingSample(features={"x": float(i)}, label=float(i % 2)) for i in range(n)]


def _chronological_samples(n: int) -> list[TrainingSample]:
    """Samples with a real, strictly increasing reference_time, built and returned IN
    chronological order — the baseline every "shuffled input" test below permutes."""
    return [
        TrainingSample(features={"x": float(i)}, label=float(i % 2), reference_time=T0 + timedelta(days=i))
        for i in range(n)
    ]


def _shuffled(samples: list[TrainingSample], seed: int = 1) -> list[TrainingSample]:
    shuffled = list(samples)
    random.Random(seed).shuffle(shuffled)
    return shuffled


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


def test_train_test_does_not_require_reference_time():
    """Milestone 18 — TRAIN_TEST/TRAIN_VAL_TEST are not order-sensitive and must keep working
    exactly as before for samples with no reference_time at all (existing non-temporal behavior
    preserved, per the milestone's own explicit requirement)."""
    samples = _samples(20)
    assert all(s.reference_time is None for s in samples)

    result = split(samples, SplitStrategy.TRAIN_TEST, test_ratio=0.25, seed=7)

    assert len(result.train) + len(result.test) == 20


def test_train_val_test_split_produces_three_disjoint_sets():
    samples = _samples(40)

    result = split(samples, SplitStrategy.TRAIN_VAL_TEST, val_ratio=0.2, test_ratio=0.2, seed=3)

    assert len(result.train) + len(result.validation) + len(result.test) == 40
    all_ids = [id(s) for s in (*result.train, *result.validation, *result.test)]
    assert len(set(all_ids)) == len(all_ids)


def test_split_requires_at_least_two_samples():
    with pytest.raises(InsufficientSamplesForSplitError):
        split(_samples(1), SplitStrategy.TRAIN_TEST)


# --- Milestone 18: the four temporal strategies must fail closed without reference_time ---------


@pytest.mark.parametrize(
    "strategy,kwargs",
    [
        (SplitStrategy.HOLDOUT, {}),
        (SplitStrategy.ROLLING_WINDOW, {"window_size": 4, "test_size": 2}),
        (SplitStrategy.WALK_FORWARD, {"min_train_size": 4, "step": 2}),
        (SplitStrategy.TIME_SERIES_SPLIT, {"n_splits": 3}),
    ],
)
def test_temporal_strategies_raise_when_reference_time_missing(strategy, kwargs):
    samples = _samples(10)  # no reference_time — must never silently fall back to input order
    with pytest.raises(MissingTemporalReferenceError):
        split(samples, strategy, **kwargs)


# --- Milestone 18: shuffled input must still produce a chronologically correct split -------------


def test_holdout_sorts_shuffled_input_chronologically():
    chronological = _chronological_samples(10)
    shuffled = _shuffled(chronological)

    result = split(shuffled, SplitStrategy.HOLDOUT, holdout_ratio=0.3)

    assert result.train == tuple(chronological[:7])
    assert result.test == tuple(chronological[7:])
    assert result.train[-1].reference_time <= result.test[0].reference_time


def test_rolling_window_sorts_shuffled_input_chronologically():
    chronological = _chronological_samples(10)
    shuffled = _shuffled(chronological)

    result = split(shuffled, SplitStrategy.ROLLING_WINDOW, window_size=4, test_size=2)

    assert len(result.folds) > 0
    first_train, first_test = result.folds[0]
    assert first_train == tuple(chronological[:4])
    assert first_test == tuple(chronological[4:6])
    for train_fold, test_fold in result.folds:
        assert train_fold[-1].reference_time <= test_fold[0].reference_time


def test_rolling_window_raises_when_not_enough_samples():
    samples = _chronological_samples(3)
    with pytest.raises(InsufficientSamplesForSplitError):
        split(samples, SplitStrategy.ROLLING_WINDOW, window_size=4, test_size=2)


def test_walk_forward_sorts_shuffled_input_chronologically():
    chronological = _chronological_samples(10)
    shuffled = _shuffled(chronological)

    result = split(shuffled, SplitStrategy.WALK_FORWARD, min_train_size=4, step=2)

    sizes = [len(train) for train, _ in result.folds]
    assert sizes == sorted(sizes)  # strictly non-decreasing — expanding window
    assert sizes[0] == 4
    for train_fold, test_fold in result.folds:
        assert train_fold[-1].reference_time <= test_fold[0].reference_time


def test_time_series_split_sorts_shuffled_input_chronologically():
    chronological = _chronological_samples(30)
    shuffled = _shuffled(chronological)

    result = split(shuffled, SplitStrategy.TIME_SERIES_SPLIT, n_splits=5)

    assert len(result.folds) == 5
    for train, test in result.folds:
        assert len(train) > 0
        assert len(test) > 0
        assert train[-1].reference_time <= test[0].reference_time


@pytest.mark.parametrize(
    "strategy,kwargs",
    [
        (SplitStrategy.HOLDOUT, {"holdout_ratio": 0.3}),
        (SplitStrategy.ROLLING_WINDOW, {"window_size": 4, "test_size": 2}),
        (SplitStrategy.WALK_FORWARD, {"min_train_size": 4, "step": 2}),
        (SplitStrategy.TIME_SERIES_SPLIT, {"n_splits": 3}),
    ],
)
def test_split_result_identical_across_many_random_shuffles(strategy, kwargs):
    """Property-style temporal test (Milestone 18 §10): the split must not merely happen to work
    because the sample list arrived in order. Feed the SAME 12 chronological samples through 8
    different random shuffles and confirm every one of them produces byte-identical train/fold
    output — proof the result depends only on reference_time, never on input position."""
    chronological = _chronological_samples(12)

    results = [split(_shuffled(chronological, seed=seed), strategy, **kwargs) for seed in range(8)]

    first = results[0]
    for other in results[1:]:
        assert other.train == first.train
        assert other.folds == first.folds
        assert other.test == first.test


def test_duplicate_reference_times_still_produce_a_valid_deterministic_split():
    """Milestone 18 §8 — several samples sharing the identical reference_time must not raise or
    produce a non-deterministic result; a stable sort resolves ties by input order."""
    tied_time = T0 + timedelta(days=5)
    samples = [
        TrainingSample(features={"x": float(i)}, label=float(i % 2), reference_time=tied_time) for i in range(4)
    ] + _chronological_samples(6)

    result_a = split(list(samples), SplitStrategy.TIME_SERIES_SPLIT, n_splits=3)
    result_b = split(list(samples), SplitStrategy.TIME_SERIES_SPLIT, n_splits=3)

    assert result_a.folds == result_b.folds
    for train, test in result_a.folds:
        assert train[-1].reference_time <= test[0].reference_time


def test_walk_forward_expands_training_window_each_fold():
    samples = _chronological_samples(10)

    result = split(samples, SplitStrategy.WALK_FORWARD, min_train_size=4, step=2)

    sizes = [len(train) for train, _ in result.folds]
    assert sizes == sorted(sizes)  # strictly non-decreasing — expanding window
    assert sizes[0] == 4


def test_time_series_split_produces_expanding_folds():
    samples = _chronological_samples(30)

    result = split(samples, SplitStrategy.TIME_SERIES_SPLIT, n_splits=5)

    assert len(result.folds) == 5
    for train, test in result.folds:
        assert len(train) > 0
        assert len(test) > 0


def test_holdout_preserves_chronological_order():
    samples = _chronological_samples(10)

    result = split(samples, SplitStrategy.HOLDOUT, holdout_ratio=0.3)

    assert result.train == tuple(samples[:7])
    assert result.test == tuple(samples[7:])


def test_rolling_window_produces_sliding_folds():
    samples = _chronological_samples(10)

    result = split(samples, SplitStrategy.ROLLING_WINDOW, window_size=4, test_size=2)

    assert len(result.folds) > 0
    first_train, first_test = result.folds[0]
    assert len(first_train) == 4
    assert len(first_test) == 2
    assert first_train == tuple(samples[:4])
    assert first_test == tuple(samples[4:6])
