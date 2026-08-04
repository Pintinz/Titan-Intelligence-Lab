"""Ensemble Learning (Milestone 9.1). Every ensemble here is itself a `PredictorPort`
implementation combining other `PredictorPort` members — the same seam `TrainedModelPredictor`
and the weighted predictors already use, so an ensemble slots into `PredictorRegistry` exactly
like any single predictor, no new integration point (`PredictionEngine`/`PredictorPort` stay
completely unchanged). Members may themselves be `TrainedModelPredictor`s wrapping different
frameworks, weighted predictors, or other ensembles — nothing here is framework-specific.

"Sport-specific"/"market-specific" ensembles (Milestone 9.1 spec) aren't a distinct class: which
members compose an ensemble, and for which market, is decided by composition wiring
(`register_for_market` on `PredictorRegistry`) — an ensemble registered for
``football.match_result`` is football-specific purely because of *what* it was built from.

Six methods, three real inference-time shapes:
- `VotingEnsemblePredictor` (`SOFT_VOTING`/`HARD_VOTING`/`WEIGHTED_VOTING`) — combines member
  outputs directly, no fitting required.
- `StackedEnsemblePredictor` (`STACKING`/`BLENDING`) — a fitted meta-`PredictionModelPort` learns
  how to combine member probabilities. The two methods are inference-time identical; they differ
  only in how the meta-model was *fit* (k-fold out-of-fold predictions for stacking, a single
  held-out blend split for blending) — a Training Platform concern, not this class's.
- `DynamicEnsemblePredictor` (`DYNAMIC`) — Dynamic Ensemble Selection: routes to whichever member
  currently has the best tracked reliability score, rather than combining every member every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.predictions.domain.ml_value_objects import EnsembleMethod
from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.ports.ml_model import ModelNotFittedError, PredictionModelPort
from modules.predictions.ports.predictor import PredictorOutput, PredictorPort

_CLASSIFICATION_VALUES = {"positive", "negative"}


class InvalidEnsembleConfigurationError(ValueError):
    pass


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _binary_distribution(value: str, probability: float) -> dict[str, float]:
    """Same two-sided split every other binary-shaped predictor reports — empty for a
    non-classification ``value`` (e.g. a raw regression number), same convention as
    `TrainedModelPredictor`."""
    if value not in _CLASSIFICATION_VALUES:
        return {}
    return {"positive": probability, "negative": 1.0 - probability}


@dataclass
class VotingEnsemblePredictor:
    market_kind: MarketKind
    members: list[PredictorPort]
    method: EnsembleMethod = EnsembleMethod.SOFT_VOTING
    weights: list[float] | None = None

    def __post_init__(self) -> None:
        if not self.members:
            raise InvalidEnsembleConfigurationError("VotingEnsemblePredictor requires at least one member")
        if self.method is EnsembleMethod.WEIGHTED_VOTING:
            if self.weights is None or len(self.weights) != len(self.members):
                raise InvalidEnsembleConfigurationError(
                    "WEIGHTED_VOTING requires one weight per member"
                )

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        outputs = [await member.predict(market_kind, features, mapping_weights) for member in self.members]

        if self.method is EnsembleMethod.HARD_VOTING:
            return self._hard_vote(outputs)
        if self.method is EnsembleMethod.WEIGHTED_VOTING:
            return self._weighted_vote(outputs)
        return self._soft_vote(outputs)

    def _soft_vote(self, outputs: list[PredictorOutput]) -> PredictorOutput:
        n = len(outputs)
        probability = _clamp(sum(o.probability for o in outputs) / n)
        raw_score = sum(o.raw_score for o in outputs) / n
        value = outputs[0].value if self._all_agree(outputs) else self._majority_value(outputs)
        return PredictorOutput(
            raw_score=raw_score,
            probability=probability,
            value=value,
            feature_contributions=self._average_contributions(outputs, [1.0] * n),
            distribution=_binary_distribution(value, probability),
        )

    def _weighted_vote(self, outputs: list[PredictorOutput]) -> PredictorOutput:
        total_weight = sum(self.weights) or 1.0
        normalized = [w / total_weight for w in self.weights]
        probability = _clamp(sum(o.probability * w for o, w in zip(outputs, normalized)))
        raw_score = sum(o.raw_score * w for o, w in zip(outputs, normalized))
        value = self._majority_value(outputs, self.weights)
        return PredictorOutput(
            raw_score=raw_score,
            probability=probability,
            value=value,
            feature_contributions=self._average_contributions(outputs, normalized),
            distribution=_binary_distribution(value, probability),
        )

    def _hard_vote(self, outputs: list[PredictorOutput]) -> PredictorOutput:
        majority_value = self._majority_value(outputs)
        agreeing = [o for o in outputs if o.value == majority_value]
        probability = _clamp(len(agreeing) / len(outputs))
        raw_score = sum(o.raw_score for o in agreeing) / len(agreeing)
        return PredictorOutput(
            raw_score=raw_score,
            probability=probability,
            value=majority_value,
            feature_contributions=self._average_contributions(agreeing, [1.0] * len(agreeing)),
            distribution=_binary_distribution(majority_value, probability),
        )

    def _all_agree(self, outputs: list[PredictorOutput]) -> bool:
        return len({o.value for o in outputs}) == 1

    def _majority_value(self, outputs: list[PredictorOutput], weights: list[float] | None = None) -> str:
        tallies: dict[str, float] = {}
        for i, output in enumerate(outputs):
            tallies[output.value] = tallies.get(output.value, 0.0) + (weights[i] if weights else 1.0)
        return max(tallies, key=tallies.get)

    def _average_contributions(self, outputs: list[PredictorOutput], weights: list[float]) -> dict[str, float]:
        total_weight = sum(weights) or 1.0
        combined: dict[str, float] = {}
        for output, weight in zip(outputs, weights):
            for key, value in output.feature_contributions.items():
                combined[key] = combined.get(key, 0.0) + value * weight
        return {key: value / total_weight for key, value in combined.items()}


@dataclass
class StackedEnsemblePredictor:
    """`STACKING`/`BLENDING` — a fitted meta-`PredictionModelPort` combines base member
    probabilities. ``meta_model.feature_order`` must equal the member names used as its training
    columns (``member_<i>`` by position), set when the meta-model was fit."""

    market_kind: MarketKind
    members: list[PredictorPort]
    meta_model: PredictionModelPort
    method: EnsembleMethod = EnsembleMethod.STACKING

    def __post_init__(self) -> None:
        if not self.members:
            raise InvalidEnsembleConfigurationError("StackedEnsemblePredictor requires at least one member")

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        if not self.meta_model.is_fitted():
            raise ModelNotFittedError("StackedEnsemblePredictor's meta_model has not been fit()/deserialize()d yet")

        outputs = [await member.predict(market_kind, features, mapping_weights) for member in self.members]
        meta_features = {f"member_{i}": output.probability for i, output in enumerate(outputs)}

        meta_prediction = self.meta_model.predict_one(meta_features)
        combined_contributions: dict[str, float] = {}
        for output in outputs:
            for key, value in output.feature_contributions.items():
                combined_contributions[key] = combined_contributions.get(key, 0.0) + value / len(outputs)

        return PredictorOutput(
            raw_score=meta_prediction.raw_score,
            probability=meta_prediction.probability,
            value=meta_prediction.value,
            feature_contributions=combined_contributions,
            distribution=_binary_distribution(meta_prediction.value, meta_prediction.probability),
        )


@dataclass
class DynamicEnsemblePredictor:
    """`DYNAMIC` — Dynamic Ensemble Selection: routes every prediction to whichever named member
    currently has the highest tracked reliability score, rather than combining all members every
    time. ``member_reliability`` is expected to be refreshed as new `PredictionOutcome` history
    accumulates per member (Model Monitoring's job, Milestone 9.1 task #167) — this class only
    reads whatever score it's handed at construction/update time."""

    market_kind: MarketKind
    members: dict[str, PredictorPort]
    member_reliability: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.members:
            raise InvalidEnsembleConfigurationError("DynamicEnsemblePredictor requires at least one member")
        for name in self.members:
            self.member_reliability.setdefault(name, 0.5)

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        best_name = max(self.member_reliability, key=self.member_reliability.get)
        return await self.members[best_name].predict(market_kind, features, mapping_weights)

    def update_reliability(self, name: str, score: float) -> None:
        if name not in self.members:
            raise InvalidEnsembleConfigurationError(f"'{name}' is not a registered member")
        self.member_reliability[name] = _clamp(score)
