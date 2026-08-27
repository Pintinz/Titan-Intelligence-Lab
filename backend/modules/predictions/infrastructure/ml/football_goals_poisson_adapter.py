"""Statistical-baseline charter, Phase 3 — a real, benchmarked Poisson baseline for football's 12
goals/score markets (`total_goals_over_under*`, `home/away_team_total_goals`, `correct_score`,
`home/away_clean_sheet`, `home/away_win_to_nil`).

Deliberately a dedicated adapter, not a `SklearnAdapter` extension: this candidate reads
`TrainingSample.raw_home_goals`/`raw_away_goals` (the real final-score goal counts) instead of
`.label`, and must emit a `ModelPrediction` shaped for whichever of 5 distinct market shapes it's
serving — no other adapter in the roster does either of those things. One instance per market, its
shape/line/team baked into `CandidateSpec.params` (no `AutomaticModelSelectionService`/
`ScheduledRetrainingOrchestrator` signature change needed — `_build_model()` passes `params`
through exactly like every other framework branch already does).

Fits two independent `sklearn.linear_model.PoissonRegressor` models (home goals, away goals) —
reusing the statistical-baseline charter's Phase 1 algorithm, already in this codebase, no new
dependency. Every market's probability is then a closed-form function of the two fitted λ's,
computed with plain `math`/`numpy` (manual Poisson pmf/survival function) rather than `scipy.stats`,
to avoid a new dependency question entirely for a few lines of math.

This is NOT the previously-removed `PoissonScorePredictor`/`PoissonGoalsThresholdPredictor`
(deleted commit `09dacc2`) — those were hand-coded closed-form formula predictors on the older
`PredictorPort`, never `fit()`-trained, registered as an unconditional Champion with no benchmark.
This adapter implements `PredictionModelPort`, is `fit()`-trained via the same
`TrainingPipelineService` every other candidate uses, and is ranked against the ML roster on real
held-out log-loss inside `AutomaticModelSelectionService` — a genuinely different, benchmarked
mechanism, satisfying the same "one real trained model per market, never a fabricated placeholder"
rule the removal enforced rather than conflicting with it.

Correct Score forensic audit (2026-08-27): optional Dixon & Coles (1997) low-score correlation
adjustment for the `correct_score` shape only (`params={"dixon_coles": True}`, `use_dixon_coles`,
`_fit_dixon_coles_rho`/`_apply_dixon_coles`) — a plain, dependency-free grid search over the single
correlation parameter rho, fit against the two already-independently-fitted Poisson GLMs' own
in-sample predictions rather than jointly re-estimating team-strength parameters the way the
original paper's own model does. Registered as a genuinely distinct, separately-benchmarked
candidate (`MLAlgorithm.POISSON_DIXON_COLES_MODEL`,
`scheduled_retraining_orchestrator.DIXON_COLES_ELIGIBLE_MARKETS`) — never assumed to improve
predictions, always compared against the plain independent-Poisson candidate on real held-out log
loss. A live backtest against 828 real resolved outcomes found rho fits slightly positive on the
data available today (opposite the classic literature direction) and log loss essentially tied
with the plain candidate — an honest empirical result, not a reason to remove the mechanism: a
different or larger future dataset may exhibit the classic low-score correlation, and the
benchmark will pick a winner correctly either way without further code changes.
"""

from __future__ import annotations

import math
import pickle
from dataclasses import dataclass, field

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.linear_model import PoissonRegressor

from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml._math import feature_union, logit, vectorize
from modules.predictions.ports.ml_model import (
    MIN_TRAINING_SAMPLES,
    InsufficientTrainingDataError,
    ModelNotFittedError,
    ModelPrediction,
    TrainingMetrics,
    TrainingSample,
)

