"""Tests for `FootballGoalsPoissonAdapter` (statistical-baseline charter, Phase 3) — a real,
`fit()`-trained Poisson baseline for football's 12 goals/score markets. Exercised against small,
deterministic, count-shaped synthetic data (features genuinely correlated with the goal counts, so
directional-sanity assertions are meaningful rather than tolerant of noise) — real fitting, real
inference, no mocked ML internals.
"""

from __future__ import annotations

import pytest

from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import FootballGoalsPoissonAdapter
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
