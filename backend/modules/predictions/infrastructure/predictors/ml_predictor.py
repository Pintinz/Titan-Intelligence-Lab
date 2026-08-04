"""`TrainedModelPredictor` — the `PredictorPort` implementation every ML framework adapter runs
behind (Milestone 9.1). `PredictorPort` itself is untouched; this class is the adapter-swap seam
the Milestone 9.1 mandate names: "Prediction Engine interfaces must NEVER change. Only the
predictor implementations may change."

Per-instance ``feature_contributions`` here is a lightweight, honestly-documented approximation —
``feature_value * global_feature_importance`` (the same "value * weight" shape
`WeightedLogisticPredictor`/`WeightedLinearPredictor` already use, with the fitted model's own
global importance standing in for a hand-configured weight). This is *not* a SHAP value: it's
signed by the raw feature value and scaled by the model's global importance, not a true per-
instance marginal contribution. Real per-instance SHAP values are layered on top of this in the
Explainability Engine (Milestone 9.1 SHAP integration, `docs/decisions.md` ADR-051) without this
predictor changing — `PredictorOutput.feature_contributions` keeps serving its existing
top-positive/top-negative ranking role in the meantime.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.ports.ml_model import ModelNotFittedError, PredictionModelPort
from modules.predictions.ports.predictor import PredictorOutput


@dataclass
class TrainedModelPredictor:
    market_kind: MarketKind
    model: PredictionModelPort

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        if not self.model.is_fitted():
            raise ModelNotFittedError(
                "TrainedModelPredictor wraps a model that has not been fit() or deserialize()d yet"
            )
        prediction = self.model.predict_one(features)
        importance = self.model.feature_importance()
        contributions = {key: value * importance.get(key, 0.0) for key, value in features.items()}
        # Every trained-model adapter today is binary-only (`ModelPrediction.value` is
        # "positive"/"negative" for a CLASSIFICATION target, a raw formatted number for
        # REGRESSION — see the four framework adapters' `predict_one()`), so the two-sided split
        # is the whole distribution a trained model can honestly report; a raw-number value means
        # this is a REGRESSION prediction, which has no discrete distribution to report at all.
        distribution = (
            {"positive": prediction.probability, "negative": 1.0 - prediction.probability}
            if prediction.value in ("positive", "negative")
            else {}
        )
        return PredictorOutput(
            raw_score=prediction.raw_score,
            probability=prediction.probability,
            value=prediction.value,
            feature_contributions=contributions,
            distribution=distribution,
        )
