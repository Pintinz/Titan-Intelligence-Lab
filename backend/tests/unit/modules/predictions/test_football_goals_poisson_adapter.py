"""Tests for `FootballGoalsPoissonAdapter` (statistical-baseline charter, Phase 3) — a real,
`fit()`-trained Poisson baseline for football's 12 goals/score markets. Exercised against small,
deterministic, count-shaped synthetic data (features genuinely correlated with the goal counts, so
directional-sanity assertions are meaningful rather than tolerant of noise) — real fitting, real
inference, no mocked ML internals.
"""

from __future__ import annotations

import numpy as np
import pytest

from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import (
    FootballGoalsPoissonAdapter,
    PoissonGridClassifierView,
    _apply_dixon_coles,
    _correct_score_grid,
    _dixon_coles_tau,
    _fit_dispersion,
    _fit_dixon_coles_rho,
    _MIN_ALPHA,
    _pmf,
    _survival,
    _total_survival,
)
from modules.predictions.ports.ml_model import InsufficientTrainingDataError, ModelNotFittedError, TrainingSample

CORRECT_SCORE_LABELS = tuple(f"{home}-{away}" for home in range(6) for away in range(6)) + ("OTHER",)


def _samples(n: int = 60) -> list[TrainingSample]:
    """`x1` genuinely drives both goal counts (home scales up faster than away with x1) so a fitted
    Poisson model's λ's respond directionally — real signal, not noise."""
    samples = []
    for i in range(n):
        x1 = float(i % 10)
        home_goals = max(0.0, round(0.35 * x1))
        away_goals = max(0.0, round(0.10 * x1))
        samples.append(
            TrainingSample(
                features={"x1": x1}, label=0.0, raw_home_goals=home_goals, raw_away_goals=away_goals
            )
        )
    return samples


def _samples_with_gaps(n_usable: int = 30, n_missing: int = 20) -> list[TrainingSample]:
    """A realistic mix — most outcomes for a market this adapter doesn't serve have no raw goal
    counts at all (`None`), and `fit()` must filter those out rather than crash or count them
    toward `MIN_TRAINING_SAMPLES`."""
    usable = _samples(n_usable)
    missing = [TrainingSample(features={"x1": float(i)}, label=0.0) for i in range(n_missing)]
    return usable + missing


