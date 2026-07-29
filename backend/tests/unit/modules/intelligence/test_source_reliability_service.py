from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.intelligence.application.source_reliability_service import SourceReliabilityService
from modules.intelligence.domain.entities import NewsSource
from modules.intelligence.domain.value_objects import NewsSourceId, NewsSourceType, TrustLevel, VerificationStatus
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemySourceReliabilityRepository

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _source(is_official: bool) -> NewsSource:
    return NewsSource(
        id=NewsSourceId(uuid4()), source_type=NewsSourceType.OFFICIAL_CLUB_WEBSITE if is_official else NewsSourceType.RSS_FEED,
        name="Test Source", url="https://example.com", is_official=is_official, created_at=T0,
    )


def _service(sqlite_session) -> SourceReliabilityService:
    return SourceReliabilityService(reliability=SqlAlchemySourceReliabilityRepository(session=sqlite_session))


async def test_get_or_initialize_creates_default_score(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=False)

    score = await service.get_or_initialize(source, T0)
    await sqlite_session.commit()

    assert score.reliability_score == 0.5
    assert score.historical_accuracy == 0.5
    assert score.bias_rating == 0.0
    assert score.verification_status == VerificationStatus.UNVERIFIED
    assert score.trust_level == TrustLevel.UNVERIFIED


async def test_get_or_initialize_marks_official_source_verified(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=True)

    score = await service.get_or_initialize(source, T0)
    await sqlite_session.commit()

    assert score.verification_status == VerificationStatus.VERIFIED
    assert score.trust_level == TrustLevel.OFFICIAL


async def test_get_or_initialize_is_idempotent(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=False)

    first = await service.get_or_initialize(source, T0)
    await sqlite_session.commit()
    second = await service.get_or_initialize(source, T0 + timedelta(days=1))
    await sqlite_session.commit()

    assert first.id == second.id
    # SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — compare naively.
    assert second.updated_at.replace(tzinfo=None) == T0.replace(tzinfo=None)  # not re-initialized


async def test_record_outcome_increases_reliability_on_accurate_report(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=False)
    await service.get_or_initialize(source, T0)
    await sqlite_session.commit()

    updated = await service.record_outcome(source, was_accurate=True, now=T0 + timedelta(days=1))
    await sqlite_session.commit()

    assert updated.reliability_score > 0.5
    assert updated.historical_accuracy > 0.5


async def test_record_outcome_decreases_reliability_on_inaccurate_report(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=False)
    await service.get_or_initialize(source, T0)
    await sqlite_session.commit()

    updated = await service.record_outcome(source, was_accurate=False, now=T0 + timedelta(days=1))
    await sqlite_session.commit()

    assert updated.reliability_score < 0.5
    assert updated.historical_accuracy < 0.5


async def test_record_outcome_bootstraps_when_uninitialized(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=False)

    updated = await service.record_outcome(source, was_accurate=True, now=T0)
    await sqlite_session.commit()

    assert updated.reliability_score > 0.5


async def test_repeated_inaccurate_outcomes_push_trust_level_to_unreliable(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=False)
    await service.get_or_initialize(source, T0)
    await sqlite_session.commit()

    score = None
    for i in range(10):
        score = await service.record_outcome(source, was_accurate=False, now=T0 + timedelta(days=i))
        await sqlite_session.commit()

    assert score.trust_level == TrustLevel.UNRELIABLE
    assert score.reliability_score < 0.3


async def test_repeated_accurate_outcomes_push_trust_level_up(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=False)
    await service.get_or_initialize(source, T0)
    await sqlite_session.commit()

    score = None
    for i in range(10):
        score = await service.record_outcome(source, was_accurate=True, now=T0 + timedelta(days=i))
        await sqlite_session.commit()

    assert score.trust_level == TrustLevel.VERIFIED
    assert score.reliability_score >= 0.7


async def test_set_bias_rating_clamps_to_valid_range(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=False)
    await service.get_or_initialize(source, T0)
    await sqlite_session.commit()

    updated = await service.set_bias_rating(source, 5.0, T0 + timedelta(days=1))
    await sqlite_session.commit()

    assert updated.bias_rating == 1.0


async def test_set_bias_rating_clamps_negative_range(sqlite_session):
    service = _service(sqlite_session)
    source = _source(is_official=False)

    updated = await service.set_bias_rating(source, -5.0, T0)
    await sqlite_session.commit()

    assert updated.bias_rating == -1.0