_CORRECT_SCORE_MAX_GOALS = 5


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for X ~ Poisson(lam). `lam` is floored at a tiny positive value — a fitted
    PoissonRegressor's mean prediction is mathematically always > 0, but this guards the edge case
    of an extreme/degenerate fit rather than raising on `math.exp(-0.0)` edge math."""
    lam = max(lam, 1e-9)
    return math.exp(-lam) * lam**k / math.factorial(k)


def _poisson_survival(line: float, lam: float) -> float:
    """P(X > line) for X ~ Poisson(lam) — every threshold this adapter serves uses a half-integer
    line (e.g. 2.5), so `floor(line)` is exactly the highest integer still <= line, and summing the
    pmf from 0 through it gives P(X <= line) whose complement is the survival probability."""
    k_max = int(math.floor(line))
    cdf = sum(_poisson_pmf(k, lam) for k in range(k_max + 1))
    return max(0.0, min(1.0, 1.0 - cdf))


def _correct_score_grid(lam_home: float, lam_away: float) -> dict[str, float]:
    """The independent-Poisson `{"h-a": probability}` grid for one fixture's fitted rate pair,
    plus the honest model-implied `OTHER` remainder (Poisson has infinite support, never a
    hardcoded 0) — factored out of `_predict_correct_score` so `predict_class_distribution` below
    can reuse the exact same math instead of duplicating it."""
    grid: dict[str, float] = {}
    grid_total = 0.0
    for home in range(_CORRECT_SCORE_MAX_GOALS + 1):
        for away in range(_CORRECT_SCORE_MAX_GOALS + 1):
            p = _poisson_pmf(home, lam_home) * _poisson_pmf(away, lam_away)
            grid[f"{home}-{away}"] = p
            grid_total += p
    grid["OTHER"] = max(0.0, 1.0 - grid_total)
    return grid


_DIXON_COLES_LOW_SCORE_CELLS = ((0, 0), (0, 1), (1, 0), (1, 1))
_DIXON_COLES_RHO_BOUNDS = (-0.9, 0.9)  # generous — a degenerate rho is naturally disfavored by the
# likelihood itself (see `_fit_dixon_coles_rho`), so the bound only needs to keep tau's argument
# safely away from producing a negative probability for any realistic fitted lambda.


def _dixon_coles_tau(x: int, y: int, lam_home: float, lam_away: float, rho: float) -> float:
    """Dixon & Coles (1997)'s low-score correlation adjustment — real football's actual observed
    (home, away) goal counts are not perfectly independent even after conditioning on each side's
    own fitted scoring rate: 0-0 and 1-1 draws occur more often than independent Poisson implies,
    and 1-0/0-1 slightly less often (the empirical finding the 1997 paper is named for). Every
    other scoreline is untouched (tau=1.0, no adjustment) — the correlation is specifically
    confined to these four low-score cells, not a general reweighting."""
    if (x, y) == (0, 0):
        return 1.0 - lam_home * lam_away * rho
    if (x, y) == (0, 1):
        return 1.0 + lam_home * rho
    if (x, y) == (1, 0):
        return 1.0 + lam_away * rho
    if (x, y) == (1, 1):
        return 1.0 - rho
    return 1.0


def _dixon_coles_negative_log_likelihood(
    rho: float, home_goals: np.ndarray, away_goals: np.ndarray, lam_homes: np.ndarray, lam_aways: np.ndarray
) -> float:
    """Only the four low-score cells' tau contributes — every other cell's tau is exactly 1.0, so
    `log(tau) == 0` and it drops out of the sum. This is this codebase's version of the 1997
    paper's own rho optimization, fitting only rho against per-sample lambdas that are already
    fixed by the two independently-fitted `PoissonRegressor` GLMs, rather than jointly
    re-estimating team-strength parameters the way the original paper's own model does."""
    total = 0.0
    for x, y, lh, la in zip(home_goals, away_goals, lam_homes, lam_aways):
        if x <= 1 and y <= 1:
            tau = max(_dixon_coles_tau(int(x), int(y), float(lh), float(la), rho), 1e-9)
            total -= math.log(tau)
    return total


