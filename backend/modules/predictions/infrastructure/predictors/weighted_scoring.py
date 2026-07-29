"""Generic Predictor strategies (Milestone 9 Part 1: "Predictions originate only from engineered
features, historical data, feature store, knowledge graph, validated statistics, approved
feature calculators" — never an LLM).

Two real, documented, deterministic statistical predictors serve every `MarketKind` across all
four sports — the "handful of real predictor classes" the data-driven Market Registry is built
around (docs/decisions.md — data-driven market registry). Both are honestly scoped as v1: a
weighted linear/logistic scoring model, not a trained black-box, because no labeled historical
outcome dataset exists yet to fit one (same mock-first/adapter-swap posture as every other v1
capability in this codebase, ADR-008 — `PredictorPort` is the seam a future trained model swaps
in behind, without touching any consumer).

- `WeightedLogisticPredictor` serves classification-shaped kinds (`BINARY`, `SEGMENT_WINNER`):
  ``raw_score`` is the weighted sum of the resolved feature snapshot, ``probability`` is its
  logistic (sigmoid) transform. ``value`` is the generic two-sided label "positive"/"negative" —
  mapping that onto a market's real outcome labels (e.g. "home_win"/"away_win") is the
  per-sport market registration's job (Milestone 9 Part 3), not the predictor's.
- `WeightedLinearPredictor` serves regression/threshold-shaped kinds (`SPREAD`, `TOTAL`,
  `TEAM_TOTAL`, `PLAYER_PROP`, `RACE_TO`, `CORRECT_SCORE`): ``raw_score`` IS the continuous
  predicted value (e.g. predicted total points). Its ``probability`` assumes the market's feature
  engineering has already centered inputs around the market's line/threshold (so a positive
  ``raw_score`` favors the "over"/covering side) — that centering is the per-sport feature
  calculator's responsibility (Milestone 9 Parts 3/tasks #136-141), not this predictor's.

Every feature contribution reported is signed and directly summable to ``raw_score`` — the exact
shape the Explainability Engine (Part 4) needs to rank top positive/negative features without
re-deriving anything.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.ports.predictor import PredictorOutput


def _sigmoid(x: float) -> float:
    # Split form avoids overflow in math.exp() for large-magnitude raw scores.
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _weighted_contributions(features: dict[str, float], mapping_weights: dict[str, float]) -> dict[str, float]:
    return {key: value * mapping_weights.get(key, 1.0) for key, value in features.items()}


class UnsupportedMarketKindError(ValueError):
    pass


@dataclass
class WeightedLogisticPredictor:
    """Classification-shaped predictor: `MarketKind.BINARY`, `MarketKind.SEGMENT_WINNER`."""

    SUPPORTED_KINDS = (MarketKind.BINARY, MarketKind.SEGMENT_WINNER)
    market_kind: MarketKind = MarketKind.BINARY

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        if market_kind not in self.SUPPORTED_KINDS:
            raise UnsupportedMarketKindError(
                f"WeightedLogisticPredictor does not support market_kind '{market_kind.value}'"
            )

        contributions = _weighted_contributions(features, mapping_weights)
        raw_score = sum(contributions.values())
        probability = _sigmoid(raw_score)
        value = "positive" if probability >= 0.5 else "negative"
        return PredictorOutput(
            raw_score=raw_score, probability=probability, value=value, feature_contributions=contributions
        )


@dataclass
class WeightedLinearPredictor:
    """Regression/threshold-shaped predictor: `MarketKind.SPREAD`, `TOTAL`, `TEAM_TOTAL`,
    `PLAYER_PROP`, `RACE_TO`, `CORRECT_SCORE`."""

    SUPPORTED_KINDS = (
        MarketKind.SPREAD,
        MarketKind.TOTAL,
        MarketKind.TEAM_TOTAL,
        MarketKind.PLAYER_PROP,
        MarketKind.RACE_TO,
        MarketKind.CORRECT_SCORE,
    )
    market_kind: MarketKind = MarketKind.TOTAL

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        if market_kind not in self.SUPPORTED_KINDS:
            raise UnsupportedMarketKindError(
                f"WeightedLinearPredictor does not support market_kind '{market_kind.value}'"
            )

        contributions = _weighted_contributions(features, mapping_weights)
        raw_score = sum(contributions.values())
        probability = _sigmoid(raw_score)
        value = f"{raw_score:.4f}"
        return PredictorOutput(
            raw_score=raw_score, probability=probability, value=value, feature_contributions=contributions
        )
