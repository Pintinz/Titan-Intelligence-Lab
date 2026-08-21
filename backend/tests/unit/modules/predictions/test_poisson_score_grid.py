"""Tests for `poisson_score_grid` — pure Poisson-derived `match_winner`/`both_teams_to_score`
math, reused from an already-fitted `correct_score` Poisson model's lam_home/lam_away (see module
docstring). Verified against hand-computable/known properties, not just "runs without error."
"""

from __future__ import annotations

from modules.predictions.domain.poisson_score_grid import (
    both_teams_to_score_probabilities,
    match_winner_probabilities,
    score_grid,
)


class TestScoreGrid:
    def test_grid_sums_to_approximately_one(self):
        grid = score_grid(1.4, 1.1, max_goals=15)
        assert abs(sum(grid.values()) - 1.0) < 1e-6

    def test_grid_has_every_combination_up_to_max_goals(self):
        grid = score_grid(1.0, 1.0, max_goals=3)
        assert len(grid) == 16  # (3+1) * (3+1)
        assert (0, 0) in grid
        assert (3, 3) in grid

    def test_higher_lambda_side_gets_more_mass_at_higher_scores(self):
        grid = score_grid(3.0, 0.3, max_goals=10)
        # a team with lam=3.0 scoring exactly 3 should be far more likely than a lam=0.3 team doing so
        assert grid[(3, 0)] > grid[(0, 3)]


class TestMatchWinnerProbabilities:
    def test_probabilities_sum_to_one(self):
        probs = match_winner_probabilities(1.6, 1.1)
        assert abs(sum(probs.values()) - 1.0) < 1e-9

    def test_uses_market_outcome_catalog_labels(self):
        probs = match_winner_probabilities(1.6, 1.1)
        assert set(probs.keys()) == {"HOME_WIN", "DRAW", "AWAY_WIN"}

    def test_stronger_home_side_favors_home_win(self):
        probs = match_winner_probabilities(2.5, 0.8)
        assert probs["HOME_WIN"] > probs["AWAY_WIN"]
        assert probs["HOME_WIN"] > probs["DRAW"]

    def test_symmetric_lambdas_give_equal_home_away_probability(self):
        probs = match_winner_probabilities(1.3, 1.3)
        assert abs(probs["HOME_WIN"] - probs["AWAY_WIN"]) < 1e-9

    def test_all_probabilities_non_negative(self):
        probs = match_winner_probabilities(0.01, 0.01)
        assert all(p >= 0.0 for p in probs.values())


class TestBothTeamsToScoreProbabilities:
    def test_probabilities_sum_to_one(self):
        probs = both_teams_to_score_probabilities(1.4, 1.2)
        assert abs(probs["YES"] + probs["NO"] - 1.0) < 1e-9

    def test_uses_market_outcome_catalog_labels(self):
        probs = both_teams_to_score_probabilities(1.4, 1.2)
        assert set(probs.keys()) == {"YES", "NO"}

    def test_near_zero_lambda_makes_yes_unlikely(self):
        probs = both_teams_to_score_probabilities(0.01, 1.5)
        assert probs["YES"] < 0.05

    def test_high_lambdas_make_yes_likely(self):
        probs = both_teams_to_score_probabilities(2.5, 2.2)
        assert probs["YES"] > 0.8

    def test_matches_closed_form_independence_formula(self):
        lam_home, lam_away = 1.7, 0.9
        probs = both_teams_to_score_probabilities(lam_home, lam_away)
        import math

        p_home_zero = math.exp(-lam_home)
        p_away_zero = math.exp(-lam_away)
        expected_yes = (1 - p_home_zero) * (1 - p_away_zero)
        assert abs(probs["YES"] - expected_yes) < 1e-9
