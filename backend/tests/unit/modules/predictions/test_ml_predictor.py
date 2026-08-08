from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from modules.predictions.domain.value_objects import MarketKind, TargetType
from modules.predictions.infrastructure.predictors.ml_predictor import TrainedModelPredictor
from modules.predictions.ports.ml_model import ModelNotFittedError, ModelPrediction


@dataclass
class _FakeModel:
    """Minimal `PredictionModelPort` double — isolates `TrainedModelPredictor`'s adaptation logic
    (ModelPrediction -> PredictorOutput, importance -> signed contributions) from any real
    framework fitting."""

    target_type: TargetType = TargetType.CLASSIFICATION
    feature_order: list[str] = field(default_factory=lambda: ["x1", "x2"])
    _fitted: bool = False
    _prediction: ModelPrediction | None = None
    _importance: dict[str, float] = field(default_factory=dict)

    def is_fitted(self) -> bool:
        return self._fitted

    def predict_one(self, features: dict[str, float]) -> ModelPrediction:
        return self._prediction

    def feature_importance(self) -> dict[str, float]:
        return self._importance


async def test_predict_adapts_model_prediction_into_predictor_output():
    model = _FakeModel(
        _fitted=True,
        _prediction=ModelPrediction(raw_score=1.2, probability=0.77, value="positive"),
        _importance={"x1": 0.6, "x2": 0.4},
    )
    predictor = TrainedModelPredictor(market_kind=MarketKind.BINARY, model=model)

    output = await predictor.predict(MarketKind.BINARY, {"x1": 2.0, "x2": -1.0}, {})

    assert output.raw_score == 1.2
    assert output.probability == 0.77
    assert output.value == "positive"
    assert output.feature_contributions == {"x1": pytest.approx(1.2), "x2": pytest.approx(-0.4)}


async def test_predict_before_fit_raises():
    model = _FakeModel(_fitted=False)
    predictor = TrainedModelPredictor(market_kind=MarketKind.BINARY, model=model)

    with pytest.raises(ModelNotFittedError):
        await predictor.predict(MarketKind.BINARY, {"x1": 1.0}, {})


async def test_predict_passes_through_multiclass_distribution():
    """(2026-08-06) A multiclass-fitted model's own `ModelPrediction.distribution` (already keyed
    by the market's real labels, e.g. football.correct_score's scoreline grid) is passed straight
    through rather than being reinterpreted as a binary positive/negative split."""
    distribution = {"0-0": 0.1, "1-0": 0.5, "0-1": 0.4}
    model = _FakeModel(
        _fitted=True,
        _prediction=ModelPrediction(raw_score=0.0, probability=0.5, value="1-0", distribution=distribution),
        _importance={"x1": 1.0},
    )
    predictor = TrainedModelPredictor(market_kind=MarketKind.CORRECT_SCORE, model=model)

    output = await predictor.predict(MarketKind.CORRECT_SCORE, {"x1": 2.0}, {})

    assert output.value == "1-0"
    assert output.distribution == distribution


async def test_missing_importance_key_contributes_zero():
    model = _FakeModel(
        _fitted=True,
        _prediction=ModelPrediction(raw_score=0.0, probability=0.5, value="negative"),
        _importance={"x1": 1.0},
    )
    predictor = TrainedModelPredictor(market_kind=MarketKind.BINARY, model=model)

    output = await predictor.predict(MarketKind.BINARY, {"x1": 2.0, "x2": 5.0}, {})

    assert output.feature_contributions == {"x1": pytest.approx(2.0), "x2": pytest.approx(0.0)}
