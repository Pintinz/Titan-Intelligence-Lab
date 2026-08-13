from __future__ import annotations

import pytest

from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.infrastructure.predictors.weighted_scoring import (
    UnsupportedMarketKindError,
    WeightedLinearPredictor,
    WeightedLogisticPredictor,
    WeightedOrdinalPredictor,
)


@pytest.mark.asyncio
async def test_logistic_predictor_positive_score_is_positive_value():
    predictor = WeightedLogisticPredictor()

    output = await predictor.predict(
        MarketKind.BINARY,
        features={"team_form": 0.8, "head_to_head": 0.5},
        mapping_weights={"team_form": 1.0, "head_to_head": 1.0},
    )

    assert output.raw_score == pytest.approx(1.3)
    assert output.value == "positive"
    assert 0.0 < output.probability < 1.0
    assert output.probability > 0.5
    assert output.feature_contributions == {"team_form": 0.8, "head_to_head": 0.5}


@pytest.mark.asyncio
async def test_logistic_predictor_negative_score_is_negative_value():
    predictor = WeightedLogisticPredictor()

    output = await predictor.predict(
        MarketKind.SEGMENT_WINNER, features={"team_form": -1.5}, mapping_weights={"team_form": 1.0}
    )

    assert output.value == "negative"
    assert output.probability < 0.5


@pytest.mark.asyncio
async def test_logistic_predictor_zero_score_is_calibrated_to_half():
    predictor = WeightedLogisticPredictor()

    output = await predictor.predict(MarketKind.BINARY, features={}, mapping_weights={})

    assert output.raw_score == 0.0
    assert output.probability == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_logistic_predictor_rejects_unsupported_market_kind():
    predictor = WeightedLogisticPredictor()

    with pytest.raises(UnsupportedMarketKindError):
        await predictor.predict(MarketKind.TOTAL, features={}, mapping_weights={})


@pytest.mark.asyncio
async def test_logistic_predictor_distribution_sums_to_one_and_matches_probability():
    predictor = WeightedLogisticPredictor()

    output = await predictor.predict(MarketKind.BINARY, features={"team_form": 0.8}, mapping_weights={})

    assert output.distribution["positive"] == pytest.approx(output.probability)
    assert output.distribution["negative"] == pytest.approx(1.0 - output.probability)
    assert sum(output.distribution.values()) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_logistic_predictor_applies_mapping_weight():
    predictor = WeightedLogisticPredictor()

    output = await predictor.predict(
        MarketKind.BINARY, features={"team_form": 2.0}, mapping_weights={"team_form": 0.5}
    )

    assert output.raw_score == pytest.approx(1.0)
    assert output.feature_contributions == {"team_form": 1.0}


@pytest.mark.asyncio
async def test_logistic_predictor_ignores_a_mapped_weight_for_a_feature_absent_from_features():
    """Milestone 8 — the exact scenario `is_required=False` structured-intel features hit on the
    four heuristic markets today: `mapping_weights` has an entry (from `FeatureMarketMapping`,
    required or not), but the feature key itself is absent from `features`
    (`PredictionContextBuilder`/`resolve_feature_snapshot` already filtered it out as an
    unavailable optional feature). Confirms it contributes exactly nothing to `raw_score` — not
    "weight × 0" — the same prediction as if the mapping didn't exist at all."""
    predictor = WeightedLogisticPredictor()

    with_absent_feature = await predictor.predict(
        MarketKind.BINARY,
        features={"team_form": 0.8},
        mapping_weights={"team_form": 1.0, "football.fixture.home_transfer_activity": 0.05},
    )
    without_the_mapping_at_all = await predictor.predict(
        MarketKind.BINARY, features={"team_form": 0.8}, mapping_weights={"team_form": 1.0},
    )

    assert with_absent_feature.raw_score == pytest.approx(without_the_mapping_at_all.raw_score)
    assert with_absent_feature.probability == pytest.approx(without_the_mapping_at_all.probability)
    assert "football.fixture.home_transfer_activity" not in with_absent_feature.feature_contributions


@pytest.mark.asyncio
async def test_linear_predictor_raw_score_is_predicted_value():
    predictor = WeightedLinearPredictor()

    output = await predictor.predict(
        MarketKind.PLAYER_PROP, features={"points_per_game_avg": 24.5, "pace_adjustment": 1.5}, mapping_weights={}
    )

    assert output.raw_score == pytest.approx(26.0)
    assert output.value == "positive"


@pytest.mark.asyncio
async def test_linear_predictor_supports_total_spread_team_total_race_to_correct_score():
    predictor = WeightedLinearPredictor()

    for kind in (
        MarketKind.SPREAD,
        MarketKind.TOTAL,
        MarketKind.TEAM_TOTAL,
        MarketKind.RACE_TO,
        MarketKind.CORRECT_SCORE,
    ):
        output = await predictor.predict(kind, features={"x": 1.0}, mapping_weights={"x": 2.0})
        assert output.raw_score == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_linear_predictor_emits_positive_negative_for_every_two_sided_kind():
    """Audit fix (2026-08-02): these kinds previously returned the raw formatted score
    (e.g. "-0.3000") as the user-facing verdict — meaningless to a fan and unmappable by
    outcome_label_mapper, which only recognizes "positive"/"negative". Every kind here has a
    genuine over/under-style two-sided verdict per this predictor's own docstring; CORRECT_SCORE
    (checked separately below) does not."""
    predictor = WeightedLinearPredictor()

    for kind in (MarketKind.SPREAD, MarketKind.TOTAL, MarketKind.TEAM_TOTAL, MarketKind.PLAYER_PROP, MarketKind.RACE_TO):
        positive = await predictor.predict(kind, features={"x": 1.0}, mapping_weights={"x": 1.0})
        assert positive.value == "positive"
        negative = await predictor.predict(kind, features={"x": -1.0}, mapping_weights={"x": 1.0})
        assert negative.value == "negative"


