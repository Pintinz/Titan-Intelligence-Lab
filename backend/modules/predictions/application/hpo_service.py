"""Hyperparameter Optimization (Milestone 9.1) — 5 strategies over a caller-supplied ``objective``
callable, ``async def objective(params: dict, budget_fraction: float) -> float`` (higher is
better; ``budget_fraction`` in ``(0, 1]`` lets `SUCCESSIVE_HALVING` request a cheaper partial
evaluation — e.g. fewer boosting rounds or a training-sample subset — the objective's own
business, not this module's). Every strategy is algorithm-agnostic: this service never imports
`PredictionModelPort` or any framework adapter directly, it only drives ``objective``.

`BAYESIAN_OPTIMIZATION` and `OPTUNA` share one implementation (`_optuna_search`) built on Optuna's
ask-and-tell interface (`study.ask()`/`study.tell()`, not `study.optimize()`'s synchronous
callback, since our ``objective`` is async) — `BAYESIAN_OPTIMIZATION` is the fixed, opinionated
recipe (Optuna's default `TPESampler`); `OPTUNA` is the generic escape hatch accepting any
caller-supplied `optuna.samplers.BaseSampler`, which is what "Optuna-ready" (Milestone 9.1 spec)
means architecturally: every other strategy here is hand-rolled, but the door is open to any
Optuna sampler without new code.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Awaitable, Callable

import optuna

from modules.predictions.domain.validation import HPOResult, HPOStrategy, HPOTrial

optuna.logging.set_verbosity(optuna.logging.WARNING)

ParamSpace = dict[str, list | tuple]
Objective = Callable[[dict, float], Awaitable[float]]


class InvalidParamSpaceError(ValueError):
    pass


class UnsupportedHPOStrategyError(ValueError):
    pass


async def optimize(
    param_space: ParamSpace,
    objective: Objective,
    strategy: HPOStrategy,
    n_trials: int = 20,
    seed: int = 42,
    **kwargs,
) -> HPOResult:
    if not param_space:
        raise InvalidParamSpaceError("param_space must have at least one parameter")

    if strategy is HPOStrategy.GRID_SEARCH:
        trials = await _grid_search(param_space, objective)
    elif strategy is HPOStrategy.RANDOM_SEARCH:
        trials = await _random_search(param_space, objective, n_trials, seed)
    elif strategy is HPOStrategy.SUCCESSIVE_HALVING:
        trials = await _successive_halving(
            param_space, objective, n_candidates=kwargs.get("n_candidates", n_trials), seed=seed
        )
    elif strategy is HPOStrategy.BAYESIAN_OPTIMIZATION:
        trials = await _optuna_search(param_space, objective, n_trials, seed, sampler=optuna.samplers.TPESampler(seed=seed))
    elif strategy is HPOStrategy.OPTUNA:
        trials = await _optuna_search(param_space, objective, n_trials, seed, sampler=kwargs.get("sampler"))
    else:
        raise UnsupportedHPOStrategyError(f"unsupported HPO strategy '{strategy}'")

    if not trials:
        raise InvalidParamSpaceError("no trials were evaluated")

    best = max(trials, key=lambda t: t.metric_value)
    return HPOResult(strategy=strategy, trials=tuple(trials), best_params=best.params, best_metric_value=best.metric_value)


def _sample_param(spec, rng: random.Random):
    if isinstance(spec, list):
        return rng.choice(spec)
    if isinstance(spec, tuple) and len(spec) == 2:
        low, high = spec
        if isinstance(low, int) and isinstance(high, int):
            return rng.randint(low, high)
        return rng.uniform(float(low), float(high))
    raise InvalidParamSpaceError(f"unsupported param space {spec!r}")


async def _grid_search(param_space: ParamSpace, objective: Objective) -> list[HPOTrial]:
    for spec in param_space.values():
        if not isinstance(spec, list):
            raise InvalidParamSpaceError("GRID_SEARCH requires every param space to be a discrete list")

    names = list(param_space.keys())
    combos = itertools.product(*(param_space[name] for name in names))
    trials = []
    for i, combo in enumerate(combos):
        params = dict(zip(names, combo))
        metric_value = await objective(params, 1.0)
        trials.append(HPOTrial(trial_index=i, params=params, metric_value=metric_value))
    return trials


async def _random_search(param_space: ParamSpace, objective: Objective, n_trials: int, seed: int) -> list[HPOTrial]:
    rng = random.Random(seed)
    trials = []
    for i in range(n_trials):
        params = {name: _sample_param(spec, rng) for name, spec in param_space.items()}
        metric_value = await objective(params, 1.0)
        trials.append(HPOTrial(trial_index=i, params=params, metric_value=metric_value))
    return trials


async def _successive_halving(
    param_space: ParamSpace, objective: Objective, n_candidates: int, seed: int, reduction_factor: int = 3
) -> list[HPOTrial]:
    """Starts with ``n_candidates`` random configs at a small budget fraction, keeps the top
    ``1/reduction_factor`` after each rung, and doubles their budget — repeats until one
    candidate remains or the budget reaches 1.0."""
    rng = random.Random(seed)
    candidates = [{name: _sample_param(spec, rng) for name, spec in param_space.items()} for _ in range(n_candidates)]

    all_trials: list[HPOTrial] = []
    budget = 1.0 / reduction_factor
    trial_index = 0
    while True:
        scored = []
        for params in candidates:
            metric_value = await objective(params, min(budget, 1.0))
            all_trials.append(HPOTrial(trial_index=trial_index, params=params, metric_value=metric_value))
            scored.append((params, metric_value))
            trial_index += 1

        if len(candidates) <= 1 or budget >= 1.0:
            break

        scored.sort(key=lambda pair: pair[1], reverse=True)
        keep = max(1, len(scored) // reduction_factor)
        candidates = [params for params, _ in scored[:keep]]
        budget = min(budget * reduction_factor, 1.0)

    return all_trials


async def _optuna_search(
    param_space: ParamSpace, objective: Objective, n_trials: int, seed: int, sampler
) -> list[HPOTrial]:
    study = optuna.create_study(direction="maximize", sampler=sampler or optuna.samplers.TPESampler(seed=seed))
    trials = []
    for i in range(n_trials):
        trial = study.ask()
        params = {}
        for name, spec in param_space.items():
            if isinstance(spec, list):
                params[name] = trial.suggest_categorical(name, spec)
            elif isinstance(spec, tuple) and len(spec) == 2:
                low, high = spec
                if isinstance(low, int) and isinstance(high, int):
                    params[name] = trial.suggest_int(name, low, high)
                else:
                    params[name] = trial.suggest_float(name, float(low), float(high))
            else:
                raise InvalidParamSpaceError(f"unsupported param space for '{name}': {spec!r}")

        metric_value = await objective(params, 1.0)
        study.tell(trial, metric_value)
        trials.append(HPOTrial(trial_index=i, params=params, metric_value=metric_value))
    return trials