class TestFit:
    async def test_fit_rejects_insufficient_usable_samples(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        with pytest.raises(InsufficientTrainingDataError):
            await adapter.fit(_samples(10))

    async def test_fit_filters_out_samples_missing_raw_goals(self):
        """30 usable + 20 with no raw goal counts — must still fit successfully on the 30 usable
        ones, never counting or crashing on the ones missing raw_home_goals/raw_away_goals."""
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        metrics = await adapter.fit(_samples_with_gaps(n_usable=30, n_missing=20))
        assert metrics.sample_count == 30
        assert adapter.is_fitted()

    async def test_fit_returns_real_mae_metric(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        metrics = await adapter.fit(_samples())
        assert metrics.metric_name == "train_mae"
        assert metrics.metric_value >= 0.0


class TestPredictBeforeFit:
    async def test_predict_before_fit_raises(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        with pytest.raises(ModelNotFittedError):
            adapter.predict_one({"x1": 1.0})


class TestTargetTypeGuard:
    """Phase 3 audit fix — `target_type` was accepted but silently ignored by every predict_one()
    path (all classification/multiclass-shaped, never continuous), so a caller mistakenly wiring
    this adapter for a regression-shaped market would have `TrainingPipelineService._evaluate_
    regression` silently score nonsense (raw_score is a log-odds number, not a goal count) instead
    of failing loudly."""

    def test_default_construction_is_classification_and_succeeds(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        assert adapter.target_type is TargetType.CLASSIFICATION

    def test_rejects_regression_target_type_at_construction(self):
        with pytest.raises(ValueError, match="classification-shaped"):
            FootballGoalsPoissonAdapter(target_type=TargetType.REGRESSION, params={"market_shape": "total_threshold", "line": 2.5})

    async def test_feature_importance_before_fit_raises(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        with pytest.raises(ModelNotFittedError):
            adapter.feature_importance()

    async def test_serialize_before_fit_raises(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        with pytest.raises(ModelNotFittedError):
            adapter.serialize()


class TestThresholdShapes:
    async def test_total_threshold_probability_is_valid(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        await adapter.fit(_samples())
        result = adapter.predict_one({"x1": 5.0})
        assert 0.0 <= result.probability <= 1.0
        assert result.value in {"positive", "negative"}

    async def test_team_total_threshold_is_directionally_sane(self):
        """Higher x1 -> higher fitted λ_home -> higher P(home_team_total_goals > 1.5)."""
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "team_total_threshold", "line": 1.5, "team": "home"}
        )
        await adapter.fit(_samples())
        low = adapter.predict_one({"x1": 0.0})
        high = adapter.predict_one({"x1": 9.0})
        assert high.probability > low.probability

    async def test_clean_sheet_probability_is_valid(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "clean_sheet", "team": "home"})
        await adapter.fit(_samples())
        result = adapter.predict_one({"x1": 3.0})
        assert 0.0 <= result.probability <= 1.0

    async def test_win_to_nil_probability_is_valid(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "win_to_nil", "team": "home"})
        await adapter.fit(_samples())
        result = adapter.predict_one({"x1": 3.0})
        assert 0.0 <= result.probability <= 1.0


class TestCorrectScore:
    async def test_distribution_sums_to_one_across_grid_and_other(self):
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score"}, class_labels=CORRECT_SCORE_LABELS
        )
        await adapter.fit(_samples())
        result = adapter.predict_one({"x1": 5.0})
        assert set(result.distribution.keys()) == set(CORRECT_SCORE_LABELS)
        assert sum(result.distribution.values()) == pytest.approx(1.0, abs=1e-6)
        assert result.value in CORRECT_SCORE_LABELS

    async def test_other_cell_is_honest_remainder_not_hardcoded_zero(self):
        """At a high λ (goals concentrated well outside the 0-5 grid), OTHER must carry real,
        non-trivial probability mass — never a hardcoded 0 regardless of how the λ's land."""
        samples = [
            TrainingSample(features={"x1": 1.0}, label=0.0, raw_home_goals=15.0, raw_away_goals=15.0)
            for _ in range(35)
        ]
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score"}, class_labels=CORRECT_SCORE_LABELS
        )
        await adapter.fit(samples)
        result = adapter.predict_one({"x1": 1.0})
        assert result.distribution["OTHER"] > 0.5

    async def test_predict_class_distribution_matches_predict_one(self):
        """`predict_class_distribution` (the surface `PoissonGridClassifierView` calls for
        calibration) must return exactly the same distribution `predict_one()` already does —
        it's a factored-out reuse of the same grid math, not a second implementation."""
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score"}, class_labels=CORRECT_SCORE_LABELS
        )
        await adapter.fit(_samples())
        via_predict_one = adapter.predict_one({"x1": 5.0}).distribution
        via_class_distribution = adapter.predict_class_distribution({"x1": 5.0})
        assert via_class_distribution == via_predict_one


class TestPredictPositiveProbability:
    async def test_matches_predict_one_probability_for_every_binary_shape(self):
        """`predict_positive_probability` (the surface `PoissonGridClassifierView` calls for
        calibration on binary-shaped markets) must return exactly the same P(positive)
        `predict_one()` already does for each shape — a factored-out reuse, not a second
        implementation that could silently drift from it."""
        for params in (
            {"market_shape": "total_threshold", "line": 2.5},
            {"market_shape": "team_total_threshold", "line": 1.5, "team": "home"},
            {"market_shape": "clean_sheet", "team": "home"},
            {"market_shape": "win_to_nil", "team": "home"},
        ):
            adapter = FootballGoalsPoissonAdapter(params=params)
            await adapter.fit(_samples())
            expected = adapter.predict_one({"x1": 5.0}).probability
            assert adapter.predict_positive_probability({"x1": 5.0}) == pytest.approx(expected)


