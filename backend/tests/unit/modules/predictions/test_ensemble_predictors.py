from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from modules.predictions.domain.ml_value_objects import EnsembleMethod
from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.infrastructure.predictors.ensemble import (
    DynamicEnsemblePredictor,
    InvalidEnsembleConfigurationError,
    StackedEnsemblePredictor,
    VotingEnsemblePredictor,
)
from modules.predictions.ports.ml_model import ModelNotFittedError, ModelPrediction
from modules.predictions.ports.predictor import PredictorOutput


@dataclass
class _FixedPredictor:
    """Fake `PredictorPort` member returning a fixed output — isolates ensemble combination
    logic from any real framework."""

    output: PredictorOutput
    market_kind: MarketKind = MarketKind.BINARY

    async def predict(self, market_kind, features, mapping_weights) -> PredictorOutput:
        return self.output


def _output(probability: float, value: str, raw_score: float = 0.0, contributions: dict | None = None) -> PredictorOutput:
    return PredictorOutput(raw_score=raw_score, probability=probability, value=value, feature_contributions=contributions or {})


class TestVotingEnsemblePredictor:
    async def test_soft_voting_averages_probability(self):
        members = [
            _FixedPredictor(_output(0.8, "positive", raw_score=1.0, contributions={"x": 1.0})),
            _FixedPredictor(_output(0.6, "positive", raw_score=0.5, contributions={"x": 0.5})),
        ]
        ensemble = VotingEnsemblePredictor(market_kind=MarketKind.BINARY, members=members)

        result = await ensemble.predict(MarketKind.BINARY, {"x": 1.0}, {})

        assert result.probability == pytest.approx(0.7)
        assert result.raw_score == pytest.approx(0.75)
        assert result.value == "positive"
        assert result.feature_contributions == {"x": pytest.approx(0.75)}

    async def test_hard_voting_uses_majority_label(self):
        members = [
            _FixedPredictor(_output(0.9, "positive", raw_score=2.0)),
            _FixedPredictor(_output(0.4, "negative", raw_score=-1.0)),
            _FixedPredictor(_output(0.6, "positive", raw_score=1.0)),
        ]
        ensemble = VotingEnsemblePredictor(
            market_kind=MarketKind.BINARY, members=members, method=EnsembleMethod.HARD_VOTING
        )

        result = await ensemble.predict(MarketKind.BINARY, {}, {})

        assert result.value == "positive"
        assert result.probability == pytest.approx(2 / 3)
        assert result.raw_score == pytest.approx(1.5)  # mean of the two agreeing members' raw_scores

    async def test_weighted_voting_respects_weights(self):
        members = [
            _FixedPredictor(_output(1.0, "positive", raw_score=5.0)),
            _FixedPredictor(_output(0.0, "negative", raw_score=-5.0)),
        ]
        ensemble = VotingEnsemblePredictor(
            market_kind=MarketKind.BINARY, members=members, method=EnsembleMethod.WEIGHTED_VOTING, weights=[3.0, 1.0]
        )

        result = await ensemble.predict(MarketKind.BINARY, {}, {})

        assert result.probability == pytest.approx(0.75)
        assert result.value == "positive"

    async def test_weighted_voting_requires_matching_weight_count(self):
        members = [_FixedPredictor(_output(0.5, "positive"))]
        with pytest.raises(InvalidEnsembleConfigurationError):
            VotingEnsemblePredictor(
                market_kind=MarketKind.BINARY, members=members, method=EnsembleMethod.WEIGHTED_VOTING, weights=[1.0, 2.0]
            )

    async def test_requires_at_least_one_member(self):
        with pytest.raises(InvalidEnsembleConfigurationError):
            VotingEnsemblePredictor(market_kind=MarketKind.BINARY, members=[])


@dataclass
class _FakeMetaModel:
    feature_order: list[str] = field(default_factory=list)
    _fitted: bool = True
    _result: ModelPrediction = field(
        default_factory=lambda: ModelPrediction(raw_score=0.3, probability=0.65, value="positive")
    )

    def is_fitted(self) -> bool:
        return self._fitted

    def predict_one(self, features: dict[str, float]) -> ModelPrediction:
        return self._result


class TestStackedEnsemblePredictor:
    async def test_predict_delegates_to_meta_model(self):
        members = [
            _FixedPredictor(_output(0.8, "positive", contributions={"x": 1.0})),
            _FixedPredictor(_output(0.4, "negative", contributions={"x": -0.5})),
        ]
        ensemble = StackedEnsemblePredictor(market_kind=MarketKind.BINARY, members=members, meta_model=_FakeMetaModel())

        result = await ensemble.predict(MarketKind.BINARY, {"x": 1.0}, {})

        assert result.probability == 0.65
        assert result.value == "positive"
        assert result.feature_contributions == {"x": pytest.approx(0.25)}

    async def test_unfitted_meta_model_raises(self):
        members = [_FixedPredictor(_output(0.5, "positive"))]
        ensemble = StackedEnsemblePredictor(
            market_kind=MarketKind.BINARY, members=members, meta_model=_FakeMetaModel(_fitted=False)
        )
        with pytest.raises(ModelNotFittedError):
            await ensemble.predict(MarketKind.BINARY, {}, {})

    async def test_requires_at_least_one_member(self):
        with pytest.raises(InvalidEnsembleConfigurationError):
            StackedEnsemblePredictor(market_kind=MarketKind.BINARY, members=[], meta_model=_FakeMetaModel())


class TestDynamicEnsemblePredictor:
    async def test_routes_to_most_reliable_member(self):
        strong = _FixedPredictor(_output(0.9, "positive"))
        weak = _FixedPredictor(_output(0.1, "negative"))
        ensemble = DynamicEnsemblePredictor(
            market_kind=MarketKind.BINARY,
            members={"strong": strong, "weak": weak},
            member_reliability={"strong": 0.9, "weak": 0.2},
        )

        result = await ensemble.predict(MarketKind.BINARY, {}, {})

        assert result.value == "positive"
        assert result.probability == 0.9

    async def test_update_reliability_changes_routing(self):
        first = _FixedPredictor(_output(0.9, "positive"))
        second = _FixedPredictor(_output(0.1, "negative"))
        ensemble = DynamicEnsemblePredictor(
            market_kind=MarketKind.BINARY,
            members={"first": first, "second": second},
            member_reliability={"first": 0.9, "second": 0.2},
        )

        ensemble.update_reliability("second", 0.99)
        result = await ensemble.predict(MarketKind.BINARY, {}, {})

        assert result.value == "negative"

    async def test_update_unknown_member_raises(self):
        ensemble = DynamicEnsemblePredictor(
            market_kind=MarketKind.BINARY, members={"only": _FixedPredictor(_output(0.5, "positive"))}
        )
        with pytest.raises(InvalidEnsembleConfigurationError):
            ensemble.update_reliability("missing", 0.5)

    async def test_requires_at_least_one_member(self):
        with pytest.raises(InvalidEnsembleConfigurationError):
            DynamicEnsemblePredictor(market_kind=MarketKind.BINARY, members={})
