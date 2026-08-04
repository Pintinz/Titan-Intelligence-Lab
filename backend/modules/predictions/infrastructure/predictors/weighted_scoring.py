"""Generic Predictor strategies (Milestone 9 Part 1: "Predictions originate only from engineered
features, historical data, feature store, knowledge graph, validated statistics, approved
feature calculators" — never an LLM).

Three real, documented, deterministic statistical predictors serve every `MarketKind` across all
four sports — the "handful of real predictor classes" the data-driven Market Registry is built
around (docs/decisions.md — data-driven market registry). All three are honestly scoped as v1: a
weighted linear/logistic/ordinal scoring model, not a trained black-box, because no labeled
historical outcome dataset exists yet to fit one (same mock-first/adapter-swap posture as every
other v1 capability in this codebase, ADR-008 — `PredictorPort` is the seam a future trained
model swaps in behind, without touching any consumer).

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
- `WeightedOrdinalPredictor` (Milestone 9.2 Phase 3) serves `HOME_DRAW_AWAY` — genuinely
  three-outcome markets where a draw is a real possibility (football match winner). A single
  sigmoid can only express two outcomes, so relabeling `WeightedLogisticPredictor`'s call onto
  three real labels would mean fabricating which side "draw" silently absorbs. Instead this uses
  an ordinal logistic (proportional-odds) model — the standard, well-established statistical
  construction for turning one continuous score into an ordered N-class distribution — over the
  same weighted-feature `raw_score` the other two predictors already compute.

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
            raw_score=raw_score,
            probability=probability,
            value=value,
            feature_contributions=contributions,
            distribution={"positive": probability, "negative": 1.0 - probability},
        )


@dataclass
class WeightedLinearPredictor:
    """Regression/threshold-shaped predictor: `MarketKind.SPREAD`, `TOTAL`, `TEAM_TOTAL`,
    `PLAYER_PROP`, `RACE_TO`, `CORRECT_SCORE`.

    Audit fix (2026-08-02): every one of these kinds except `CORRECT_SCORE` is genuinely a
    two-sided over/under-style verdict — a positive ``raw_score`` favors the over/covering side,
    per this class's own original docstring — so ``value`` now emits the same generic
    ``"positive"``/``"negative"`` vocabulary `WeightedLogisticPredictor` already uses, letting
    `outcome_label_mapper.map_generic_value_to_real_label` turn it into the market's real label
    (e.g. "OVER"/"UNDER") the same way it already does for `BINARY` markets — previously this
    returned the raw formatted number (e.g. ``"-0.3000"``) as the user-facing verdict, which
    the mapper's "positive"/"negative" check could never match. `CORRECT_SCORE` predicts a
    specific scoreline, not a threshold, so no market in that shape has a real predictor yet —
    it keeps the raw formatted score, an honest placeholder rather than a fabricated label.
    """

    SUPPORTED_KINDS = (
        MarketKind.SPREAD,
        MarketKind.TOTAL,
        MarketKind.TEAM_TOTAL,
        MarketKind.PLAYER_PROP,
        MarketKind.RACE_TO,
        MarketKind.CORRECT_SCORE,
    )
    _RAW_VALUE_KINDS = (MarketKind.CORRECT_SCORE,)
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
        if market_kind in self._RAW_VALUE_KINDS:
            value = f"{raw_score:.4f}"
        else:
            value = "positive" if raw_score >= 0 else "negative"
        return PredictorOutput(
            raw_score=raw_score,
            probability=probability,
            value=value,
            feature_contributions=contributions,
            distribution={"positive": probability, "negative": 1.0 - probability},
        )


@dataclass
class WeightedOrdinalPredictor:
    """Three-outcome predictor: `MarketKind.HOME_DRAW_AWAY`. Ordinal logistic (proportional-odds)
    model with two cutpoints ``away_cutpoint < home_cutpoint`` on the same weighted-feature
    ``raw_score`` the other two predictors compute:

    - P(raw_score falls at/below away_cutpoint) = sigmoid(away_cutpoint - raw_score) = P(AWAY_WIN)
    - P(raw_score falls at/below home_cutpoint) = sigmoid(home_cutpoint - raw_score) = P(AWAY_WIN or DRAW)
    - P(HOME_WIN) = 1 - P(at/below home_cutpoint)
    - P(DRAW) = P(at/below home_cutpoint) - P(at/below away_cutpoint)

    This CDF-differencing construction guarantees all three probabilities are non-negative and
    sum to exactly 1 by construction — no post-hoc normalization needed. The two cutpoints are a
    v1 heuristic default (same "no fitted model yet" honesty as the other two predictors here),
    not derived from any historical dataset — override them once real training data exists to fit
    a proper ordinal regression.
    """

    SUPPORTED_KINDS = (MarketKind.HOME_DRAW_AWAY,)
    market_kind: MarketKind = MarketKind.HOME_DRAW_AWAY
    # Symmetric cutpoints must exceed ln(2) ≈ 0.693 in magnitude for DRAW to be able to win the
    # plurality at raw_score == 0 at all — with a narrower gap the middle class is mathematically
    # dominated by both sides even for a perfectly even matchup, which doesn't reflect how often
    # real football matches actually draw (~25-30%). 0.85 leaves a real, non-degenerate draw
    # region around a balanced raw_score without needing a fitted model to choose it.
    away_cutpoint: float = -0.85
    home_cutpoint: float = 0.85

    def __post_init__(self) -> None:
        if self.away_cutpoint >= self.home_cutpoint:
            raise ValueError("away_cutpoint must be strictly less than home_cutpoint")

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        if market_kind not in self.SUPPORTED_KINDS:
            raise UnsupportedMarketKindError(
                f"WeightedOrdinalPredictor does not support market_kind '{market_kind.value}'"
            )

        contributions = _weighted_contributions(features, mapping_weights)
        raw_score = sum(contributions.values())

        p_at_or_below_away = _sigmoid(self.away_cutpoint - raw_score)
        p_at_or_below_home = _sigmoid(self.home_cutpoint - raw_score)
        p_away = p_at_or_below_away
        p_draw = p_at_or_below_home - p_at_or_below_away
        p_home = 1.0 - p_at_or_below_home

        outcomes = {"AWAY_WIN": p_away, "DRAW": p_draw, "HOME_WIN": p_home}
        value = max(outcomes, key=outcomes.get)
        probability = outcomes[value]

        return PredictorOutput(
            raw_score=raw_score,
            probability=probability,
            value=value,
            feature_contributions=contributions,
            distribution=outcomes,
        )
