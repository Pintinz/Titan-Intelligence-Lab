"""Correct-score predictor (audit fix 2026-08-02): `MarketKind.CORRECT_SCORE` was previously
served by `WeightedLinearPredictor`, whose ``value`` is a raw regression-number string — a
scoreline market has no meaningful "over/under a threshold" interpretation, so that number was
never a real verdict, just a formatted placeholder (see weighted_scoring.py's docstring).

Models home and away goals as independent Poisson processes with rates (``lambda_home``,
``lambda_away``) taken directly from the resolved feature snapshot —
`FixtureExpectedGoalsCalculator`'s real historical scoring rates
(`windowed_feature_engineering_service.py`), not a fitted joint model (no labeled historical
correct-score outcome dataset exists yet — the same "honest v1, no fitted model" posture the two
weighted-scoring predictors already carry). Treating the two sides' goals as independent is the
standard simplifying assumption real correct-score models start from (the well-known refinement,
Dixon-Coles, adds a low-score correlation correction on top of exactly this base model) — a real,
documented statistical technique, not an invented heuristic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.ports.predictor import PredictorOutput

_MIN_LAMBDA = 1e-6


class UnsupportedMarketKindError(ValueError):
    pass


class MissingExpectedGoalsFeatureError(KeyError):
    pass


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam**k) / math.factorial(k)


@dataclass
class PoissonScorePredictor:
    SUPPORTED_KINDS = (MarketKind.CORRECT_SCORE,)
    market_kind: MarketKind = MarketKind.CORRECT_SCORE
    home_feature_key: str = "football.fixture.expected_home_goals"
    away_feature_key: str = "football.fixture.expected_away_goals"
    # Covers the realistic range of top-flight football scorelines without an unbounded (and
    # mostly-zero-probability) grid — a joint probability beyond 6-6 is negligible for any
    # realistic lambda and would only add wasted computation. Used to search for the single most
    # likely scoreline (`value`/`probability`) — a slightly wider net than the distribution grid
    # below, so a genuinely lopsided lambda pair can still surface its true mode.
    max_goals: int = 6
    # The Top-N distribution grid this predictor reports (Universal Probability Engine,
    # 2026-08-02) — matches `market_outcome_registry._correct_score_grid`'s own `max_goals=5`
    # exactly, so `distribution`'s keys are always a subset of the market's real `allowed_values`.
    # Any joint mass outside this grid (either side scoring 6+) is folded into "OTHER", computed
    # analytically from the two independent Poisson marginals rather than approximated by
    # widening the grid — exact, not a truncation artifact.
    distribution_max_goals: int = 5

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        if market_kind not in self.SUPPORTED_KINDS:
            raise UnsupportedMarketKindError(
                f"PoissonScorePredictor does not support market_kind '{market_kind.value}'"
            )
        if self.home_feature_key not in features or self.away_feature_key not in features:
            raise MissingExpectedGoalsFeatureError(
                f"PoissonScorePredictor requires both '{self.home_feature_key}' and "
                f"'{self.away_feature_key}' in the resolved feature snapshot"
            )

        lambda_home = max(features[self.home_feature_key] * mapping_weights.get(self.home_feature_key, 1.0), _MIN_LAMBDA)
        lambda_away = max(features[self.away_feature_key] * mapping_weights.get(self.away_feature_key, 1.0), _MIN_LAMBDA)

        best_score = (0, 0)
        best_probability = -1.0
        for home_goals in range(self.max_goals + 1):
            p_home = _poisson_pmf(home_goals, lambda_home)
            for away_goals in range(self.max_goals + 1):
                probability = p_home * _poisson_pmf(away_goals, lambda_away)
                if probability > best_probability:
                    best_probability = probability
                    best_score = (home_goals, away_goals)

        value = f"{best_score[0]}-{best_score[1]}"
        contributions = {self.home_feature_key: lambda_home, self.away_feature_key: lambda_away}
        distribution = self._grid_distribution(lambda_home, lambda_away)
        return PredictorOutput(
            raw_score=lambda_home - lambda_away,
            probability=best_probability,
            value=value,
            feature_contributions=contributions,
            distribution=distribution,
        )

    def _grid_distribution(self, lambda_home: float, lambda_away: float) -> dict[str, float]:
        """The Top-N scoreline distribution (Universal Probability Engine) — every scoreline in
        `distribution_max_goals`'s grid keyed exactly like `market_outcome_registry._correct_score_grid`,
        plus an analytically-exact "OTHER" bucket for the joint mass outside it. Because home/away
        goals are modeled as independent Poisson processes, the grid's total mass factors as
        ``P(home <= N) * P(away <= N)`` — no need to widen the grid to bound the remainder."""
        home_pmf = [_poisson_pmf(k, lambda_home) for k in range(self.distribution_max_goals + 1)]
        away_pmf = [_poisson_pmf(k, lambda_away) for k in range(self.distribution_max_goals + 1)]
        distribution = {
            f"{home}-{away}": home_pmf[home] * away_pmf[away]
            for home in range(self.distribution_max_goals + 1)
            for away in range(self.distribution_max_goals + 1)
        }
        grid_mass = sum(home_pmf) * sum(away_pmf)
        distribution["OTHER"] = max(0.0, 1.0 - grid_mass)
        return distribution