class TestPoissonGridClassifierView:
    """Correct Score forensic audit (2026-08-26): `CalibrationValidationService` needs a real
    scikit-learn-classifier surface (`predict_proba`/`classes_`) over a fitted
    `FootballGoalsPoissonAdapter` — the raw `(home_model, away_model)` tuple
    `underlying_estimator()` returns has neither, which crashed calibration validation live
    against football.correct_score's real PRODUCTION Champion. These tests exercise the view
    directly, the same way `CalibrationValidationService._predict_proba`/`CalibratedClassifierCV`
    actually call it — vectorized `X` rows in `feature_order`, not a features dict."""

    async def test_predict_proba_multiclass_matches_predict_class_distribution(self):
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score"}, class_labels=CORRECT_SCORE_LABELS
        )
        await adapter.fit(_samples())
        view = PoissonGridClassifierView(adapter=adapter, classes_=np.arange(len(CORRECT_SCORE_LABELS)))

        X = np.array([[5.0], [3.0]])
        proba = view.predict_proba(X)

        assert proba.shape == (2, len(CORRECT_SCORE_LABELS))
        for row, x1 in zip(proba, (5.0, 3.0)):
            expected = adapter.predict_class_distribution({"x1": x1})
            assert row == pytest.approx([expected[label] for label in CORRECT_SCORE_LABELS])
            assert sum(row) == pytest.approx(1.0, abs=1e-6)

    async def test_predict_proba_binary_shape_is_two_column(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        await adapter.fit(_samples())
        view = PoissonGridClassifierView(adapter=adapter, classes_=np.array([0, 1]))

        X = np.array([[5.0]])
        proba = view.predict_proba(X)

        assert proba.shape == (1, 2)
        expected_positive = adapter.predict_positive_probability({"x1": 5.0})
        assert proba[0, 1] == pytest.approx(expected_positive)
        assert proba[0, 0] == pytest.approx(1.0 - expected_positive)

    async def test_predict_returns_the_argmax_class(self):
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score"}, class_labels=CORRECT_SCORE_LABELS
        )
        await adapter.fit(_samples())
        view = PoissonGridClassifierView(adapter=adapter, classes_=np.arange(len(CORRECT_SCORE_LABELS)))

        X = np.array([[5.0]])
        predicted = view.predict(X)

        expected_index = np.argmax(view.predict_proba(X)[0])
        assert predicted[0] == expected_index


