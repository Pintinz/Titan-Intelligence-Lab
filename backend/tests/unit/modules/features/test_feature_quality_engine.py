from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.features.application.feature_quality_engine import FeatureNotFoundError, FeatureQualityEngine
from modules.features.domain.entities import FeatureDefinition, FeatureValue
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
    FeatureValueId,
    QualityFlag,
    ValidationStatus,
)

T0 = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
KEY = FeatureKey("football.team.form_index_last5")


def _definition(**overrides) -> FeatureDefinition:
    kwargs = dict(
        id=FeatureDefinitionId(uuid4()),
        feature_key=KEY,
        name="Form index",
        description="d",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="f(x)",
        data_type=FeatureDataType.FLOAT,
        owner="data-team",
        entity_type=EntityType.TEAM,
        status=FeatureStatus.ACTIVE,
        online_ttl_seconds=3600,
    )
    kwargs.update(overrides)
    return FeatureDefinition(**kwargs)


def _value(entity_id="team-1", as_of=T0, value=0.5, flags=(QualityFlag.OK,)) -> FeatureValue:
    return FeatureValue(
        id=FeatureValueId(uuid4()), feature_key=KEY, entity_type=EntityType.TEAM, entity_id=entity_id,
        as_of=as_of, value=value, quality_flags=flags,
    )


@pytest.fixture
def engine(definition_repo, value_repo, validation_report_repo, computation_log_repo, consumer_repo, usage_repo, provider_reliability_port):
    return FeatureQualityEngine(
        definitions=definition_repo, values=value_repo, reports=validation_report_repo,
        computation_logs=computation_log_repo, consumers=consumer_repo, usage=usage_repo,
        provider_reliability_port=provider_reliability_port,
    )


@pytest.mark.asyncio
async def test_unknown_feature_raises_not_found(engine):
    with pytest.raises(FeatureNotFoundError):
        await engine.quality_snapshot("does.not.exist", T0)


# -- quality_snapshot ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quality_snapshot_with_no_values_is_all_none(engine, definition_repo):
    await definition_repo.upsert(_definition())

    snapshot = await engine.quality_snapshot(KEY.value, T0)

    assert snapshot.sample_size == 0
    assert snapshot.quality_score is None
    assert snapshot.missing_pct is None


