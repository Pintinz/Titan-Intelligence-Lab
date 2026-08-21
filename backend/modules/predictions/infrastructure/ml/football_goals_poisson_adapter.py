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
"""

from __future__ import annotations

import math
import pickle
from dataclasses import dataclass, field

import numpy as np
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


@dataclass
class FootballGoalsPoissonAdapter:
    """One instance serves exactly one of the 12 football goals/score markets, per `params`:
    `market_shape` (`"total_threshold"` | `"team_total_threshold"` | `"correct_score"` |
    `"clean_sheet"` | `"win_to_nil"`), `line` (float, threshold shapes only), `team`
    (`"home"`/`"away"`, team-scoped shapes only)."""

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
        grid: dict[str, float] = {}
        grid_total = 0.0
        for home in range(_CORRECT_SCORE_MAX_GOALS + 1):
            for away in range(_CORRECT_SCORE_MAX_GOALS + 1):
                p = _poisson_pmf(home, lam_home) * _poisson_pmf(away, lam_away)
                grid[f"{home}-{away}"] = p
                grid_total += p
        # The honest model-implied remainder (Poisson has infinite support) — never a hardcoded 0.
        grid["OTHER"] = max(0.0, 1.0 - grid_total)

        labels = self.class_labels or tuple(grid.keys())
        distribution = {label: grid.get(label, 0.0) for label in labels}
        best_label = max(distribution, key=distribution.get)
        best_probability = distribution[best_label]
        return ModelPrediction(
            raw_score=logit(best_probability), probability=best_probability, value=best_label, distribution=distribution
        )

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