class TestFeatureImportanceAndSerialization:
    async def test_feature_importance_sums_to_one(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        await adapter.fit(_samples())
        importance = adapter.feature_importance()
        assert set(importance.keys()) == {"x1"}
        assert sum(importance.values()) == pytest.approx(1.0, abs=1e-6)

    async def test_serialize_roundtrip_preserves_shape_and_predictions(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "team_total_threshold", "line": 1.5, "team": "away"})
        await adapter.fit(_samples())
        original = adapter.predict_one({"x1": 4.0})

        restored = FootballGoalsPoissonAdapter()
        restored.deserialize(adapter.serialize())
        assert restored.is_fitted()
        assert restored.market_shape == "team_total_threshold"
        assert restored.team == "away"
        again = restored.predict_one({"x1": 4.0})
        assert again.probability == pytest.approx(original.probability)

    async def test_underlying_estimator_returns_both_models(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        assert adapter.underlying_estimator() is None
        await adapter.fit(_samples())
        home_model, away_model = adapter.underlying_estimator()
        assert home_model is not None
        assert away_model is not None

    def test_target_type_is_classification_by_default(self):
        adapter = FootballGoalsPoissonAdapter()
        assert adapter.target_type is TargetType.CLASSIFICATION


def _sample_dixon_coles_scores(rng, n, lam_home, lam_away, rho):
    """Draws `n` (home_goals, away_goals) pairs from the Dixon-Coles-adjusted joint distribution
    for a fixed (lam_home, lam_away, rho) — a synthetic dataset with a REAL, known low-score
    correlation baked in, so `_fit_dixon_coles_rho` can be checked against ground truth instead of
    just "doesn't crash"."""
    grid = _apply_dixon_coles(_correct_score_grid(lam_home, lam_away), lam_home, lam_away, rho)
    scores = [k for k in grid if k != "OTHER"]
    weights = np.array([grid[k] for k in scores])
    weights = weights / weights.sum()
    chosen = rng.choice(len(scores), size=n, p=weights)
    return [tuple(int(v) for v in scores[i].split("-")) for i in chosen]


class TestDixonColesTau:
    def test_low_score_cells_use_the_real_formula(self):
        lam_home, lam_away, rho = 1.4, 1.1, -0.15
        assert _dixon_coles_tau(0, 0, lam_home, lam_away, rho) == pytest.approx(1.0 - lam_home * lam_away * rho)
        assert _dixon_coles_tau(0, 1, lam_home, lam_away, rho) == pytest.approx(1.0 + lam_home * rho)
        assert _dixon_coles_tau(1, 0, lam_home, lam_away, rho) == pytest.approx(1.0 + lam_away * rho)
        assert _dixon_coles_tau(1, 1, lam_home, lam_away, rho) == pytest.approx(1.0 - rho)

    def test_every_other_cell_is_unadjusted(self):
        for x, y in [(2, 0), (0, 2), (2, 2), (3, 1), (5, 5)]:
            assert _dixon_coles_tau(x, y, 1.4, 1.1, -0.2) == 1.0

    def test_zero_rho_is_the_identity_on_low_score_cells(self):
        for x, y in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            assert _dixon_coles_tau(x, y, 1.4, 1.1, 0.0) == pytest.approx(1.0)


class TestApplyDixonColes:
    def test_distribution_still_sums_to_one(self):
        grid = _correct_score_grid(1.4, 1.1)
        adjusted = _apply_dixon_coles(grid, 1.4, 1.1, -0.2)
        assert sum(adjusted.values()) == pytest.approx(1.0, abs=1e-9)

    def test_negative_rho_increases_draws_and_decreases_10_01(self):
        """The documented real-world direction (Dixon & Coles 1997): a negative rho makes 0-0/1-1
        MORE likely and 1-0/0-1 LESS likely than independent Poisson alone predicts."""
        grid = _correct_score_grid(1.4, 1.1)
        adjusted = _apply_dixon_coles(grid, 1.4, 1.1, -0.2)
        assert adjusted["0-0"] > grid["0-0"]
        assert adjusted["1-1"] > grid["1-1"]
        assert adjusted["1-0"] < grid["1-0"]
        assert adjusted["0-1"] < grid["0-1"]

    def test_zero_rho_leaves_the_grid_unchanged(self):
        grid = _correct_score_grid(1.4, 1.1)
        adjusted = _apply_dixon_coles(grid, 1.4, 1.1, 0.0)
        for key in grid:
            assert adjusted[key] == pytest.approx(grid[key])


class TestFitDixonColesRho:
    def test_recovers_a_known_negative_rho_from_synthetic_data(self):
        rng = np.random.default_rng(42)
        lam_home, lam_away, true_rho = 1.4, 1.1, -0.2
        pairs = _sample_dixon_coles_scores(rng, 4000, lam_home, lam_away, true_rho)
        home_goals = np.array([p[0] for p in pairs], dtype=float)
        away_goals = np.array([p[1] for p in pairs], dtype=float)
        lam_homes = np.full(len(pairs), lam_home)
        lam_aways = np.full(len(pairs), lam_away)

        recovered = _fit_dixon_coles_rho(home_goals, away_goals, lam_homes, lam_aways)

        assert recovered == pytest.approx(true_rho, abs=0.05)

    def test_independent_data_recovers_rho_near_zero(self):
        rng = np.random.default_rng(7)
        lam_home, lam_away = 1.4, 1.1
        home_goals = rng.poisson(lam_home, size=4000).astype(float)
        away_goals = rng.poisson(lam_away, size=4000).astype(float)
        lam_homes = np.full(4000, lam_home)
        lam_aways = np.full(4000, lam_away)

        recovered = _fit_dixon_coles_rho(home_goals, away_goals, lam_homes, lam_aways)

        assert recovered == pytest.approx(0.0, abs=0.08)


class TestDixonColesAdapter:
    async def test_use_dixon_coles_reads_params(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "correct_score", "dixon_coles": True})
        assert adapter.use_dixon_coles is True
        plain = FootballGoalsPoissonAdapter(params={"market_shape": "correct_score"})
        assert plain.use_dixon_coles is False

    async def test_fit_sets_rho_only_when_enabled_and_correct_score_shaped(self):
        dc_adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score", "dixon_coles": True}, class_labels=CORRECT_SCORE_LABELS
        )
        await dc_adapter.fit(_samples())
        assert dc_adapter._rho is not None

        plain_adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score"}, class_labels=CORRECT_SCORE_LABELS
        )
        await plain_adapter.fit(_samples())
        assert plain_adapter._rho is None

        # dixon_coles=True on a non-correct_score shape must not fit rho — it would have no effect
        # on that shape's marginal-only `_threshold_probability`.
        binary_dc_adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "total_threshold", "line": 2.5, "dixon_coles": True}
        )
        await binary_dc_adapter.fit(_samples())
        assert binary_dc_adapter._rho is None

    async def test_predicted_distribution_still_sums_to_one(self):
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score", "dixon_coles": True}, class_labels=CORRECT_SCORE_LABELS
        )
        await adapter.fit(_samples())
        result = adapter.predict_one({"x1": 5.0})
        assert sum(result.distribution.values()) == pytest.approx(1.0, abs=1e-6)

    async def test_serialize_roundtrip_preserves_rho(self):
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score", "dixon_coles": True}, class_labels=CORRECT_SCORE_LABELS
        )
        await adapter.fit(_samples())
        original_rho = adapter._rho

        restored = FootballGoalsPoissonAdapter()
        restored.deserialize(adapter.serialize())

        assert restored._rho == pytest.approx(original_rho)


