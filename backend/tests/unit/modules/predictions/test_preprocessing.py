from __future__ import annotations

import pytest

from modules.predictions.application.preprocessing import detect_outliers, impute_missing, select_features
from modules.predictions.ports.ml_model import TrainingSample


def test_impute_missing_zero_fill():
    samples = [
        TrainingSample(features={"a": 1.0}, label=1.0),
        TrainingSample(features={"a": 2.0, "b": 5.0}, label=0.0),
    ]

    imputed = impute_missing(samples, ["a", "b"], strategy="zero")

    assert imputed[0].features == {"a": 1.0, "b": 0.0}
    assert imputed[1].features == {"a": 2.0, "b": 5.0}


def test_impute_missing_mean_fill():
    samples = [
        TrainingSample(features={"a": 1.0, "b": 10.0}, label=1.0),
        TrainingSample(features={"a": 3.0}, label=0.0),
        TrainingSample(features={"a": 5.0, "b": 20.0}, label=1.0),
    ]

    imputed = impute_missing(samples, ["a", "b"], strategy="mean")

    assert imputed[1].features["b"] == pytest.approx(15.0)


def test_impute_missing_mean_fill_with_no_observations_falls_back_to_zero():
    samples = [TrainingSample(features={}, label=1.0)]
    imputed = impute_missing(samples, ["a"], strategy="mean")
    assert imputed[0].features["a"] == 0.0


def test_impute_missing_rejects_unknown_strategy():
    with pytest.raises(ValueError):
        impute_missing([], ["a"], strategy="median")


def test_detect_outliers_flags_extreme_value():
    samples = [TrainingSample(features={"x": 1.0 + i * 0.01}, label=0.0) for i in range(20)]
    samples.append(TrainingSample(features={"x": 1000.0}, label=1.0))

    flagged = detect_outliers(samples, ["x"], z_threshold=3.0)

    assert len(samples) - 1 in flagged


def test_detect_outliers_no_flags_for_uniform_data():
    samples = [TrainingSample(features={"x": 5.0}, label=0.0) for _ in range(10)]
    assert detect_outliers(samples, ["x"], z_threshold=3.0) == []


def test_select_features_variance_prefers_higher_variance():
    samples = [
        TrainingSample(features={"low_var": 1.0, "high_var": float(i)}, label=float(i % 2))
        for i in range(20)
    ]

    selected = select_features(samples, ["low_var", "high_var"], top_k=1, method="variance")

    assert selected == ["high_var"]


def test_select_features_correlation_prefers_predictive_feature():
    samples = [
        TrainingSample(features={"noise": float((i * 7) % 5), "signal": float(i % 2)}, label=float(i % 2))
        for i in range(30)
    ]

    selected = select_features(samples, ["noise", "signal"], top_k=1, method="correlation")

    assert selected == ["signal"]


def test_select_features_top_k_at_or_above_count_returns_all():
    samples = [TrainingSample(features={"a": 1.0, "b": 2.0}, label=1.0)]
    assert select_features(samples, ["a", "b"], top_k=5) == ["a", "b"]


def test_select_features_rejects_unknown_method():
    with pytest.raises(ValueError):
        select_features([], ["a"], top_k=1, method="chi2")
