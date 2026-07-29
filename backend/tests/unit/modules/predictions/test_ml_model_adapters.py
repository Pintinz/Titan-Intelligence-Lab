"""Tests for the Milestone 9.1 `PredictionModelPort` framework adapters — LightGBM, XGBoost,
CatBoost, and the generic scikit-learn adapter across its 8 algorithms. Each adapter is exercised
against a small, deterministically-generated, linearly-separable (classification) or linear
(regression) synthetic dataset — real fitting, real inference, no mocked ML internals.
"""

from __future__ import annotations

import pytest

from modules.predictions.domain.ml_value_objects import MLAlgorithm
from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml.catboost_adapter import CatBoostAdapter
from modules.predictions.infrastructure.ml.lightgbm_adapter import LightGBMAdapter
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.infrastructure.ml.xgboost_adapter import XGBoostAdapter
from modules.predictions.ports.ml_model import (
    InsufficientTrainingDataError,
    ModelNotFittedError,
    TrainingSample,
    UnsupportedAlgorithmForTargetTypeError,
)


def _classification_samples(n: int = 60) -> list[TrainingSample]:
    samples = []
    for i in range(n):
        x1 = float(i % 10) - 5.0
        x2 = float((i * 3) % 10) - 5.0
        label = 1.0 if (x1 + x2) > 0 else 0.0
        samples.append(TrainingSample(features={"x1": x1, "x2": x2}, label=label))
    return samples


def _regression_samples(n: int = 60) -> list[TrainingSample]:
    samples = []
    for i in range(n):
        x1 = float(i % 10) - 5.0
        x2 = float((i * 2) % 10) - 5.0
        label = 2.0 * x1 - 1.0 * x2 + 3.0
        samples.append(TrainingSample(features={"x1": x1, "x2": x2}, label=label))
    return samples


BOOSTING_ADAPTERS = [LightGBMAdapter, XGBoostAdapter, CatBoostAdapter]


@pytest.mark.parametrize("adapter_cls", BOOSTING_ADAPTERS)
class TestBoostingAdapters:
    async def test_classification_fit_predict(self, adapter_cls):
        adapter = adapter_cls(target_type=TargetType.CLASSIFICATION)
        metrics = await adapter.fit(_classification_samples())
        assert metrics.sample_count == 60
        assert metrics.metric_name == "train_accuracy"
        assert 0.0 <= metrics.metric_value <= 1.0
        assert adapter.is_fitted()

        result = adapter.predict_one({"x1": 4.0, "x2": 4.0})
        assert result.value == "positive"
        assert 0.0 <= result.probability <= 1.0

    async def test_regression_fit_predict(self, adapter_cls):
        adapter = adapter_cls(target_type=TargetType.REGRESSION)
        await adapter.fit(_regression_samples())
        result = adapter.predict_one({"x1": 1.0, "x2": 1.0})
        assert isinstance(result.raw_score, float)
        assert 0.0 <= result.probability <= 1.0

    async def test_fit_rejects_insufficient_samples(self, adapter_cls):
        adapter = adapter_cls(target_type=TargetType.CLASSIFICATION)
        with pytest.raises(InsufficientTrainingDataError):
            await adapter.fit(_classification_samples(n=5))

    async def test_predict_before_fit_raises(self, adapter_cls):
        adapter = adapter_cls()
        with pytest.raises(ModelNotFittedError):
            adapter.predict_one({"x1": 1.0})

    async def test_feature_importance_before_fit_raises(self, adapter_cls):
        adapter = adapter_cls()
        with pytest.raises(ModelNotFittedError):
            adapter.feature_importance()

    async def test_feature_importance_sums_to_one(self, adapter_cls):
        adapter = adapter_cls(target_type=TargetType.CLASSIFICATION)
        await adapter.fit(_classification_samples())
        importance = adapter.feature_importance()
        assert set(importance.keys()) == {"x1", "x2"}
        assert sum(importance.values()) == pytest.approx(1.0, abs=1e-6)

    async def test_serialize_roundtrip(self, adapter_cls):
        adapter = adapter_cls(target_type=TargetType.CLASSIFICATION)
        await adapter.fit(_classification_samples())
        original = adapter.predict_one({"x1": 3.0, "x2": 3.0})

        restored = adapter_cls()
        restored.deserialize(adapter.serialize())
        assert restored.is_fitted()
        again = restored.predict_one({"x1": 3.0, "x2": 3.0})
        assert again.value == original.value
        assert again.probability == pytest.approx(original.probability)

    async def test_serialize_before_fit_raises(self, adapter_cls):
        adapter = adapter_cls()
        with pytest.raises(ModelNotFittedError):
            adapter.serialize()

    async def test_fit_with_validation_samples_enables_early_stopping(self, adapter_cls):
        adapter = adapter_cls(target_type=TargetType.CLASSIFICATION, early_stopping_rounds=5)
        metrics = await adapter.fit(_classification_samples(n=80), validation_samples=_classification_samples(n=20))
        assert adapter.is_fitted()
        assert metrics.sample_count == 80
        result = adapter.predict_one({"x1": 4.0, "x2": 4.0})
        assert result.value == "positive"

    async def test_fit_with_validation_samples_enables_early_stopping(self, adapter_cls):
        adapter = adapter_cls(target_type=TargetType.CLASSIFICATION, early_stopping_rounds=3)
        train = _classification_samples(80)
        validation = _classification_samples(20)

        metrics = await adapter.fit(train, validation_samples=validation)

        assert adapter.is_fitted()
        assert 0.0 <= metrics.metric_value <= 1.0