class TestNegativeBinomialMath:
    """Forensic audit finding #7 (2026-08-30) — `_pmf`/`_survival` must reduce exactly to plain
    Poisson when `alpha` is `None` (every existing, non-NB call site), and behave as a real
    Negative-Binomial distribution otherwise."""

    def test_pmf_with_no_alpha_matches_poisson_exactly(self):
        from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import _poisson_pmf

        for k in range(6):
            assert _pmf(k, 2.3, None) == pytest.approx(_poisson_pmf(k, 2.3))

    def test_pmf_below_min_alpha_falls_back_to_poisson(self):
        from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import _poisson_pmf

        assert _pmf(1, 2.3, _MIN_ALPHA / 2) == pytest.approx(_poisson_pmf(1, 2.3))

    def test_nb_pmf_sums_to_one_over_a_wide_range(self):
        total = sum(_pmf(k, 2.0, 0.5) for k in range(200))
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_nb_pmf_has_fatter_tail_than_poisson_at_same_mean(self):
        """The whole point of the dispersion parameter: at a fixed mean, a real alpha > 0 must
        put more probability mass on extreme counts than Poisson does — otherwise it wouldn't be
        modeling overdispersion at all."""
        from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import _poisson_pmf

        mean = 3.0
        far_tail_nb = sum(_pmf(k, mean, 1.0) for k in range(10, 60))
        far_tail_poisson = sum(_poisson_pmf(k, mean) for k in range(10, 60))
        assert far_tail_nb > far_tail_poisson

    def test_survival_with_no_alpha_matches_poisson_exactly(self):
        from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import _poisson_survival

        assert _survival(2.5, 3.1, None) == pytest.approx(_poisson_survival(2.5, 3.1))

    def test_total_survival_with_no_alpha_matches_closed_form_poisson_sum(self):
        from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import _poisson_survival

        lam_home, lam_away = 1.4, 0.9
        assert _total_survival(2.5, lam_home, lam_away, None, None) == pytest.approx(
            _poisson_survival(2.5, lam_home + lam_away), abs=1e-9
        )

    def test_total_survival_convolution_matches_manual_grid_sum(self):
        """Independent verification of `_total_survival`'s convolution against a hand-summed grid
        — not just internal self-consistency."""
        lam_home, lam_away, alpha_home, alpha_away = 1.6, 1.1, 0.4, 0.6
        line = 2.5
        expected_cdf = sum(
            _pmf(h, lam_home, alpha_home) * _pmf(a, lam_away, alpha_away)
            for h in range(3) for a in range(3) if h + a <= 2
        )
        assert _total_survival(line, lam_home, lam_away, alpha_home, alpha_away) == pytest.approx(
            1.0 - expected_cdf, abs=1e-9
        )


