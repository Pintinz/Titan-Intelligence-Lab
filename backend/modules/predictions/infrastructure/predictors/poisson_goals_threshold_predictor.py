"""Poisson goals-threshold predictor (audit fix 2026-08-03).

Live-verifying the Universal Probability Engine work surfaced a real, pre-existing bug: eleven
markets — every total-goals line (`football.total_goals_over_under*`), both team-total-goals
markets, both clean-sheet markets, and both win-to-nil markets — all mapped the exact same
`required_features` (the fixture-form stat differentials) with the exact same weights, to the
same generic `WeightedLogisticPredictor`/`WeightedLinearPredictor`. Since none of those features
encode *which line* or *which side* a specific market actually asks about, every one of them
produced a byte-identical probability regardless of whether the line was 0.5 or 4.5 goals, or
whether the market was "Home Clean Sheet" or "Away Win To Nil" — a real correctness bug a user
would notice immediately comparing markets side by side, not a fabricated one.

The fix reuses the real signal `FixtureExpectedGoalsCalculator` already computes for
`football.correct_score` (`football.fixture.expected_home_goals`/`expected_away_goals` — each
side's own historical scoring rate) and derives each market's real answer from the same
independent-Poisson model `PoissonScorePredictor` already uses, via standard closed-form Poisson
results — no new data, no invented heuristic:

- **Total goals over/under a line**: the sum of two independent Poisson variables is itself
  Poisson with rate ``lambda_home + lambda_away`` (a standard, well-known result) — so
  P(total > line) = 1 - PoissonCDF(floor(line), lambda_home + lambda_away).
- **Team total goals over/under a line**: P(team_goals > line) = 1 - PoissonCDF(floor(line),
  lambda_team) directly from that side's own rate.
- **Clean sheet** (a side concedes zero): P(opponent scores 0) = PoissonPMF(0, lambda_opponent).
- **Win to nil** (a side wins without conceding): the two events are independent under this
  model, so P(opponent scores 0 AND this side scores >= 1) = PoissonPMF(0, lambda_opponent) *
  (1 - PoissonPMF(0, lambda_side)).

One predictor instance is registered per affected market_key (`PredictorRegistry.register_for_market`,
not by `MarketKind` — `MarketKind.BINARY`/`TOTAL`/`TEAM_TOTAL` are also used by markets that
correctly stay on the generic weighted predictors, e.g. `football.both_teams_to_score`), each
configured with that market's own `line`/`side`/`mode` at composition time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.ports.predictor import PredictorOutput

_MIN_LAMBDA = 1e-6


class UnsupportedMarketKindError(ValueError):
    pass


class MissingExpectedGoalsFeatureError(KeyError):
    pass


class PoissonGoalsThresholdMode(str, Enum):
    TOTAL_OVER_UNDER = "total_over_under"  # home_goals + away_goals vs. a line
    TEAM_TOTAL_OVER_UNDER = "team_total_over_under"  # one side's own goals vs. a line
    CLEAN_SHEET = "clean_sheet"  # the opponent scores zero
    WIN_TO_NIL = "win_to_nil"  # this side wins and the opponent scores zero


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def _poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) for X ~ Poisson(lam), k >= 0."""
    return sum(_poisson_pmf(i, lam) for i in range(k + 1))


@dataclass
class PoissonGoalsThresholdPredictor:
    market_kind: MarketKind
    mode: PoissonGoalsThresholdMode
    home_feature_key: str = "football.fixture.expected_home_goals"
    away_feature_key: str = "football.fixture.expected_away_goals"
    line: float = 2.5  # threshold for the two OVER_UNDER modes; unused otherwise
    side: str = "home"  # "home" or "away" — which side TEAM_TOTAL_OVER_UNDER/CLEAN_SHEET/WIN_TO_NIL is about

    def __post_init__(self) -> None:
        if self.side not in ("home", "away"):
            raise ValueError(f"side must be 'home' or 'away', got {self.side!r}")

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        if market_kind is not self.market_kind:
            raise UnsupportedMarketKindError(
                f"PoissonGoalsThresholdPredictor configured for '{self.market_kind.value}', got '{market_kind.value}'"
            )
        if self.home_feature_key not in features or self.away_feature_key not in features:
            raise MissingExpectedGoalsFeatureError(
                f"PoissonGoalsThresholdPredictor requires both '{self.home_feature_key}' and "
                f"'{self.away_feature_key}' in the resolved feature snapshot"
            )

        lambda_home = max(features[self.home_feature_key] * mapping_weights.get(self.home_feature_key, 1.0), _MIN_LAMBDA)
        lambda_away = max(features[self.away_feature_key] * mapping_weights.get(self.away_feature_key, 1.0), _MIN_LAMBDA)
        lambda_side = lambda_home if self.side == "home" else lambda_away
        lambda_opponent = lambda_away if self.side == "home" else lambda_home

        p_positive = self._p_positive(lambda_home, lambda_away, lambda_side, lambda_opponent)
        value = "positive" if p_positive >= 0.5 else "negative"

        return PredictorOutput(
            raw_score=p_positive - 0.5,
            probability=p_positive,
            value=value,
            feature_contributions={self.home_feature_key: lambda_home, self.away_feature_key: lambda_away},
            distribution={"positive": p_positive, "negative": 1.0 - p_positive},
        )

    def _p_positive(self, lambda_home: float, lambda_away: float, lambda_side: float, lambda_opponent: float) -> float:
        floor_line = math.floor(self.line)
        if self.mode is PoissonGoalsThresholdMode.TOTAL_OVER_UNDER:
            # Sum of two independent Poisson(lambda) variables is Poisson(lambda_home + lambda_away).
            return 1.0 - _poisson_cdf(floor_line, lambda_home + lambda_away)
        if self.mode is PoissonGoalsThresholdMode.TEAM_TOTAL_OVER_UNDER:
            return 1.0 - _poisson_cdf(floor_line, lambda_side)
        if self.mode is PoissonGoalsThresholdMode.CLEAN_SHEET:
            return _poisson_pmf(0, lambda_opponent)
        if self.mode is PoissonGoalsThresholdMode.WIN_TO_NIL:
            return _poisson_pmf(0, lambda_opponent) * (1.0 - _poisson_pmf(0, lambda_side))
        raise AssertionError(f"unhandled mode {self.mode!r}")  # pragma: no cover — exhaustive Enum