CLASSIFICATION_ALGORITHMS = [
    MLAlgorithm.RANDOM_FOREST,
    MLAlgorithm.EXTRA_TREES,
    MLAlgorithm.LOGISTIC_REGRESSION,
    MLAlgorithm.RIDGE,
    MLAlgorithm.ELASTIC_NET,
    MLAlgorithm.SVM,
    MLAlgorithm.GAUSSIAN_NB,
    MLAlgorithm.MLP,
]

REGRESSION_ALGORITHMS = [
    MLAlgorithm.RANDOM_FOREST,
    MLAlgorithm.EXTRA_TREES,
    MLAlgorithm.RIDGE,
    MLAlgorithm.ELASTIC_NET,
    MLAlgorithm.SVM,
    MLAlgorithm.MLP,
]


class TestSklearnAdapter:
    @pytest.mark.parametrize("algorithm", CLASSIFICATION_ALGORITHMS)
    async def test_classification_fit_predict(self, algorithm):
        params = {"max_iter": 2000} if algorithm is MLAlgorithm.MLP else {}
        adapter = SklearnAdapter(algorithm=algorithm, target_type=TargetType.CLASSIFICATION, params=params)
        metrics = await adapter.fit(_classification_samples())
        assert metrics.sample_count == 60
        assert adapter.is_fitted()

        result = adapter.predict_one({"x1": 4.0, "x2": 4.0})
        assert result.value in {"positive", "negative"}
        assert 0.0 <= result.probability <= 1.0

    @pytest.mark.parametrize("algorithm", REGRESSION_ALGORITHMS)
    async def test_regression_fit_predict(self, algorithm):
        params = {"max_iter": 2000} if algorithm is MLAlgorithm.MLP else {}
        adapter = SklearnAdapter(algorithm=algorithm, target_type=TargetType.REGRESSION, params=params)
        await adapter.fit(_regression_samples())
        result = adapter.predict_one({"x1": 1.0, "x2": 1.0})
        assert isinstance(result.raw_score, float)

    async def test_logistic_regression_has_no_regression_form(self):
        adapter = SklearnAdapter(algorithm=MLAlgorithm.LOGISTIC_REGRESSION, target_type=TargetType.REGRESSION)
        with pytest.raises(UnsupportedAlgorithmForTargetTypeError):
            await adapter.fit(_regression_samples())

    async def test_gaussian_nb_has_no_regression_form(self):
        adapter = SklearnAdapter(algorithm=MLAlgorithm.GAUSSIAN_NB, target_type=TargetType.REGRESSION)
        with pytest.raises(UnsupportedAlgorithmForTargetTypeError):
            await adapter.fit(_regression_samples())

    async def test_fit_rejects_insufficient_samples(self):
        adapter = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        with pytest.raises(InsufficientTrainingDataError):
            await adapter.fit(_classification_samples(n=5))

    async def test_predict_before_fit_raises(self):
        adapter = SklearnAdapter()
        with pytest.raises(ModelNotFittedError):
            adapter.predict_one({"x1": 1.0})

    async def test_tree_ensemble_feature_importance_sums_to_one(self):
        adapter = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        await adapter.fit(_classification_samples())
        importance = adapter.feature_importance()
        assert sum(importance.values()) == pytest.approx(1.0, abs=1e-6)

    async def test_svm_feature_importance_falls_back_to_uniform(self):
        adapter = SklearnAdapter(algorithm=MLAlgorithm.SVM, target_type=TargetType.CLASSIFICATION)
        await adapter.fit(_classification_samples())
        importance = adapter.feature_importance()
        # SVC exposes neither feature_importances_ nor coef_ (non-linear kernel) — honest uniform default.
        assert importance == {"x1": 0.5, "x2": 0.5}

    async def test_serialize_roundtrip_preserves_algorithm(self):
        adapter = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        await adapter.fit(_classification_samples())
        original = adapter.predict_one({"x1": 3.0, "x2": 3.0})

        restored = SklearnAdapter()
        restored.deserialize(adapter.serialize())
        assert restored.algorithm is MLAlgorithm.RANDOM_FOREST
        again = restored.predict_one({"x1": 3.0, "x2": 3.0})
        assert again.value == original.value
