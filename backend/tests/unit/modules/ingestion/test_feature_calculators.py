from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from modules.ingestion.application.data_validation_engine import ValidationResult
from modules.ingestion.application.feature_pipeline import FeaturePipeline
from modules.ingestion.infrastructure.feature_calculators import (
    AttendanceRatioCalculator,
    HoursUntilKickoffCalculator,
    ImpliedProbabilityCalculator,
    OddsOverroundCalculator,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_implied_probability_calculator_converts_decimal_odds():
    calculator = ImpliedProbabilityCalculator(feature_key="football.market.implied_probability_home", odds_key="home")

    value = await calculator.compute({"odds": {"home": 2.0}}, T0)

    assert value == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_implied_probability_calculator_returns_none_when_odds_missing():
    calculator = ImpliedProbabilityCalculator(feature_key="football.market.implied_probability_home", odds_key="home")

    assert await calculator.compute({"odds": {}}, T0) is None
    assert await calculator.compute({}, T0) is None


@pytest.mark.asyncio
async def test_implied_probability_calculator_rejects_invalid_odds():
    calculator = ImpliedProbabilityCalculator(feature_key="k", odds_key="home")

    assert await calculator.compute({"odds": {"home": 1.0}}, T0) is None
    assert await calculator.compute({"odds": {"home": "not-a-number"}}, T0) is None
    assert await calculator.compute({"odds": {"home": True}}, T0) is None


@pytest.mark.asyncio
async def test_odds_overround_calculator_computes_bookmaker_margin():
    calculator = OddsOverroundCalculator(feature_key="football.market.overround", odds_keys=("home", "draw", "away"))

    value = await calculator.compute({"odds": {"home": 2.0, "draw": 3.5, "away": 4.0}}, T0)

    expected = (1 / 2.0 + 1 / 3.5 + 1 / 4.0) - 1.0
    assert value == pytest.approx(expected)


@pytest.mark.asyncio
async def test_odds_overround_calculator_returns_none_when_any_outcome_missing():
    calculator = OddsOverroundCalculator(feature_key="k", odds_keys=("home", "draw", "away"))

    value = await calculator.compute({"odds": {"home": 2.0, "away": 4.0}}, T0)

    assert value is None


@pytest.mark.asyncio
async def test_hours_until_kickoff_calculator_with_datetime():
    calculator = HoursUntilKickoffCalculator()

    value = await calculator.compute({"scheduled_at": T0 + timedelta(hours=5)}, T0)

    assert value == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_hours_until_kickoff_calculator_with_iso_string():
    calculator = HoursUntilKickoffCalculator()

    value = await calculator.compute({"scheduled_at": (T0 + timedelta(hours=2)).isoformat()}, T0)

    assert value == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_hours_until_kickoff_calculator_negative_after_kickoff():
    calculator = HoursUntilKickoffCalculator()

    value = await calculator.compute({"scheduled_at": T0 - timedelta(hours=1)}, T0)

    assert value == pytest.approx(-1.0)


@pytest.mark.asyncio
async def test_hours_until_kickoff_calculator_handles_naive_datetime_from_sqlite_readback():
    calculator = HoursUntilKickoffCalculator()
    naive_scheduled_at = (T0 + timedelta(hours=3)).replace(tzinfo=None)

    value = await calculator.compute({"scheduled_at": naive_scheduled_at}, T0)

    assert value == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_hours_until_kickoff_calculator_returns_none_for_garbage():
    calculator = HoursUntilKickoffCalculator()

    assert await calculator.compute({"scheduled_at": "not-a-date"}, T0) is None
    assert await calculator.compute({}, T0) is None


@pytest.mark.asyncio
async def test_attendance_ratio_calculator_caps_at_one():
    calculator = AttendanceRatioCalculator()

    value = await calculator.compute({"attendance": 60000, "venue_capacity": 50000}, T0)

    assert value == 1.0


@pytest.mark.asyncio
async def test_attendance_ratio_calculator_normal_case():
    calculator = AttendanceRatioCalculator()

    value = await calculator.compute({"attendance": 25000, "venue_capacity": 50000}, T0)

    assert value == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_attendance_ratio_calculator_returns_none_for_zero_capacity():
    calculator = AttendanceRatioCalculator()

    assert await calculator.compute({"attendance": 100, "venue_capacity": 0}, T0) is None


@pytest.mark.asyncio
async def test_calculators_run_through_the_real_feature_pipeline():
    pipeline = FeaturePipeline()
    pipeline.register_calculator(
        ImpliedProbabilityCalculator(feature_key="football.market.implied_probability_home", odds_key="home")
    )
    pipeline.register_calculator(HoursUntilKickoffCalculator())

    raw = {"odds": {"home": 2.0}, "scheduled_at": T0 + timedelta(hours=10)}
    result = await pipeline.run(
        raw, T0, normalize=lambda r: r, validate=lambda r: ValidationResult.ok(), clean=lambda r: r
    )

    assert result.stage_reached == "calculated"
    assert dict(result.computed_features) == {
        "football.market.implied_probability_home": 0.5,
        "fixture.hours_until_kickoff": 10.0,
    }