@pytest.mark.asyncio
async def test_perfect_data_yields_full_reliability_and_no_bad_pct(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    for i in range(10):
        await value_repo.record(_value(entity_id=f"team-{i}", as_of=T0))

    snapshot = await engine.quality_snapshot(KEY.value, T0 + timedelta(minutes=1))

    assert snapshot.sample_size == 10
    assert snapshot.reliability_score == pytest.approx(100.0)
    assert snapshot.missing_pct == pytest.approx(0.0)
    assert snapshot.outlier_pct == pytest.approx(0.0)
    assert snapshot.invalid_pct == pytest.approx(0.0)
    assert snapshot.duplicate_pct == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_missing_and_null_pct_are_equal_today(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    for i in range(4):
        await value_repo.record(_value(entity_id=f"team-{i}", flags=(QualityFlag.MISSING_IMPUTED,)))
    for i in range(6):
        await value_repo.record(_value(entity_id=f"team-{i+4}"))

    snapshot = await engine.quality_snapshot(KEY.value, T0 + timedelta(minutes=1))

    assert snapshot.missing_pct == pytest.approx(40.0)
    assert snapshot.null_pct == snapshot.missing_pct


@pytest.mark.asyncio
async def test_outlier_and_invalid_pct(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    await value_repo.record(_value(entity_id="a", flags=(QualityFlag.OUT_OF_RANGE,)))
    await value_repo.record(_value(entity_id="b", flags=(QualityFlag.TYPE_MISMATCH,)))
    await value_repo.record(_value(entity_id="c"))
    await value_repo.record(_value(entity_id="d"))

    snapshot = await engine.quality_snapshot(KEY.value, T0 + timedelta(minutes=1))

    assert snapshot.outlier_pct == pytest.approx(25.0)
    assert snapshot.invalid_pct == pytest.approx(25.0)


@pytest.mark.asyncio
async def test_duplicate_pct_detects_same_entity_and_timestamp(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    await value_repo.record(_value(entity_id="a", as_of=T0))
    await value_repo.record(_value(entity_id="a", as_of=T0))  # duplicate write
    await value_repo.record(_value(entity_id="b", as_of=T0))

    snapshot = await engine.quality_snapshot(KEY.value, T0 + timedelta(minutes=1))

    assert snapshot.duplicate_pct == pytest.approx(100 / 3, abs=0.01)


@pytest.mark.asyncio
async def test_coverage_pct_uses_total_expected_entities(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    for i in range(3):
        await value_repo.record(_value(entity_id=f"team-{i}"))

    with_total = await engine.quality_snapshot(KEY.value, T0 + timedelta(minutes=1), total_expected_entities=10)
    without_total = await engine.quality_snapshot(KEY.value, T0 + timedelta(minutes=1))

    assert with_total.coverage_pct == pytest.approx(30.0)
    assert without_total.coverage_pct is None


@pytest.mark.asyncio
async def test_completeness_score_falls_back_to_missing_pct_without_total(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    await value_repo.record(_value(entity_id="a", flags=(QualityFlag.MISSING_IMPUTED,)))
    await value_repo.record(_value(entity_id="b"))
    await value_repo.record(_value(entity_id="c"))
    await value_repo.record(_value(entity_id="d"))

    snapshot = await engine.quality_snapshot(KEY.value, T0 + timedelta(minutes=1))

    assert snapshot.completeness_score == pytest.approx(100 - 25.0)


@pytest.mark.asyncio
async def test_freshness_score_full_within_ttl(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition(online_ttl_seconds=3600))
    await value_repo.record(_value(as_of=T0))

    snapshot = await engine.quality_snapshot(KEY.value, T0 + timedelta(minutes=30))

    assert snapshot.freshness_score == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_freshness_score_decays_after_ttl(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition(online_ttl_seconds=3600))  # 1h ttl, stale at 5h
    await value_repo.record(_value(as_of=T0))

    # 3 hours old: 2h past ttl out of 4h decay range -> ~50%
    snapshot = await engine.quality_snapshot(KEY.value, T0 + timedelta(hours=3))

    assert 0 < snapshot.freshness_score < 100
    assert snapshot.freshness_score == pytest.approx(50.0, abs=1.0)


@pytest.mark.asyncio
async def test_freshness_score_zero_when_very_stale(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition(online_ttl_seconds=3600))
    await value_repo.record(_value(as_of=T0))

    snapshot = await engine.quality_snapshot(KEY.value, T0 + timedelta(hours=10))

    assert snapshot.freshness_score == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_quality_score_is_high_for_healthy_feature(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    for i in range(10):
        await value_repo.record(_value(entity_id=f"team-{i}", as_of=T0))

    snapshot = await engine.quality_snapshot(KEY.value, T0 + timedelta(minutes=1))

    assert snapshot.quality_score > 95


@pytest.mark.asyncio
async def test_quality_score_is_low_for_unhealthy_feature(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition(online_ttl_seconds=60))
    for i in range(10):
        await value_repo.record(
            _value(entity_id=f"team-{i}", as_of=T0 - timedelta(days=1), flags=(QualityFlag.MISSING_IMPUTED,))
        )

    snapshot = await engine.quality_snapshot(KEY.value, T0)

    assert snapshot.quality_score < 30


# -- validation reports ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_validation_fails_with_no_data(engine, definition_repo):
    await definition_repo.upsert(_definition())

    report = await engine.run_validation(KEY.value, T0)

    assert report.status is ValidationStatus.FAILED
    assert report.sample_size == 0
    assert any("no feature values" in issue for issue in report.issues)


@pytest.mark.asyncio
async def test_run_validation_passes_for_clean_data(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    for i in range(10):
        await value_repo.record(_value(entity_id=f"team-{i}", as_of=T0))

    report = await engine.run_validation(KEY.value, T0 + timedelta(minutes=1))

    assert report.status is ValidationStatus.PASSED
    assert report.issues == ()


@pytest.mark.asyncio
async def test_run_validation_warns_on_elevated_missing_rate(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    for i in range(2):
        await value_repo.record(_value(entity_id=f"missing-{i}", flags=(QualityFlag.MISSING_IMPUTED,)))
    for i in range(8):
        await value_repo.record(_value(entity_id=f"ok-{i}"))

    report = await engine.run_validation(KEY.value, T0 + timedelta(minutes=1))

    assert report.status is ValidationStatus.WARNING
    assert any("missing value rate" in issue for issue in report.issues)


@pytest.mark.asyncio
async def test_validation_report_is_persisted_and_queryable(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    await value_repo.record(_value())

    await engine.run_validation(KEY.value, T0)
    await engine.run_validation(KEY.value, T0 + timedelta(days=1))

    latest = await engine.get_latest_validation(KEY.value)
    history = await engine.list_validation_history(KEY.value)

    assert latest.validated_at == T0 + timedelta(days=1)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_get_latest_validation_none_when_never_validated(engine, definition_repo):
    await definition_repo.upsert(_definition())

    assert await engine.get_latest_validation(KEY.value) is None


# -- provider reliability ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_reliability_none_without_source_provider(engine, definition_repo):
    await definition_repo.upsert(_definition(source_provider_key=None))

    assert await engine.provider_reliability(KEY.value, T0) is None


@pytest.mark.asyncio
async def test_provider_reliability_delegates_to_port(engine, definition_repo, provider_reliability_port):
    await definition_repo.upsert(_definition(source_provider_key="api_football"))
    provider_reliability_port.scores["api_football"] = 87.5

    score = await engine.provider_reliability(KEY.value, T0)

    assert score == pytest.approx(87.5)


@pytest.mark.asyncio
async def test_provider_reliability_none_without_port(definition_repo, value_repo, validation_report_repo, computation_log_repo, consumer_repo, usage_repo):
    engine = FeatureQualityEngine(
        definitions=definition_repo, values=value_repo, reports=validation_report_repo,
        computation_logs=computation_log_repo, consumers=consumer_repo, usage=usage_repo,
        provider_reliability_port=None,
    )
    await definition_repo.upsert(_definition(source_provider_key="api_football"))

    assert await engine.provider_reliability(KEY.value, T0) is None


# -- computation cost -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_computation_cost_with_no_logs(engine, definition_repo):
    await definition_repo.upsert(_definition())

    cost = await engine.computation_cost(KEY.value, T0)

    assert cost.sample_size == 0
    assert cost.average_duration_ms is None
    assert cost.cost_score is None


@pytest.mark.asyncio
async def test_computation_cost_averages_duration_and_memory(engine, definition_repo):
    await definition_repo.upsert(_definition())
    await engine.record_computation(KEY.value, T0, duration_ms=100, memory_bytes=1000)
    await engine.record_computation(KEY.value, T0, duration_ms=300, memory_bytes=3000)

    cost = await engine.computation_cost(KEY.value, T0 + timedelta(days=1))

    assert cost.sample_size == 2
    assert cost.average_duration_ms == pytest.approx(200.0)
    assert cost.average_memory_bytes == pytest.approx(2000.0)


@pytest.mark.asyncio
async def test_computation_cost_score_caps_at_100(engine, definition_repo):
    await definition_repo.upsert(_definition())
    await engine.record_computation(KEY.value, T0, duration_ms=50_000)  # way above the 5000ms ceiling

    cost = await engine.computation_cost(KEY.value, T0 + timedelta(minutes=1))

    assert cost.cost_score == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_computation_cost_handles_logs_without_memory(engine, definition_repo):
    await definition_repo.upsert(_definition())
    await engine.record_computation(KEY.value, T0, duration_ms=100, memory_bytes=None)

    cost = await engine.computation_cost(KEY.value, T0 + timedelta(minutes=1))

    assert cost.average_memory_bytes is None


# -- storage size -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_size_none_with_no_values(engine, definition_repo):
    await definition_repo.upsert(_definition())

    assert await engine.storage_size_bytes(KEY.value, T0) is None


@pytest.mark.asyncio
async def test_storage_size_grows_with_more_values(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    await value_repo.record(_value(entity_id="a"))

    one_value = await engine.storage_size_bytes(KEY.value, T0 + timedelta(minutes=1))

    await value_repo.record(_value(entity_id="b"))
    two_values = await engine.storage_size_bytes(KEY.value, T0 + timedelta(minutes=1))

    assert one_value > 0
    assert two_values > one_value


# -- consumers --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_and_list_consumers(engine, definition_repo):
    await definition_repo.upsert(_definition())

    await engine.register_consumer(KEY.value, "football.match_result.v1", T0)
    consumers = await engine.list_consumers(KEY.value)

    assert len(consumers) == 1
    assert consumers[0].consumer_key == "football.match_result.v1"


@pytest.mark.asyncio
async def test_register_consumer_is_idempotent(engine, definition_repo):
    await definition_repo.upsert(_definition())

    await engine.register_consumer(KEY.value, "market-a", T0)
    await engine.register_consumer(KEY.value, "market-a", T0 + timedelta(days=1))

    consumers = await engine.list_consumers(KEY.value)
    assert len(consumers) == 1


# -- usage frequency --------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_frequency_accumulates_within_window(engine, definition_repo):
    await definition_repo.upsert(_definition())
    for _ in range(3):
        await engine.record_usage(KEY.value, T0)
    await engine.record_usage(KEY.value, T0 + timedelta(days=1))

    frequency = await engine.usage_frequency(KEY.value, T0 + timedelta(days=1), window_days=7)

    assert frequency == 4


@pytest.mark.asyncio
async def test_usage_frequency_excludes_outside_window(engine, definition_repo):
    await definition_repo.upsert(_definition())
    await engine.record_usage(KEY.value, T0 - timedelta(days=30))
    await engine.record_usage(KEY.value, T0)

    frequency = await engine.usage_frequency(KEY.value, T0, window_days=7)

    assert frequency == 1


# -- deprecation warning ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deprecation_warning_for_deprecated_feature(engine, definition_repo):
    await definition_repo.upsert(_definition(status=FeatureStatus.DEPRECATED, deprecated_at=T0))

    warning = await engine.deprecation_warning(KEY.value, T0 + timedelta(days=1))

    assert warning is not None
    assert "deprecated" in warning.lower()


@pytest.mark.asyncio
async def test_deprecation_warning_advisory_on_low_quality(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    for i in range(10):
        await value_repo.record(_value(entity_id=f"t{i}", flags=(QualityFlag.MISSING_IMPUTED,)))
    await engine.run_validation(KEY.value, T0 + timedelta(minutes=1))

    warning = await engine.deprecation_warning(KEY.value, T0 + timedelta(minutes=2))

    assert warning is not None
    assert "quality score" in warning.lower()


@pytest.mark.asyncio
async def test_no_deprecation_warning_for_healthy_active_feature(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    for i in range(10):
        await value_repo.record(_value(entity_id=f"t{i}"))
    await engine.run_validation(KEY.value, T0 + timedelta(minutes=1))

    warning = await engine.deprecation_warning(KEY.value, T0 + timedelta(minutes=2))

    assert warning is None


# -- composite health report ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_report_assembles_everything(engine, definition_repo, value_repo):
    await definition_repo.upsert(_definition(source_provider_key="api_football"))
    for i in range(5):
        await value_repo.record(_value(entity_id=f"t{i}"))
    await engine.record_computation(KEY.value, T0, duration_ms=200)
    await engine.register_consumer(KEY.value, "market-a", T0)
    await engine.record_usage(KEY.value, T0)

    report = await engine.health_report(KEY.value, T0 + timedelta(minutes=1))

    assert report.feature_key == KEY.value
    assert report.status == "active"
    assert report.quality.sample_size == 5
    assert report.consumer_count == 1
    assert report.usage_last_7_days == 1
    assert report.storage_size_bytes is not None
    assert report.computation_cost.sample_size == 1