class TestFitDispersion:
    def test_recovers_near_zero_alpha_for_genuinely_equidispersed_data(self):
        rng = np.random.default_rng(42)
        mu = np.full(400, 2.0)
        y = rng.poisson(mu)

        alpha = _fit_dispersion(y, mu)

        assert alpha < 0.15

    def test_recovers_a_meaningfully_larger_alpha_for_genuinely_overdispersed_data(self):
        from scipy.stats import nbinom

        rng = np.random.default_rng(42)
        true_alpha = 1.5
        mu = np.full(400, 2.0)
        n = 1.0 / true_alpha
        p = n / (n + mu)
        y = nbinom.rvs(n, p, random_state=rng)

        alpha = _fit_dispersion(y, mu)

        assert alpha > 0.5


class TestNegativeBinomialAdapter:
    async def test_use_negative_binomial_reads_params(self):
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5, "negative_binomial": True})
        assert adapter.use_negative_binomial is True
        plain = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        assert plain.use_negative_binomial is False

    async def test_fit_sets_alphas_only_when_enabled(self):
        nb_adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "total_threshold", "line": 2.5, "negative_binomial": True}
        )
        await nb_adapter.fit(_samples())
        assert nb_adapter._alpha_home is not None
        assert nb_adapter._alpha_away is not None

        plain_adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        await plain_adapter.fit(_samples())
        assert plain_adapter._alpha_home is None
        assert plain_adapter._alpha_away is None

    @pytest.mark.parametrize(
        "params",
        [
            {"market_shape": "total_threshold", "line": 2.5},
            {"market_shape": "team_total_threshold", "line": 1.5, "team": "home"},
            {"market_shape": "team_total_threshold", "line": 1.5, "team": "away"},
            {"market_shape": "clean_sheet", "team": "home"},
            {"market_shape": "clean_sheet", "team": "away"},
            {"market_shape": "win_to_nil", "team": "home"},
            {"market_shape": "win_to_nil", "team": "away"},
        ],
    )
    async def test_every_binary_shape_produces_a_valid_probability_under_negative_binomial(self, params):
        adapter = FootballGoalsPoissonAdapter(params={**params, "negative_binomial": True})
        await adapter.fit(_samples())

        result = adapter.predict_one({"x1": 5.0})

        assert 0.0 <= result.probability <= 1.0

    async def test_correct_score_distribution_still_sums_to_one_under_negative_binomial(self):
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score", "negative_binomial": True}, class_labels=CORRECT_SCORE_LABELS
        )
        await adapter.fit(_samples())

        result = adapter.predict_one({"x1": 5.0})

        assert sum(result.distribution.values()) == pytest.approx(1.0, abs=1e-6)

    async def test_negative_binomial_and_dixon_coles_can_both_be_enabled_together(self):
        """Each is registered as its own, separately-benchmarked candidate — never both at once
        in production — but nothing should crash if a caller does combine them: the grid is built
        with NB pmf, then Dixon-Coles reweights it, same as it would reweight a Poisson grid."""
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "correct_score", "negative_binomial": True, "dixon_coles": True},
            class_labels=CORRECT_SCORE_LABELS,
        )
        await adapter.fit(_samples())

        result = adapter.predict_one({"x1": 5.0})

        assert sum(result.distribution.values()) == pytest.approx(1.0, abs=1e-6)

    async def test_serialize_roundtrip_preserves_alphas_and_predictions(self):
        adapter = FootballGoalsPoissonAdapter(
            params={"market_shape": "total_threshold", "line": 2.5, "negative_binomial": True}
        )
        await adapter.fit(_samples())
        original_probability = adapter.predict_one({"x1": 5.0}).probability

        restored = FootballGoalsPoissonAdapter()
        restored.deserialize(adapter.serialize())

        assert restored._alpha_home == pytest.approx(adapter._alpha_home)
        assert restored._alpha_away == pytest.approx(adapter._alpha_away)
        assert restored.predict_one({"x1": 5.0}).probability == pytest.approx(original_probability)
