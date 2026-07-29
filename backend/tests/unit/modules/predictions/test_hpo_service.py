from __future__ import annotations

import pytest

from modules.predictions.application.hpo_service import InvalidParamSpaceError, optimize
from modules.predictions.domain.validation import HPOStrategy


async def _objective(params: dict, budget_fraction: float) -> float:
    """A simple deterministic objective — higher ``x`` is always better, so the optimum is
    unambiguous and every strategy's ``best_params`` can be asserted precisely. ``budget_fraction``
    is accepted (SUCCESSIVE_HALVING passes it) but doesn't change the score, since correctness of
    *that* budget-scaling behavior is exercised by `test_successive_halving_*` below instead."""
    return float(params["x"])


class TestOptimize:
    async def test_grid_search_finds_the_maximum(self):
        result = await optimize({"x": [1, 5, 3]}, _objective, HPOStrategy.GRID_SEARCH)
        assert result.best_params == {"x": 5}
        assert result.best_metric_value == 5.0
        assert len(result.trials) == 3

    async def test_random_search_respects_n_trials(self):
        result = await optimize({"x": (0.0, 10.0)}, _objective, HPOStrategy.RANDOM_SEARCH, n_trials=15, seed=1)
        assert len(result.trials) == 15
        assert 0.0 <= result.best_metric_value <= 10.0

    async def test_random_search_is_reproducible_with_same_seed(self):
        first = await optimize({"x": (0.0, 10.0)}, _objective, HPOStrategy.RANDOM_SEARCH, n_trials=10, seed=7)
        second = await optimize({"x": (0.0, 10.0)}, _objective, HPOStrategy.RANDOM_SEARCH, n_trials=10, seed=7)
        assert [t.params for t in first.trials] == [t.params for t in second.trials]

    async def test_successive_halving_narrows_to_fewer_trials_over_rungs(self):
        result = await optimize(
            {"x": (0.0, 10.0)}, _objective, HPOStrategy.SUCCESSIVE_HALVING, n_candidates=9, seed=3
        )
        assert result.best_metric_value <= 10.0
        assert len(result.trials) >= 9  # at least the first rung ran for every candidate

    async def test_bayesian_optimization_returns_best_params(self):
        result = await optimize(
            {"x": (0.0, 10.0)}, _objective, HPOStrategy.BAYESIAN_OPTIMIZATION, n_trials=8, seed=2
        )
        assert len(result.trials) == 8
        assert result.best_metric_value == max(t.metric_value for t in result.trials)

    async def test_optuna_strategy_accepts_a_custom_sampler(self):
        import optuna

        result = await optimize(
            {"x": (0.0, 10.0)},
            _objective,
            HPOStrategy.OPTUNA,
            n_trials=6,
            sampler=optuna.samplers.RandomSampler(seed=9),
        )
        assert len(result.trials) == 6

    async def test_grid_search_rejects_continuous_param_space(self):
        with pytest.raises(InvalidParamSpaceError):
            await optimize({"x": (0.0, 1.0)}, _objective, HPOStrategy.GRID_SEARCH)

    async def test_empty_param_space_raises(self):
        with pytest.raises(InvalidParamSpaceError):
            await optimize({}, _objective, HPOStrategy.RANDOM_SEARCH)

    async def test_integer_param_space_samples_integers(self):
        async def int_objective(params, budget_fraction):
            assert isinstance(params["k"], int)
            return float(params["k"])

        result = await optimize({"k": (1, 10)}, int_objective, HPOStrategy.RANDOM_SEARCH, n_trials=5, seed=4)
        assert all(isinstance(t.params["k"], int) for t in result.trials)
