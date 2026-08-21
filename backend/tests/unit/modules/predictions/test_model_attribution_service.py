"""Phase 3 (Sports-Analyst Explainability) — real per-instance model attribution."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB

from modules.predictions.application.model_attribution_service import (
    BackgroundSampleRequiredError,
    ModelAttributionService,
    UnsupportedForMulticlassError,
)
from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.domain.ml_value_objects import MLAlgorithm

pytestmark = pytest.mark.asyncio


def _linear_adapter():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(60, 3))
    y = (X[:, 0] - X[:, 1] > 0).astype(float)
    estimator = LogisticRegression().fit(X, y)
    adapter = SklearnAdapter(algorithm=MLAlgorithm.LOGISTIC_REGRESSION, target_type=TargetType.CLASSIFICATION)
    adapter.feature_order = ["a", "b", "c"]
    adapter._model = estimator
    return adapter


def _nb_adapter():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(60, 3))
    y = (X[:, 0] > 0).astype(float)
    estimator = GaussianNB().fit(X, y)
    adapter = SklearnAdapter(algorithm=MLAlgorithm.GAUSSIAN_NB, target_type=TargetType.CLASSIFICATION)
    adapter.feature_order = ["a", "b", "c"]
    adapter._model = estimator
    return adapter


class TestLinearAttribution:
    async def test_real_coefficient_decomposition(self):
        adapter = _linear_adapter()
        service = ModelAttributionService()

        result = service.attribute(adapter, {"a": 2.0, "b": -1.0, "c": 0.5})

        assert len(result) == 3
        coef = adapter._model.coef_.reshape(-1)
        expected = {"a": coef[0] * 2.0, "b": coef[1] * -1.0, "c": coef[2] * 0.5}
        for attributed in result:
            assert attributed.contribution == pytest.approx(expected[attributed.feature_key])
            assert attributed.method == "linear_coefficient"
            assert attributed.direction == ("supports" if attributed.contribution >= 0 else "opposes")

    async def test_ranked_by_absolute_contribution(self):
        adapter = _linear_adapter()
        service = ModelAttributionService()

        result = service.attribute(adapter, {"a": 2.0, "b": -1.0, "c": 0.5})

        magnitudes = [abs(a.contribution) for a in result]
        assert magnitudes == sorted(magnitudes, reverse=True)

    async def test_multiclass_raises_not_fabricates(self):
        adapter = _linear_adapter()
        adapter.class_labels = ("HOME_WIN", "DRAW", "AWAY_WIN")
        service = ModelAttributionService()

        with pytest.raises(UnsupportedForMulticlassError):
            service.attribute(adapter, {"a": 1.0, "b": 1.0, "c": 1.0})


class TestShapAttribution:
    async def test_missing_background_raises_not_fabricates(self):
        adapter = _nb_adapter()
        service = ModelAttributionService()

        with pytest.raises(BackgroundSampleRequiredError):
            service.attribute(adapter, {"a": 1.0, "b": 1.0, "c": 1.0})

    async def test_shap_used_for_non_linear_estimator(self):
        adapter = _nb_adapter()
        service = ModelAttributionService()
        background = [{"a": float(i % 3), "b": float(i % 2), "c": 0.0} for i in range(10)]

        result = service.attribute(adapter, {"a": 3.0, "b": 0.0, "c": 0.0}, background=background)

        assert len(result) == 3
        assert all(a.method == "shap" for a in result)