def _fit_dixon_coles_rho(
    home_goals: np.ndarray, away_goals: np.ndarray, lam_homes: np.ndarray, lam_aways: np.ndarray
) -> float:
    """A plain, dependency-free coarse-to-fine grid search over rho — no `scipy.optimize`, same
    "plain math/numpy" posture this module's Poisson pmf/survival math already commits to. The
    negative log-likelihood is a smooth, well-behaved 1-D function over `_DIXON_COLES_RHO_BOUNDS`
    (a sum of four simple linear/bilinear terms), so a two-pass grid search converges to
    essentially the same optimum a gradient method would, without a derivative to compute for
    four separate cases."""
    best_rho = 0.0
    best_nll = _dixon_coles_negative_log_likelihood(0.0, home_goals, away_goals, lam_homes, lam_aways)
    low, high = _DIXON_COLES_RHO_BOUNDS
    for _ in range(2):  # coarse pass across the full bounds, then a fine pass around the winner
        candidates = np.linspace(low, high, 41)
        for rho in candidates:
            nll = _dixon_coles_negative_log_likelihood(float(rho), home_goals, away_goals, lam_homes, lam_aways)
            if nll < best_nll:
                best_nll, best_rho = nll, float(rho)
        step = (candidates[1] - candidates[0]) * 2  # narrow the window around the current best
        low, high = best_rho - step, best_rho + step
    return best_rho


def _apply_dixon_coles(grid: dict[str, float], lam_home: float, lam_away: float, rho: float) -> dict[str, float]:
    """Reweights the four low-score cells by tau, then renormalizes the WHOLE grid (including
    `OTHER`) back to sum to 1.0 — tau can push the raw total slightly away from 1 (a real,
    expected property of the adjustment, not a bug), and this module's own contract (every served
    distribution sums to 1.0, `test_distribution_sums_to_one_across_grid_and_other`) must still
    hold exactly."""
    adjusted = dict(grid)
    for x, y in _DIXON_COLES_LOW_SCORE_CELLS:
        key = f"{x}-{y}"
        if key in adjusted:
            adjusted[key] = max(0.0, adjusted[key] * _dixon_coles_tau(x, y, lam_home, lam_away, rho))
    total = sum(adjusted.values())
    if total <= 0.0:
        return grid  # degenerate — honestly fall back to the unadjusted grid rather than divide by ~0
    return {label: value / total for label, value in adjusted.items()}


