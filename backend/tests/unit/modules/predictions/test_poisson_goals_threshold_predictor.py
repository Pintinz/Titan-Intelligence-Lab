from __future__ import annotations

import math

import pytest

from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.infrastructure.predictors.poisson_goals_threshold_predictor import (
    MissingExpectedGoalsFeatureError,
    PoissonGoalsThresholdMode,
    PoissonGoalsThresholdPredictor,
    UnsupportedMarketKindError,
    _poisson_cdf,
    _poisson_pmf,
)

HOME_KEY = "football.fixture.expected_home_goals"
AWAY_KEY = "football.fixture.expected_away_goals"


def _predictor(mode, line=2.5, side="home", market_kind=MarketKind.TOTAL):
    return PoissonGoalsThresholdPredictor(market_kind=market_kind, mode=mode, line=line, side=side)


def test_poisson_cdf_matches_summed_pmf():
    lam = 2.3
    assert _poisson_cdf(3, lam) == pytest.approx(sum(_poisson_pmf(k, lam) for k in range(4)))


def test_rejects_invalid_side():
    with pytest.raises(ValueError):
        PoissonGoalsThresholdPredictor(
            market_kind=MarketKind.BINARY, mode=PoissonGoalsThresholdMode.CLEAN_SHEET, side="both"
        )


class TestTotalOverUnder:
    @pytest.mark.asyncio
    async def test_matches_manual_poisson_calculation(self):
        """The real regression test for the bug this predictor exists to fix: P(total > line) is
        computed from the sum-of-Poissons closed form, not a shared weighted-feature formula."""
        predictor = _predictor(PoissonGoalsThresholdMode.TOTAL_OVER_UNDER, line=2.5)

        output = await predictor.predict(
            MarketKind.TOTAL, features={HOME_KEY: 1.5, AWAY_KEY: 1.2}, mapping_weights={}
        )

        expected_p_over = 1.0 - _poisson_cdf(2, 1.5 + 1.2)
        assert output.probability == pytest.approx(expected_p_over)
        assert output.value == ("positive" if expected_p_over >= 0.5 else "negative")
        assert output.distribution == {"positive": pytest.approx(expected_p_over), "negative": pytest.approx(1.0 - expected_p_over)}

    @pytest.mark.asyncio
    async def test_different_lines_produce_different_probabilities(self):
        """The exact bug found live-verifying the Universal Probability Engine: every over/under
        line used to return the identical probability. A 0.5 line must be far more likely to go
        "over" than a 4.5 line for the same expected-goals input."""
        features = {HOME_KEY: 1.4, AWAY_KEY: 1.1}

        low_line = await _predictor(PoissonGoalsThresholdMode.TOTAL_OVER_UNDER, line=0.5).predict(
            MarketKind.TOTAL, features, {}
        )
        high_line = await _predictor(PoissonGoalsThresholdMode.TOTAL_OVER_UNDER, line=4.5).predict(
            MarketKind.TOTAL, features, {}
        )

        assert low_line.probability != pytest.approx(high_line.probability)
        assert low_line.probability > high_line.probability
        assert low_line.value == "positive"  # near-certain to have at least 1 goal
        assert high_line.value == "negative"  # unlikely to exceed 4.5 goals

    @pytest.mark.asyncio
    async def test_applies_mapping_weight_to_each_lambda(self):
        predictor = _predictor(PoissonGoalsThresholdMode.TOTAL_OVER_UNDER, line=2.5)

        output = await predictor.predict(
            MarketKind.TOTAL, features={HOME_KEY: 1.0, AWAY_KEY: 1.0},
            mapping_weights={HOME_KEY: 2.0, AWAY_KEY: 0.5},
        )

        assert output.feature_contributions == {HOME_KEY: pytest.approx(2.0), AWAY_KEY: pytest.approx(0.5)}


class TestTeamTotalOverUnder:
    @pytest.mark.asyncio
    async def test_home_side_uses_only_home_lambda(self):
        predictor = _predictor(PoissonGoalsThresholdMode.TEAM_TOTAL_OVER_UNDER, line=1.5, side="home", market_kind=MarketKind.TEAM_TOTAL)

        output = await predictor.predict(
            MarketKind.TEAM_TOTAL, features={HOME_KEY: 2.0, AWAY_KEY: 0.3}, mapping_weights={}
        )

        assert output.probability == pytest.approx(1.0 - _poisson_cdf(1, 2.0))

    @pytest.mark.asyncio
    async def test_away_side_uses_only_away_lambda(self):
        predictor = _predictor(PoissonGoalsThresholdMode.TEAM_TOTAL_OVER_UNDER, line=1.5, side="away", market_kind=MarketKind.TEAM_TOTAL)

        output = await predictor.predict(
            MarketKind.TEAM_TOTAL, features={HOME_KEY: 2.0, AWAY_KEY: 0.3}, mapping_weights={}
        )

        assert output.probability == pytest.approx(1.0 - _poisson_cdf(1, 0.3))

    @pytest.mark.asyncio
    async def test_home_and_away_sides_differ_for_asymmetric_teams(self):
        features = {HOME_KEY: 2.2, AWAY_KEY: 0.6}
        home = await _predictor(PoissonGoalsThresholdMode.TEAM_TOTAL_OVER_UNDER, line=1.5, side="home", market_kind=MarketKind.TEAM_TOTAL).predict(
            MarketKind.TEAM_TOTAL, features, {}
        )
        away = await _predictor(PoissonGoalsThresholdMode.TEAM_TOTAL_OVER_UNDER, line=1.5, side="away", market_kind=MarketKind.TEAM_TOTAL).predict(
            MarketKind.TEAM_TOTAL, features, {}
        )
        assert home.probability > away.probability


