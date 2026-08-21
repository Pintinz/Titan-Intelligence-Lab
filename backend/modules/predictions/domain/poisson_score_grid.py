"""Gemini Prediction Reasoning Engine — statistical-baseline charter, live wiring.

Derives `football.match_winner`/`football.both_teams_to_score` probabilities from a pair of
already-fitted Poisson goal-rate parameters (`lam_home`/`lam_away`) — the same `lam_home`/
`lam_away` `FootballGoalsPoissonAdapter.predict_one()` computes internally for its own
`correct_score` market shape (see that module). This is deliberately NOT a new trained model: no
market_winner/BTTS-specific `PoissonRegressor` is fit anywhere — the two goal-rate regressors
already fitted for `football.correct_score` fully determine the home/away goal distribution for
any fixture, and match_winner/BTTS are standard closed-form (independent-Poisson) derivations of
that same distribution. `StatisticalBaselineProvider` only calls this when a real, trained
`correct_score` Poisson model is available for the fixture's features; there is no "derive
without a fit" path.

Pure domain math — no infrastructure/ML-adapter imports, so this stays reusable (and testable in
isolation) independent of how `lam_home`/`lam_away` were obtained.
"""

from __future__ import annotations

import math

_DEFAULT_MAX_GOALS = 10


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for X ~ Poisson(lam), floored at a tiny positive `lam` for the same degenerate-fit
    guard `FootballGoalsPoissonAdapter._poisson_pmf` uses."""
    lam = max(lam, 1e-9)
    return math.exp(-lam) * lam**k / math.factorial(k)


def score_grid(lam_home: float, lam_away: float, max_goals: int = _DEFAULT_MAX_GOALS) -> dict[tuple[int, int], float]:
    """The bounded joint (home_goals, away_goals) probability grid under the independent-Poisson
    assumption — the same assumption `FootballGoalsPoissonAdapter`'s own `win_to_nil`/`clean_sheet`
    shapes already make. `max_goals=10` captures effectively all real probability mass for
    football-realistic lambda values (typically well under 4); any residual tail is handled by
    `match_winner_probabilities`'s renormalization, never silently dropped."""
    return {
        (home, away): _poisson_pmf(home, lam_home) * _poisson_pmf(away, lam_away)
        for home in range(max_goals + 1)
        for away in range(max_goals + 1)
    }


def match_winner_probabilities(
    lam_home: float, lam_away: float, max_goals: int = _DEFAULT_MAX_GOALS
) -> dict[str, float]:
    """`{"HOME_WIN": ..., "DRAW": ..., "AWAY_WIN": ...}` — matches `football.match_winner`'s
    `MARKET_OUTCOME_CATALOG` label contract exactly. Renormalized over the bounded grid so the
    three probabilities always sum to 1.0 (the grid's own truncation tail, not a fabricated
    adjustment) rather than quietly summing to slightly less than 1."""
    grid = score_grid(lam_home, lam_away, max_goals)
    home = sum(p for (h, a), p in grid.items() if h > a)
    draw = sum(p for (h, a), p in grid.items() if h == a)
    away = sum(p for (h, a), p in grid.items() if h < a)
    total = home + draw + away
    if total <= 0:
        return {"HOME_WIN": 0.0, "DRAW": 0.0, "AWAY_WIN": 0.0}
    return {"HOME_WIN": home / total, "DRAW": draw / total, "AWAY_WIN": away / total}


def both_teams_to_score_probabilities(lam_home: float, lam_away: float) -> dict[str, float]:
    """`{"YES": ..., "NO": ...}` — matches `football.both_teams_to_score`'s label contract. Closed
    form under independence: both teams score iff neither is held to zero, so
    `P(YES) = (1 - P(home=0)) * (1 - P(away=0))` — no grid summation needed."""
    p_home_scores = 1.0 - _poisson_pmf(0, lam_home)
    p_away_scores = 1.0 - _poisson_pmf(0, lam_away)
    p_yes = max(0.0, min(1.0, p_home_scores * p_away_scores))
    return {"YES": p_yes, "NO": 1.0 - p_yes}