@dataclass
class FootballGoalsPoissonAdapter:
    """One instance serves exactly one of the 12 football goals/score markets, per `params`:
    `market_shape` (`"total_threshold"` | `"team_total_threshold"` | `"correct_score"` |
    `"clean_sheet"` | `"win_to_nil"`), `line` (float, threshold shapes only), `team`
    (`"home"`/`"away"`, team-scoped shapes only), and `dixon_coles` (bool, `correct_score` only —
    see `use_dixon_coles`) — whether to fit and apply the Dixon & Coles (1997) low-score
    correlation adjustment to the correct-score grid."""

    # Held only to satisfy `PredictionModelPort`'s interface (and because `TrainingPipelineService
    # .train()` branches its evaluator on `model.target_type`, not on anything this class computes)
    # — every `predict_one()` path below always returns a probability/value pair (binary threshold/
    # clean-sheet/win-to-nil shapes, or the multiclass `correct_score` distribution), never a
    # continuous raw prediction. `__post_init__` fails loudly on any other value instead of
    # silently mis-evaluating a Poisson candidate as if it were a regression model.
    target_type: TargetType = TargetType.CLASSIFICATION
    params: dict = field(default_factory=dict)
    feature_order: list[str] = field(default_factory=list)
    class_labels: tuple[str, ...] = field(default_factory=tuple)
    _home_model: object | None = field(default=None, repr=False)
    _away_model: object | None = field(default=None, repr=False)
    _rho: float | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.target_type is not TargetType.CLASSIFICATION:
            raise ValueError(
                f"FootballGoalsPoissonAdapter only serves classification-shaped markets — every "
                f"predict_one() path returns a probability/value pair (or the multiclass "
                f"correct_score distribution), never a continuous raw score a regression "
                f"evaluator could score. Got target_type={self.target_type!r}."
            )

    @property
    def market_shape(self) -> str:
        return self.params.get("market_shape", "total_threshold")

    @property
    def line(self) -> float | None:
        return self.params.get("line")

    @property
    def team(self) -> str | None:
        return self.params.get("team")

    @property
    def use_dixon_coles(self) -> bool:
        """Correct Score forensic audit (2026-08-27) — a second, distinct `CandidateSpec`
        (`DIXON_COLES_ELIGIBLE_MARKETS`, `scheduled_retraining_orchestrator.py`) registers this
        adapter with `params={"market_shape": "correct_score", "dixon_coles": True}`, empirically
        benchmarked against the plain independent-Poisson candidate on real held-out log loss —
        never assumed better, always compared."""
        return bool(self.params.get("dixon_coles", False))

    async def fit(
        self, samples: list[TrainingSample], validation_samples: list[TrainingSample] | None = None
    ) -> TrainingMetrics:
        del validation_samples  # no native early stopping for a closed-form GLM pair
        usable = [s for s in samples if s.raw_home_goals is not None and s.raw_away_goals is not None]
        if len(usable) < MIN_TRAINING_SAMPLES:
            raise InsufficientTrainingDataError(
                f"FootballGoalsPoissonAdapter({self.market_shape}) requires >= {MIN_TRAINING_SAMPLES} "
                f"samples with real goal counts, got {len(usable)}"
            )
        self.feature_order = feature_union(usable)
        X = np.array([vectorize(s.features, self.feature_order) for s in usable])
        y_home = np.array([float(s.raw_home_goals) for s in usable])
        y_away = np.array([float(s.raw_away_goals) for s in usable])

        self._home_model = PoissonRegressor()
        self._home_model.fit(X, y_home)
        self._away_model = PoissonRegressor()
        self._away_model.fit(X, y_away)

        home_pred = self._home_model.predict(X)
        away_pred = self._away_model.predict(X)

        if self.use_dixon_coles and self.market_shape == "correct_score":
            # Rho only ever affects the multiclass correct-score grid (see `_apply_dixon_coles`'s
            # call site in `_class_distribution_from_lambdas`) — fitting it for any other
            # `market_shape` would be wasted computation with zero effect on that shape's
            # marginal-only `_threshold_probability`, so it's skipped rather than silently unused.
            self._rho = _fit_dixon_coles_rho(y_home, y_away, home_pred, away_pred)

        mae = float(np.mean(np.abs(home_pred - y_home)) + np.mean(np.abs(away_pred - y_away))) / 2.0
        return TrainingMetrics(sample_count=len(usable), metric_name="train_mae", metric_value=mae)

    def predict_lambdas(self, features: dict[str, float]) -> tuple[float, float]:
        """The two fitted Poisson rate parameters (`lam_home`, `lam_away`) for one fixture's
        features — exposed so a caller (e.g. `StatisticalBaselineProvider`'s derivation of
        `match_winner`/`both_teams_to_score` via `poisson_score_grid`) can reuse an already-fitted
        `correct_score`-shaped model's goal-rate estimate without a second training pass. Every
        `market_shape` fits the same two regressors, so this works regardless of which shape this
        particular instance serves."""
        if self._home_model is None or self._away_model is None:
            raise ModelNotFittedError(
                f"FootballGoalsPoissonAdapter({self.market_shape}).predict_lambdas called before fit()/deserialize()"
            )
        x = np.array([vectorize(features, self.feature_order)])
        return float(self._home_model.predict(x)[0]), float(self._away_model.predict(x)[0])

    def predict_one(self, features: dict[str, float]) -> ModelPrediction:
        if self._home_model is None or self._away_model is None:
            raise ModelNotFittedError(
                f"FootballGoalsPoissonAdapter({self.market_shape}).predict_one called before fit()/deserialize()"
            )
        lam_home, lam_away = self.predict_lambdas(features)

        if self.market_shape == "correct_score":
            return self._predict_correct_score(lam_home, lam_away)

        probability = self._threshold_probability(lam_home, lam_away)
        return ModelPrediction(
            raw_score=logit(probability),
            probability=probability,
            value="positive" if probability >= 0.5 else "negative",
        )

    def _threshold_probability(self, lam_home: float, lam_away: float) -> float:
        shape = self.market_shape
        if shape == "total_threshold":
            return _poisson_survival(self.line, lam_home + lam_away)
        if shape == "team_total_threshold":
            lam = lam_home if self.team == "home" else lam_away
            return _poisson_survival(self.line, lam)
        if shape == "clean_sheet":
            # A team keeps a clean sheet iff its opponent scores 0.
            lam_opponent = lam_away if self.team == "home" else lam_home
            return _poisson_pmf(0, lam_opponent)
        if shape == "win_to_nil":
            # Team wins AND opponent scores 0 — independent-Poisson assumption, same posture as
            # every other shape here.
            lam_team = lam_home if self.team == "home" else lam_away
            lam_opponent = lam_away if self.team == "home" else lam_home
            return _poisson_pmf(0, lam_opponent) * (1.0 - _poisson_pmf(0, lam_team))
        raise ValueError(f"FootballGoalsPoissonAdapter: unknown market_shape {shape!r}")

    def _predict_correct_score(self, lam_home: float, lam_away: float) -> ModelPrediction:
        distribution = self._class_distribution_from_lambdas(lam_home, lam_away)
        best_label = max(distribution, key=distribution.get)
        best_probability = distribution[best_label]
        return ModelPrediction(
            raw_score=logit(best_probability), probability=best_probability, value=best_label, distribution=distribution
        )

    def _class_distribution_from_lambdas(self, lam_home: float, lam_away: float) -> dict[str, float]:
        grid = _correct_score_grid(lam_home, lam_away)
        if self._rho is not None:
            grid = _apply_dixon_coles(grid, lam_home, lam_away, self._rho)
        labels = self.class_labels or tuple(grid.keys())
        return {label: grid.get(label, 0.0) for label in labels}

    def predict_positive_probability(self, features: dict[str, float]) -> float:
        """P(the market's defined "positive" side) for any of this adapter's four binary-shaped
        `market_shape`s (`total_threshold`/`team_total_threshold`/`clean_sheet`/`win_to_nil`) —
        the same closed-form Poisson probability `predict_one()` already returns as `probability`
        for those shapes, factored out so `PoissonGridClassifierView` below can score/recalibrate
        it through a real scikit-learn-shaped surface instead of the raw
        `(home_model, away_model)` tuple `underlying_estimator()` returns, which has neither
        `predict_proba` nor `decision_function`."""
        lam_home, lam_away = self.predict_lambdas(features)
        return self._threshold_probability(lam_home, lam_away)

    def predict_class_distribution(self, features: dict[str, float]) -> dict[str, float]:
        """P(each class label) for this adapter's multiclass `correct_score` shape — the same
        grid `_predict_correct_score` builds, factored out for the same calibration-surface
        reason `predict_positive_probability` is."""
        lam_home, lam_away = self.predict_lambdas(features)
        return self._class_distribution_from_lambdas(lam_home, lam_away)

    def feature_importance(self) -> dict[str, float]:
        if self._home_model is None or self._away_model is None:
            raise ModelNotFittedError(
                f"FootballGoalsPoissonAdapter({self.market_shape}).feature_importance called before fit()/deserialize()"
            )
        home_importance = np.abs(np.asarray(self._home_model.coef_, dtype=float))
        away_importance = np.abs(np.asarray(self._away_model.coef_, dtype=float))
        combined = (home_importance + away_importance) / 2.0
        total = float(combined.sum()) or 1.0
        return {key: float(value) / total for key, value in zip(self.feature_order, combined)}

    def is_fitted(self) -> bool:
        return self._home_model is not None and self._away_model is not None

    def underlying_estimator(self):
        """Returns `(home_model, away_model)` — SHAP explainability for this two-model composite
        adapter is a known, explicitly out-of-scope gap for Phase 3."""
        if self._home_model is None or self._away_model is None:
            return None
        return (self._home_model, self._away_model)

    def serialize(self) -> bytes:
        if self._home_model is None or self._away_model is None:
            raise ModelNotFittedError(
                f"FootballGoalsPoissonAdapter({self.market_shape}).serialize called before fit()/deserialize()"
            )
        return pickle.dumps(
            {
                "home_model": self._home_model,
                "away_model": self._away_model,
                "feature_order": self.feature_order,
                "target_type": self.target_type,
                "params": self.params,
                "class_labels": self.class_labels,
                "rho": self._rho,
            }
        )

    def deserialize(self, payload: bytes) -> None:
        state = pickle.loads(payload)
        self._home_model = state["home_model"]
        self._away_model = state["away_model"]
        self.feature_order = state["feature_order"]
        self.target_type = state["target_type"]
        self.params = state.get("params", {})
        self.class_labels = state.get("class_labels", ())
        self._rho = state.get("rho")