class TestCleanSheet:
    @pytest.mark.asyncio
    async def test_home_clean_sheet_is_pmf_zero_of_away_lambda(self):
        """Home Clean Sheet means the AWAY side fails to score."""
        predictor = _predictor(PoissonGoalsThresholdMode.CLEAN_SHEET, side="home", market_kind=MarketKind.BINARY)

        output = await predictor.predict(
            MarketKind.BINARY, features={HOME_KEY: 1.8, AWAY_KEY: 0.4}, mapping_weights={}
        )

        assert output.probability == pytest.approx(_poisson_pmf(0, 0.4))

    @pytest.mark.asyncio
    async def test_away_clean_sheet_is_pmf_zero_of_home_lambda(self):
        predictor = _predictor(PoissonGoalsThresholdMode.CLEAN_SHEET, side="away", market_kind=MarketKind.BINARY)

        output = await predictor.predict(
            MarketKind.BINARY, features={HOME_KEY: 1.8, AWAY_KEY: 0.4}, mapping_weights={}
        )

        assert output.probability == pytest.approx(_poisson_pmf(0, 1.8))

    @pytest.mark.asyncio
    async def test_lower_opponent_lambda_means_more_likely_clean_sheet(self):
        strong_defense = await _predictor(
            PoissonGoalsThresholdMode.CLEAN_SHEET, side="home", market_kind=MarketKind.BINARY
        ).predict(MarketKind.BINARY, {HOME_KEY: 1.5, AWAY_KEY: 0.2}, {})
        weak_defense = await _predictor(
            PoissonGoalsThresholdMode.CLEAN_SHEET, side="home", market_kind=MarketKind.BINARY
        ).predict(MarketKind.BINARY, {HOME_KEY: 1.5, AWAY_KEY: 2.5}, {})

        assert strong_defense.probability > weak_defense.probability


class TestWinToNil:
    @pytest.mark.asyncio
    async def test_matches_independent_joint_probability(self):
        predictor = _predictor(PoissonGoalsThresholdMode.WIN_TO_NIL, side="home", market_kind=MarketKind.BINARY)

        output = await predictor.predict(
            MarketKind.BINARY, features={HOME_KEY: 1.6, AWAY_KEY: 0.5}, mapping_weights={}
        )

        expected = _poisson_pmf(0, 0.5) * (1.0 - _poisson_pmf(0, 1.6))
        assert output.probability == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_win_to_nil_never_exceeds_clean_sheet_probability(self):
        """Winning to nil additionally requires scoring at least once — a strict subset of "kept
        a clean sheet," so its probability can never exceed the clean-sheet probability for the
        same side/lambdas."""
        features = {HOME_KEY: 1.3, AWAY_KEY: 0.9}
        clean_sheet = await _predictor(
            PoissonGoalsThresholdMode.CLEAN_SHEET, side="home", market_kind=MarketKind.BINARY
        ).predict(MarketKind.BINARY, features, {})
        win_to_nil = await _predictor(
            PoissonGoalsThresholdMode.WIN_TO_NIL, side="home", market_kind=MarketKind.BINARY
        ).predict(MarketKind.BINARY, features, {})

        assert win_to_nil.probability < clean_sheet.probability


@pytest.mark.asyncio
async def test_rejects_mismatched_market_kind():
    predictor = _predictor(PoissonGoalsThresholdMode.CLEAN_SHEET, market_kind=MarketKind.BINARY)

    with pytest.raises(UnsupportedMarketKindError):
        await predictor.predict(MarketKind.TOTAL, features={HOME_KEY: 1.0, AWAY_KEY: 1.0}, mapping_weights={})


@pytest.mark.asyncio
async def test_raises_when_a_required_feature_is_missing():
    predictor = _predictor(PoissonGoalsThresholdMode.TOTAL_OVER_UNDER)

    with pytest.raises(MissingExpectedGoalsFeatureError):
        await predictor.predict(MarketKind.TOTAL, features={HOME_KEY: 1.0}, mapping_weights={})


@pytest.mark.asyncio
async def test_zero_expected_goals_does_not_crash():
    predictor = _predictor(PoissonGoalsThresholdMode.TOTAL_OVER_UNDER, line=0.5)

    output = await predictor.predict(
        MarketKind.TOTAL, features={HOME_KEY: 0.0, AWAY_KEY: 0.0}, mapping_weights={}
    )

    assert 0.0 <= output.probability <= 1.0
    assert not math.isnan(output.probability)
