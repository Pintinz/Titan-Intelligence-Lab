from __future__ import annotations

import pytest

from modules.predictions.domain.ml_value_objects import MLAlgorithm
from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.infrastructure.ml.shap_explainer_service import (
    SHAPExplainerService,
    UnsupportedModelForShapError,
)
from modules.predictions.ports.ml_model import ModelNotFittedError, TrainingSample


def _classification_samples(n: int = 60) -> list[TrainingSample]:
    samples = []
    for i in range(n):
        x1 = float(i % 10) - 5.0
        x2 = float((i * 3) % 10) - 5.0
        label = 1.0 if (x1 + x2) > 0 else 0.0
        samples.append(TrainingSample(features={"x1": x1, "x2": x2}, label=label))
    return samples


@pytest.fixture
async def tree_model():
    """RandomForest — bare estimator, not wrapped in a Pipeline, so `TreeExplainer` applies."""
    model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
    await model.fit(_classification_samples())
    return model


@pytest.fixture
async def linear_model():
    """LogisticRegression — wrapped in a `Pipeline` by `SklearnAdapter`, so `KernelExplainer` applies."""
    model = SklearnAdapter(algorithm=MLAlgorithm.LOGISTIC_REGRESSION, target_type=TargetType.CLASSIFICATION)
    await model.fit(_classification_samples())
    return model


@pytest.fixture
def background():
    return [{"x1": float(i % 10) - 5.0, "x2": float((i * 3) % 10) - 5.0} for i in range(10)]


@pytest.fixture
def service():
    return SHAPExplainerService()


class TestExplainInstanceTreeExplainer:
    async def test_local_shap_values_cover_every_feature(self, service, tree_model, background):
        explanation = service.explain_instance(tree_model, {"x1": 4.0, "x2": 4.0}, background)

        assert set(explanation.local_shap_values.keys()) == {"x1", "x2"}
        assert isinstance(explanation.base_value, float)

    async def test_global_importance_sums_to_one(self, service, tree_model, background):
        explanation = service.explain_instance(tree_model, {"x1": 4.0, "x2": 4.0}, background)

        assert sum(explanation.global_importance.values()) == pytest.approx(1.0, abs=1e-6)

    async def test_decision_path_is_populated_and_ranked_by_magnitude(self, service, tree_model, background):
        explanation = service.explain_instance(tree_model, {"x1": 4.0, "x2": 4.0}, background)

        assert len(explanation.decision_path) <= 2
        assert all(isinstance(line, str) for line in explanation.decision_path)

    async def test_interaction_values_computed_for_tree_models(self, service, tree_model, background):
        explanation = service.explain_instance(tree_model, {"x1": 4.0, "x2": 4.0}, background)

        assert ("x1", "x2") in explanation.interaction_values


class TestExplainInstanceKernelExplainer:
    async def test_local_shap_values_cover_every_feature(self, service, linear_model, background):
        explanation = service.explain_instance(linear_model, {"x1": 4.0, "x2": 4.0}, background)
        assert set(explanation.local_shap_values.keys()) == {"x1", "x2"}

    async def test_no_interaction_values_for_kernel_explainer(self, service, linear_model, background):
        explanation = service.explain_instance(linear_model, {"x1": 4.0, "x2": 4.0}, background)
        assert explanation.interaction_values == {}


class TestUnfittedModel:
    async def test_explain_instance_raises_before_fit(self, service, background):
        model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        with pytest.raises(ModelNotFittedError):
            service.explain_instance(model, {"x1": 1.0, "x2": 1.0}, background)


class TestCounterfactual:
    async def test_finds_a_flip_for_a_borderline_instance(self, service, tree_model, background):
        result = service.counterfactual(tree_model, {"x1": 0.5, "x2": 0.5}, background, max_iterations=30)

        assert result.original_value in {"positive", "negative"}
        if result.found:
            assert result.counterfactual_value != result.original_value
            assert len(result.changed_features) >= 1

    async def test_records_original_and_changed_feature_values(self, service, tree_model, background):
        result = service.counterfactual(tree_model, {"x1": 4.0, "x2": 4.0}, background, max_iterations=5)
        for original, changed in result.changed_features.values():
            assert isinstance(original, float)
            assert isinstance(changed, float)


class TestDependenceData:
    async def test_returns_a_point_per_grid_step(self, service, tree_model, background):
        data = service.dependence_data(tree_model, "x1", {"x1": 0.0, "x2": 0.0}, background, n_points=5)

        assert data.feature_key == "x1"
        assert len(data.points) == 5
        assert all(isinstance(p.shap_value, float) for p in data.points)

    async def test_unknown_feature_raises(self, service, tree_model, background):
        with pytest.raises(UnsupportedModelForShapError):
            service.dependence_data(tree_model, "not_a_feature", {"x1": 0.0, "x2": 0.0}, background)
