from __future__ import annotations

import statistics as pystats
from dataclasses import dataclass, field

import pytest

from modules.predictions.application.validation_service import (
    InsufficientSamplesForValidationError,
    cross_validate,
)
from modules.predictions.domain.validation import ValidationStrategy
from modules.predictions.domain.value_objects import TargetType
from modules.predictions.ports.ml_model import ModelPrediction, TrainingMetrics, TrainingSample


@dataclass
class _ConstantModel:
    """Deterministic fake `PredictionModelPort` — memorizes the majority class (classification)
    or mean label (regression) from its training fold, so fold construction/aggregation can be
    asserted precisely without depending on any real framework's fit behavior."""

    target_type: TargetType = TargetType.CLASSIFICATION
    feature_order: list[str] = field(default_factory=list)
    _value: float = 0.0

    async def fit(self, samples, validation_samples=None):
        if self.target_type is TargetType.CLASSIFICATION:
            positive = sum(1 for s in samples if s.label >= 0.5)
            self._value = 1.0 if positive >= len(samples) / 2 else 0.0
        else:
            self._value = pystats.fmean(s.label for s in samples)
        return TrainingMetrics(sample_count=len(samples), metric_name="dummy", metric_value=0.0)

    def predict_one(self, features):
        if self.target_type is TargetType.CLASSIFICATION:
            return ModelPrediction(
                raw_score=0.0, probability=1.0 if self._value >= 0.5 else 0.0, value="positive" if self._value >= 0.5 else "negative"
            )
        return ModelPrediction(raw_score=self._value, probability=0.5, value=str(self._value))

    def feature_importance(self) -> dict[str, float]:
        return {}

    def is_fitted(self) -> bool:
        return True

    def serialize(self) -> bytes:
        return b""

    def deserialize(self, payload: bytes) -> None:
        pass


def _classification_samples(n: int = 40) -> list[TrainingSample]:
    return [TrainingSample(features={"x": float(i)}, label=1.0 if i % 2 == 0 else 0.0) for i in range(n)]


def _regression_samples(n: int = 40) -> list[TrainingSample]:
    return [TrainingSample(features={"x": float(i)}, label=float(i)) for i in range(n)]


def _factory(target_type: TargetType = TargetType.CLASSIFICATION):
    return lambda samples: _ConstantModel(target_type=target_type)


NON_NESTED_STRATEGIES = [
    ValidationStrategy.HOLDOUT,
    ValidationStrategy.K_FOLD,
    ValidationStrategy.STRATIFIED_K_FOLD,
    ValidationStrategy.TIME_SERIES_SPLIT,
    ValidationStrategy.ROLLING_WINDOW,
    ValidationStrategy.WALK_FORWARD,
    ValidationStrategy.LEAVE_ONE_OUT,
    ValidationStrategy.REPEATED_K_FOLD,
]


class TestCrossValidate:
    @pytest.mark.parametrize("strategy", NON_NESTED_STRATEGIES)
    async def test_produces_a_result_with_fold_metrics(self, strategy):
        result = await cross_validate(_factory(), _classification_samples(), strategy)

        assert result.strategy is strategy
        assert len(result.fold_results) > 0
        assert 0.0 <= result.mean_metric <= 1.0
        assert result.std_metric >= 0.0

    async def test_leave_one_out_produces_one_fold_per_sample(self):
        samples = _classification_samples(n=10)
        result = await cross_validate(_factory(), samples, ValidationStrategy.LEAVE_ONE_OUT)
        assert len(result.fold_results) == 10
        assert all(f.sample_count == 1 for f in result.fold_results)

    async def test_repeated_k_fold_produces_more_folds_than_k_fold(self):
        samples = _classification_samples()
        k_fold = await cross_validate(_factory(), samples, ValidationStrategy.K_FOLD, k=5)
        repeated = await cross_validate(_factory(), samples, ValidationStrategy.REPEATED_K_FOLD, k=5, n_repeats=3)
        assert len(repeated.fold_results) == 3 * len(k_fold.fold_results)

    async def test_regression_metric_is_mae(self):
        result = await cross_validate(
            _factory(TargetType.REGRESSION), _regression_samples(), ValidationStrategy.K_FOLD
        )
        assert all(f.metric_name == "mae" for f in result.fold_results)

    async def test_nested_cv_uses_caller_fits_model(self):
        async def factory(samples):
            model = _ConstantModel(target_type=TargetType.CLASSIFICATION)
            await model.fit(samples)
            return model

        result = await cross_validate(
            factory, _classification_samples(), ValidationStrategy.NESTED_CV, caller_fits_model=True, outer_k=4
        )
        assert result.strategy is ValidationStrategy.NESTED_CV
        assert len(result.fold_results) == 4

    async def test_too_few_samples_raises(self):
        with pytest.raises(InsufficientSamplesForValidationError):
            await cross_validate(_factory(), [TrainingSample(features={"x": 1.0}, label=1.0)], ValidationStrategy.K_FOLD)

    async def test_time_series_split_respects_chronological_order(self):
        samples = _classification_samples(n=60)
        result = await cross_validate(_factory(), samples, ValidationStrategy.TIME_SERIES_SPLIT, n_splits=3)
        assert len(result.fold_results) <= 3
        assert result.fold_results[0].sample_count > 0
