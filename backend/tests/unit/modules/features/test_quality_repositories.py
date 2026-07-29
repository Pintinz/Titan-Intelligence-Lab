from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.features.domain.entities import (
    FeatureComputationLog,
    FeatureConsumer,
    FeatureDefinition,
    FeatureUsageRecord,
    FeatureValidationReport,
    FeatureValue,
)
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureValidationReportId,
    FeatureValueId,
    QualityFlag,
    ValidationStatus,
)
from modules.features.infrastructure.persistence.repositories import (
    SqlAlchemyFeatureComputationLogRepository,
    SqlAlchemyFeatureConsumerRepository,
    SqlAlchemyFeatureDefinitionRepository,
    SqlAlchemyFeatureUsageRepository,
    SqlAlchemyFeatureValidationReportRepository,
    SqlAlchemyFeatureValueRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)
KEY = FeatureKey("football.team.form_index_last5")


async def _seed_definition(sqlite_session, **overrides) -> FeatureDefinition:
    repo = SqlAlchemyFeatureDefinitionRepository(session=sqlite_session)
    kwargs = dict(
        id=FeatureDefinitionId(uuid4()), feature_key=KEY, name="n", description="d", sport_code="football",
        category=FeatureCategory.ENGINEERED, formula="f(x)", data_type=FeatureDataType.FLOAT,
        owner="data-team", entity_type=EntityType.TEAM,
    )
    kwargs.update(overrides)
    definition = FeatureDefinition(**kwargs)
    await repo.upsert(definition)
    return definition


@pytest.mark.asyncio
async def test_definition_round_trip_preserves_source_provider_key(sqlite_session):
    await _seed_definition(sqlite_session, source_provider_key="api_football")
    await sqlite_session.commit()

    repo = SqlAlchemyFeatureDefinitionRepository(session=sqlite_session)
    fetched = await repo.get(KEY)

    assert fetched.source_provider_key == "api_football"


@pytest.mark.asyncio
async def test_value_list_all_recent_filters_by_since_and_spans_entities(sqlite_session):
    await _seed_definition(sqlite_session)
    value_repo = SqlAlchemyFeatureValueRepository(session=sqlite_session)

    await value_repo.record(
        FeatureValue(id=FeatureValueId(uuid4()), feature_key=KEY, entity_type=EntityType.TEAM, entity_id="a", as_of=T0, value=0.5)
    )
    await value_repo.record(
        FeatureValue(
            id=FeatureValueId(uuid4()), feature_key=KEY, entity_type=EntityType.TEAM, entity_id="b",
            as_of=T0 + timedelta(days=2), value=0.7,
        )
    )
    await sqlite_session.commit()

    all_values = await value_repo.list_all_recent(KEY)
    recent_only = await value_repo.list_all_recent(KEY, since=T0 + timedelta(days=1))

    assert len(all_values) == 2
    assert len(recent_only) == 1
    assert recent_only[0].entity_id == "b"


@pytest.mark.asyncio
async def test_validation_report_round_trip_and_latest(sqlite_session):
    await _seed_definition(sqlite_session)
    repo = SqlAlchemyFeatureValidationReportRepository(session=sqlite_session)

    older = FeatureValidationReport(
        id=FeatureValidationReportId(uuid4()), feature_key=KEY, validated_at=T0, sample_size=10,
        quality_score=80.0, freshness_score=90.0, reliability_score=100.0, completeness_score=70.0,
        missing_pct=5.0, outlier_pct=1.0, null_pct=5.0, invalid_pct=0.0, duplicate_pct=0.0, coverage_pct=None,
        status=ValidationStatus.PASSED, issues=(),
    )
    newer = FeatureValidationReport(
        id=FeatureValidationReportId(uuid4()), feature_key=KEY, validated_at=T0 + timedelta(days=1), sample_size=12,
        quality_score=40.0, freshness_score=50.0, reliability_score=60.0, completeness_score=30.0,
        missing_pct=20.0, outlier_pct=10.0, null_pct=20.0, invalid_pct=5.0, duplicate_pct=2.0, coverage_pct=60.0,
        status=ValidationStatus.WARNING, issues=("missing value rate 20.0% exceeds 10%",),
    )
    await repo.record(older)
    await repo.record(newer)
    await sqlite_session.commit()

    latest = await repo.get_latest(KEY)
    history = await repo.list_by_feature(KEY)

    # SQLite/aiosqlite drops tzinfo on read-back (unlike Postgres/asyncpg) — compare the naive
    # wall-clock value, per the same testing tradeoff as docs/decisions.md ADR-007.
    assert latest.validated_at.replace(tzinfo=timezone.utc) == T0 + timedelta(days=1)
    assert latest.status is ValidationStatus.WARNING
    assert latest.issues == ("missing value rate 20.0% exceeds 10%",)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_computation_log_round_trip(sqlite_session):
    await _seed_definition(sqlite_session)
    repo = SqlAlchemyFeatureComputationLogRepository(session=sqlite_session)

    await repo.record(FeatureComputationLog(feature_key=KEY, recorded_at=T0, duration_ms=150.0, memory_bytes=2048))
    await sqlite_session.commit()

    logs = await repo.list_since(KEY, T0 - timedelta(minutes=1))

    assert len(logs) == 1
    assert logs[0].duration_ms == pytest.approx(150.0)
    assert logs[0].memory_bytes == 2048


@pytest.mark.asyncio
async def test_consumer_round_trip_and_list(sqlite_session):
    await _seed_definition(sqlite_session)
    repo = SqlAlchemyFeatureConsumerRepository(session=sqlite_session)

    await repo.register(FeatureConsumer(feature_key=KEY, consumer_key="market-a", registered_at=T0))
    await repo.register(FeatureConsumer(feature_key=KEY, consumer_key="market-b", registered_at=T0))
    await sqlite_session.commit()

    consumers = await repo.list_by_feature(KEY)

    assert {c.consumer_key for c in consumers} == {"market-a", "market-b"}


@pytest.mark.asyncio
async def test_usage_record_round_trip_and_update(sqlite_session):
    await _seed_definition(sqlite_session)
    repo = SqlAlchemyFeatureUsageRepository(session=sqlite_session)

    record = FeatureUsageRecord(feature_key=KEY, window_key="2026-07-25", read_count=1)
    await repo.upsert(record)
    await sqlite_session.commit()

    fetched = await repo.get(KEY, "2026-07-25")
    fetched.read_count += 1
    await repo.upsert(fetched)
    await sqlite_session.commit()

    final = await repo.get(KEY, "2026-07-25")
    assert final.read_count == 2


@pytest.mark.asyncio
async def test_usage_list_since_filters_by_window_key(sqlite_session):
    await _seed_definition(sqlite_session)
    repo = SqlAlchemyFeatureUsageRepository(session=sqlite_session)

    await repo.upsert(FeatureUsageRecord(feature_key=KEY, window_key="2026-07-01", read_count=5))
    await repo.upsert(FeatureUsageRecord(feature_key=KEY, window_key="2026-07-25", read_count=3))
    await sqlite_session.commit()

    recent = await repo.list_since(KEY, "2026-07-20")

    assert len(recent) == 1
    assert recent[0].window_key == "2026-07-25"
