from __future__ import annotations

import math

import pytest

from modules.predictions.domain.probability_metrics import log_loss


def test_empty_samples_returns_zero():
    assert log_loss([]) == 0.0


def test_perfect_predictions_approach_zero():
    assert log_loss([1.0 - 1e-16] * 10) == pytest.approx(0.0, abs=1e-10)


def test_coin_flip_predictions_equal_log_two():
    assert log_loss([0.5] * 10) == pytest.approx(math.log(2))


def test_clips_extreme_probabilities_instead_of_producing_infinity():
    # A hard 0.0 for the true class would be -log(0) == inf without clipping.
    assert math.isfinite(log_loss([0.0]))
    assert math.isfinite(log_loss([1.0]))


def test_worse_predictions_produce_higher_loss():
    confident_and_right = log_loss([0.95] * 10)
    confident_and_wrong = log_loss([0.05] * 10)
    assert confident_and_wrong > confident_and_right
