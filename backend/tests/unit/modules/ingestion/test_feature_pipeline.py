from datetime import datetime, timezone

import pytest

from modules.ingestion.application.data_validation_engine import ValidationResult
from modules.ingestion.application.feature_pipeline import FeaturePipeline

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


class _DoublingCalculator:
    feature_key = "doubled"

    async def compute(self, clean_record, now):
        return clean_record["value"] * 2


class _NoneCalculator:
    feature_key = "unavailable"

    async def compute(self, clean_record, now):
        return None


@pytest.mark.asyncio
async def test_pipeline_stops_at_validation_stage_when_invalid():
    pipeline = FeaturePipeline()

    result = await pipeline.run(
        {"value": -1}, T0,
        normalize=lambda raw: raw,
        validate=lambda rec: ValidationResult.failed("value must be positive"),
        clean=lambda rec: rec,
    )

    assert result.stage_reached == "validated"
    assert not result.validation.is_valid
    assert result.clean_record is None
    assert result.computed_features == ()


@pytest.mark.asyncio
async def test_pipeline_reaches_cleaned_stage_with_no_calculators():
    pipeline = FeaturePipeline()

    result = await pipeline.run(
        {"raw_value": 5}, T0,
        normalize=lambda raw: {"value": raw["raw_value"]},
        validate=lambda rec: ValidationResult.ok(),
        clean=lambda rec: {"value": rec["value"], "cleaned": True},
    )

    assert result.stage_reached == "cleaned"
    assert result.clean_record == {"value": 5, "cleaned": True}
    assert result.computed_features == ()


@pytest.mark.asyncio
async def test_pipeline_runs_registered_calculators():
    pipeline = FeaturePipeline()
    pipeline.register_calculator(_DoublingCalculator())

    result = await pipeline.run(
        {"value": 5}, T0,
        normalize=lambda raw: raw, validate=lambda rec: ValidationResult.ok(), clean=lambda rec: rec,
    )

    assert result.stage_reached == "calculated"
    assert result.computed_features == (("doubled", 10),)


@pytest.mark.asyncio
async def test_pipeline_skips_calculators_that_return_none():
    pipeline = FeaturePipeline()
    pipeline.register_calculator(_NoneCalculator())
    pipeline.register_calculator(_DoublingCalculator())

    result = await pipeline.run(
        {"value": 3}, T0,
        normalize=lambda raw: raw, validate=lambda rec: ValidationResult.ok(), clean=lambda rec: rec,
    )

    assert result.computed_features == (("doubled", 6),)


def test_register_calculator_rejects_duplicate_feature_key():
    pipeline = FeaturePipeline()
    pipeline.register_calculator(_DoublingCalculator())

    with pytest.raises(ValueError):
        pipeline.register_calculator(_DoublingCalculator())


@pytest.mark.asyncio
async def test_pipeline_with_no_calculators_and_no_features_registered_is_the_milestone5_default():
    """Milestone 5 scope: the pipeline exists and works, but ships with zero registered
    calculators — no sport-specific engineered features yet."""
    pipeline = FeaturePipeline()

    assert pipeline.calculators == []