@dataclass
class PoissonGridClassifierView(ClassifierMixin, BaseEstimator):
    """Correct Score forensic audit (2026-08-26) — a minimal, read-only scikit-learn-classifier
    surface (`predict_proba`, `predict`, `classes_`) over an already-fitted
    `FootballGoalsPoissonAdapter`.

    Real live defect this fixes: `CalibrationValidationService` (the genuinely multiclass-aware
    Platt/isotonic recalibration + log-loss comparison machinery, `calibration_validation_service.py`)
    calls `adapter.underlying_estimator()` and passes the result straight into scikit-learn's
    `CalibratedClassifierCV`/`FrozenEstimator`, which requires exactly this surface — every other
    adapter's `underlying_estimator()` already returns one real sklearn classifier that has it.
    `FootballGoalsPoissonAdapter.underlying_estimator()` instead returns `(home_model, away_model)`,
    a bare tuple of two independent `PoissonRegressor` GLMs with neither method, which crashed
    `CalibrationValidationService._predict_proba` with `AttributeError: 'tuple' object has no
    attribute 'decision_function'` — confirmed live against `football.correct_score`'s real
    PRODUCTION Champion (v8) before this fix, meaning the scheduled
    `check_scheduled_calibration_validation` Celery task (every 6h, `beat_schedule.py`) has been
    raising unhandled on every single run since that Champion was promoted, not just skipping this
    one market: `_validate_market_safe` only catches `CalibrationBlockedError`, so this crash
    aborted `validate_all_production_markets`'s sweep for every other PRODUCTION market too.

    Inherits `ClassifierMixin`/`BaseEstimator` (rather than plain duck-typing) because modern
    scikit-learn's `CalibratedClassifierCV` calls `is_classifier()` -> `get_tags()` ->
    `estimator.__sklearn_tags__()` internally, which only a real `BaseEstimator` subclass provides
    — confirmed live, separately: without this, `CalibratedClassifierCV.fit()` itself raised
    `AttributeError: 'PoissonGridClassifierView' object has no attribute '__sklearn_tags__'` even
    though `predict_proba`/`classes_` were both already correct.

    Read-only in substance, but `fit()` still exists as a no-op identity (`return self`): confirmed
    live, `sklearn.frozen.FrozenEstimator.fit()` calls `check_is_fitted(self.estimator)` before its
    own no-op passthrough, and `check_is_fitted` requires `hasattr(estimator, "fit")` just to
    recognize the object as a real estimator at all (`TypeError: ... is not an estimator instance`
    otherwise) — it is never actually invoked with real training data; the underlying Poisson
    regressors were already fit by `FootballGoalsPoissonAdapter.fit()` long before this view is
    ever constructed, and `FrozenEstimator` itself is the mechanism that skips calling it for real.

    Handles both of this adapter's real market shapes so any future Poisson-served market reaching
    PRODUCTION hits the same working path, not just `correct_score`: the multiclass `correct_score`
    grid (`predict_class_distribution`), and the binary `total_threshold`/`team_total_threshold`/
    `clean_sheet`/`win_to_nil` shapes (`predict_positive_probability`, returned as a real two-column
    `[P(negative), P(positive)]` matrix — the same shape `_predict_proba`'s own binary fallback
    already produces for a real sklearn `decision_function`-only classifier)."""

    adapter: FootballGoalsPoissonAdapter
    classes_: np.ndarray

    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> "PoissonGridClassifierView":
        """No-op identity — see the class docstring's `check_is_fitted` note. `FrozenEstimator`
        never actually calls this with real data; it exists only so `check_is_fitted` recognizes
        this object as a real estimator before `FrozenEstimator` short-circuits the actual refit."""
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        is_multiclass = self.adapter.market_shape == "correct_score"
        rows = []
        for row in X:
            features = dict(zip(self.adapter.feature_order, row))
            if is_multiclass:
                distribution = self.adapter.predict_class_distribution(features)
                rows.append([distribution[label] for label in self.adapter.class_labels])
            else:
                positive = self.adapter.predict_positive_probability(features)
                rows.append([1.0 - positive, positive])
        return np.asarray(rows)

    def predict(self, X: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(X)
        return self.classes_[np.argmax(proba, axis=1)]