@pytest.mark.asyncio
async def test_linear_predictor_correct_score_keeps_the_raw_formatted_value():
    """CORRECT_SCORE predicts a specific scoreline, not a threshold — no real predictor exists
    for that shape yet, so it deliberately keeps the honest raw-number placeholder rather than
    fabricating a "positive"/"negative" verdict that would mean nothing for this market."""
    predictor = WeightedLinearPredictor()

    output = await predictor.predict(MarketKind.CORRECT_SCORE, features={"x": -1.0}, mapping_weights={"x": 1.0})

    assert output.value == "-1.0000"


@pytest.mark.asyncio
async def test_linear_predictor_rejects_unsupported_market_kind():
    predictor = WeightedLinearPredictor()

    with pytest.raises(UnsupportedMarketKindError):
        await predictor.predict(MarketKind.BINARY, features={}, mapping_weights={})


def test_ordinal_predictor_rejects_non_ordered_cutpoints():
    with pytest.raises(ValueError):
        WeightedOrdinalPredictor(away_cutpoint=0.5, home_cutpoint=0.5)

    with pytest.raises(ValueError):
        WeightedOrdinalPredictor(away_cutpoint=0.5, home_cutpoint=-0.5)


@pytest.mark.asyncio
async def test_ordinal_predictor_rejects_unsupported_market_kind():
    predictor = WeightedOrdinalPredictor()

    with pytest.raises(UnsupportedMarketKindError):
        await predictor.predict(MarketKind.BINARY, features={}, mapping_weights={})


@pytest.mark.asyncio
async def test_ordinal_predictor_probabilities_always_sum_to_one():
    predictor = WeightedOrdinalPredictor()

    for raw in (-5.0, -2.0, -0.85, 0.0, 0.5, 0.85, 3.0, 10.0):
        output = await predictor.predict(
            MarketKind.HOME_DRAW_AWAY, features={"x": raw}, mapping_weights={"x": 1.0}
        )
        outcomes = {"AWAY_WIN", "DRAW", "HOME_WIN"}
        assert output.value in outcomes
        # Reconstruct the three probabilities the same way predict() does, since PredictorOutput
        # only carries the winning outcome's probability.
        away = _sigmoid(-0.85 - output.raw_score)
        home_cdf = _sigmoid(0.85 - output.raw_score)
        draw = home_cdf - away
        home = 1.0 - home_cdf
        assert away + draw + home == pytest.approx(1.0)
        assert away >= 0.0
        assert draw >= 0.0
        assert home >= 0.0
        assert output.distribution == {"AWAY_WIN": pytest.approx(away), "DRAW": pytest.approx(draw), "HOME_WIN": pytest.approx(home)}
        assert output.distribution[output.value] == pytest.approx(output.probability)


@pytest.mark.asyncio
async def test_ordinal_predictor_draw_wins_plurality_at_symmetric_center():
    """At raw_score == 0, exactly between symmetric cutpoints, DRAW must be the single most likely
    outcome — the default cutpoints (0.85 magnitude, > ln(2)) exist specifically to guarantee this
    for an evenly-matched fixture, which a narrower gap (e.g. the pre-fix 0.5 default) cannot."""
    predictor = WeightedOrdinalPredictor()

    output = await predictor.predict(MarketKind.HOME_DRAW_AWAY, features={}, mapping_weights={})

    assert output.raw_score == 0.0
    assert output.value == "DRAW"
    assert output.probability == pytest.approx(0.4011, abs=1e-3)


@pytest.mark.asyncio
async def test_ordinal_predictor_strongly_favors_home_win_for_large_positive_score():
    predictor = WeightedOrdinalPredictor()

    output = await predictor.predict(
        MarketKind.HOME_DRAW_AWAY, features={"x": 5.0}, mapping_weights={"x": 1.0}
    )

    assert output.value == "HOME_WIN"
    assert output.probability > 0.9


@pytest.mark.asyncio
async def test_ordinal_predictor_strongly_favors_away_win_for_large_negative_score():
    predictor = WeightedOrdinalPredictor()

    output = await predictor.predict(
        MarketKind.HOME_DRAW_AWAY, features={"x": -5.0}, mapping_weights={"x": 1.0}
    )

    assert output.value == "AWAY_WIN"
    assert output.probability > 0.9


@pytest.mark.asyncio
async def test_ordinal_predictor_applies_mapping_weight_to_raw_score():
    predictor = WeightedOrdinalPredictor()

    output = await predictor.predict(
        MarketKind.HOME_DRAW_AWAY, features={"team_form": 1.0}, mapping_weights={"team_form": 3.0}
    )

    assert output.raw_score == pytest.approx(3.0)
    assert output.feature_contributions == {"team_form": 3.0}


@pytest.mark.asyncio
async def test_ordinal_predictor_custom_cutpoints_shift_draw_region():
    predictor = WeightedOrdinalPredictor(away_cutpoint=-1.5, home_cutpoint=1.5)

    # A raw_score that would favor HOME_WIN under the default cutpoints falls inside this wider
    # predictor's draw region instead — proves cutpoints are actually load-bearing, not decorative.
    output = await predictor.predict(
        MarketKind.HOME_DRAW_AWAY, features={"x": 1.0}, mapping_weights={"x": 1.0}
    )

    assert output.value == "DRAW"


def _sigmoid(x: float) -> float:
    import math

    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)
