from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.intelligence.application.intelligence_monitoring_service import (
    IntelligenceMetricsRecorder,
    IntelligenceMonitoringService,
)
from modules.intelligence.domain.entities import (
    CommunityPost,
    IntelligenceSyncRun,
    NewsArticle,
    NewsSource,
    SourceReliabilityScore,
)
from modules.intelligence.domain.value_objects import (
    ArticleStatus,
    CommunityPlatform,
    CommunityPostId,
    IntelligenceChannelType,
    IntelligenceSyncRunId,
    NewsArticleId,
    NewsSourceId,
    NewsSourceType,
    SourceReliabilityId,
    SyncStatus,
    SyncTrigger,
    TrustLevel,
    VerificationStatus,
)
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyCommunityPostRepository,
    SqlAlchemyIntelligenceSyncRunRepository,
    SqlAlchemyNewsArticleRepository,
    SqlAlchemySourceReliabilityRepository,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _service(sqlite_session, recorder=None) -> IntelligenceMonitoringService:
    return IntelligenceMonitoringService(
        sync_runs=SqlAlchemyIntelligenceSyncRunRepository(session=sqlite_session),
        articles=SqlAlchemyNewsArticleRepository(session=sqlite_session),
        community_posts=SqlAlchemyCommunityPostRepository(session=sqlite_session),
        source_reliability=SqlAlchemySourceReliabilityRepository(session=sqlite_session),
        recorder=recorder or IntelligenceMetricsRecorder(),
    )


def _run(channel_key: str, status: SyncStatus, started_at: datetime, fetched=0, duplicate=0) -> IntelligenceSyncRun:
    return IntelligenceSyncRun(
        id=IntelligenceSyncRunId(uuid4()), channel_type=IntelligenceChannelType.NEWS, channel_key=channel_key,
        trigger=SyncTrigger.SCHEDULED, status=status, started_at=started_at, finished_at=started_at,
        items_fetched=fetched, items_duplicate=duplicate,
    )


def test_recorder_tracks_processing_time():
    recorder = IntelligenceMetricsRecorder()

    with recorder.time_ingestion():
        pass

    assert recorder.ingestion_run_count == 1
    assert recorder.avg_processing_seconds >= 0


def test_recorder_gemini_usage_counter():
    recorder = IntelligenceMetricsRecorder()

    recorder.record_gemini_call()
    recorder.record_gemini_call(3)

    assert recorder.gemini_call_count == 4


def test_recorder_extraction_accuracy_is_none_with_no_data():
    recorder = IntelligenceMetricsRecorder()

    assert recorder.extraction_accuracy is None


def test_recorder_extraction_accuracy_computed_from_outcomes():
    recorder = IntelligenceMetricsRecorder()
    recorder.record_extraction_outcome(True)
    recorder.record_extraction_outcome(True)
    recorder.record_extraction_outcome(False)

    assert recorder.extraction_accuracy == 2 / 3


async def test_ingestion_rate_counts_runs_within_window(sqlite_session):
    service = _service(sqlite_session)
    sync_runs = service.sync_runs
    await sync_runs.record(_run("source-1", SyncStatus.SUCCEEDED, T0))
    await sync_runs.record(_run("source-1", SyncStatus.SUCCEEDED, T0 - timedelta(days=10)))  # outside window
    await sqlite_session.commit()

    rate = await service.ingestion_rate(IntelligenceChannelType.NEWS, timedelta(hours=24), T0 + timedelta(hours=1))

    assert rate == 1 / 24


async def test_duplicate_rate_computed_across_runs(sqlite_session):
    service = _service(sqlite_session)
    await service.sync_runs.record(_run("source-1", SyncStatus.SUCCEEDED, T0, fetched=10, duplicate=2))
    await service.sync_runs.record(_run("source-2", SyncStatus.SUCCEEDED, T0, fetched=10, duplicate=3))
    await sqlite_session.commit()

    rate = await service.duplicate_rate(IntelligenceChannelType.NEWS)

    assert rate == 5 / 20


async def test_duplicate_rate_zero_with_no_runs(sqlite_session):
    service = _service(sqlite_session)

    assert await service.duplicate_rate(IntelligenceChannelType.NEWS) == 0.0


async def test_provider_health_reports_success_rate_and_consecutive_failures(sqlite_session):
    service = _service(sqlite_session)
    await service.sync_runs.record(_run("source-1", SyncStatus.FAILED, T0 + timedelta(hours=2)))
    await service.sync_runs.record(_run("source-1", SyncStatus.FAILED, T0 + timedelta(hours=1)))
    await service.sync_runs.record(_run("source-1", SyncStatus.SUCCEEDED, T0))
    await sqlite_session.commit()

    health = await service.provider_health(IntelligenceChannelType.NEWS)

    assert health["source-1"]["consecutive_failures"] == 2
    assert health["source-1"]["success_rate"] == 1 / 3


async def test_average_source_reliability_none_with_no_scores(sqlite_session):
    service = _service(sqlite_session)

    assert await service.average_source_reliability() is None


async def test_average_source_reliability_computed(sqlite_session):
    service = _service(sqlite_session)
    for score_value in (0.4, 0.8):
        await service.source_reliability.upsert(
            SourceReliabilityScore(
                id=SourceReliabilityId(uuid4()), source_id=NewsSourceId(uuid4()), reliability_score=score_value,
                historical_accuracy=0.5, bias_rating=0.0, verification_status=VerificationStatus.UNVERIFIED,
                trust_level=TrustLevel.UNVERIFIED, updated_at=T0,
            )
        )
    await sqlite_session.commit()

    assert await service.average_source_reliability() == pytest.approx(0.6)


async def test_snapshot_assembles_all_metrics(sqlite_session):
    recorder = IntelligenceMetricsRecorder()
    recorder.record_gemini_call(5)
    service = _service(sqlite_session, recorder=recorder)

    articles_repo = SqlAlchemyNewsArticleRepository(session=sqlite_session)
    await articles_repo.upsert(
        NewsArticle(
            id=NewsArticleId(uuid4()), source_id=NewsSourceId(uuid4()), title="t", url=f"https://x.com/{uuid4()}",
            content_hash=str(uuid4()), raw_text="body", published_at=T0, fetched_at=T0, status=ArticleStatus.ACTIVE,
        )
    )
    posts_repo = SqlAlchemyCommunityPostRepository(session=sqlite_session)
    await posts_repo.upsert(
        CommunityPost(
            id=CommunityPostId(uuid4()), platform=CommunityPlatform.REDDIT, external_id="p1", author_ref="fan1",
            text="great win", posted_at=T0, fetched_at=T0,
        )
    )
    await service.sync_runs.record(_run("source-1", SyncStatus.SUCCEEDED, T0, fetched=5, duplicate=1))
    await sqlite_session.commit()

    snapshot = await service.snapshot(T0 + timedelta(hours=1))

    assert snapshot.article_count == 1
    assert snapshot.community_post_count == 1
    assert snapshot.gemini_call_count == 5
    assert snapshot.news_ingestion_runs_recent == 1
    assert snapshot.news_duplicate_rate == 1 / 5
    assert snapshot.average_source_reliability is None
