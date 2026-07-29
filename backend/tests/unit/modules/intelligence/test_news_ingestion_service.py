from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.intelligence.application.news_ingestion_service import NewsIngestionService, content_hash
from modules.intelligence.domain.entities import NewsSource
from modules.intelligence.domain.value_objects import NewsSourceId, NewsSourceType, SyncStatus, SyncTrigger
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyIntelligenceSyncCheckpointRepository,
    SqlAlchemyIntelligenceSyncRunRepository,
    SqlAlchemyNewsArticleRepository,
    SqlAlchemyNewsSourceRepository,
)
from modules.intelligence.infrastructure.providers.mock_news_provider import MockNewsProvider
from modules.intelligence.ports.news_provider import RawArticleRecord

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _service(sqlite_session, provider=None):
    sources = SqlAlchemyNewsSourceRepository(session=sqlite_session)
    articles = SqlAlchemyNewsArticleRepository(session=sqlite_session)
    checkpoints = SqlAlchemyIntelligenceSyncCheckpointRepository(session=sqlite_session)
    sync_runs = SqlAlchemyIntelligenceSyncRunRepository(session=sqlite_session)
    providers = {"rss_feed": provider} if provider else {}
    return NewsIngestionService(
        sources=sources, articles=articles, checkpoints=checkpoints, sync_runs=sync_runs, providers=providers
    ), sources


async def _seed_source(sources, sqlite_session) -> NewsSource:
    source = NewsSource(
        id=NewsSourceId(uuid4()), source_type=NewsSourceType.RSS_FEED, name="Mock Feed",
        url="https://example.com/feed.xml", is_official=True, created_at=T0,
    )
    await sources.upsert(source)
    await sqlite_session.commit()
    return source


def test_content_hash_is_stable_and_case_insensitive():
    a = content_hash("Big Transfer News", "Player signs for club.")
    b = content_hash("big transfer news", "Player   signs for club.")

    assert a == b


def test_content_hash_differs_for_different_content():
    assert content_hash("A", "B") != content_hash("A", "C")


async def test_sync_source_creates_new_articles(sqlite_session):
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(
                external_ref="1", title="Striker Signs New Deal", url="https://example.com/1",
                body="The striker has signed a new contract.", published_at=T0,
            ),
        )
    )
    service, sources = _service(sqlite_session, provider)
    source = await _seed_source(sources, sqlite_session)

    run = await service.sync_source(source.id, T0 + timedelta(minutes=1))
    await sqlite_session.commit()

    assert run.status == SyncStatus.SUCCEEDED
    assert run.items_created == 1
    assert run.items_fetched == 1


async def test_sync_source_deduplicates_by_content_hash(sqlite_session):
    article = RawArticleRecord(
        external_ref="1", title="Same Story", url="https://example.com/a",
        body="Identical content.", published_at=T0,
    )
    republished = RawArticleRecord(
        external_ref="2", title="Same Story", url="https://example.com/b",
        body="Identical content.", published_at=T0,
    )
    provider = MockNewsProvider(fixed_articles=(article, republished))
    service, sources = _service(sqlite_session, provider)
    source = await _seed_source(sources, sqlite_session)

    run = await service.sync_source(source.id, T0 + timedelta(minutes=1))
    await sqlite_session.commit()

    assert run.items_created == 1
    assert run.items_duplicate == 1


async def test_sync_source_rejects_empty_body(sqlite_session):
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(external_ref="1", title="Headline Only", url="https://example.com/1", body="", published_at=T0),
        )
    )
    service, sources = _service(sqlite_session, provider)
    source = await _seed_source(sources, sqlite_session)

    run = await service.sync_source(source.id, T0 + timedelta(minutes=1))
    await sqlite_session.commit()

    assert run.items_rejected == 1
    assert run.status == SyncStatus.PARTIAL


async def test_sync_source_advances_checkpoint_incrementally(sqlite_session):
    early = RawArticleRecord(
        external_ref="1", title="Early Story", url="https://example.com/early",
        body="Old news.", published_at=T0,
    )
    late = RawArticleRecord(
        external_ref="2", title="Late Story", url="https://example.com/late",
        body="Fresh news.", published_at=T0 + timedelta(days=1),
    )
    provider = MockNewsProvider(fixed_articles=(early, late))
    service, sources = _service(sqlite_session, provider)
    source = await _seed_source(sources, sqlite_session)

    first_run = await service.sync_source(source.id, T0 + timedelta(hours=1))
    await sqlite_session.commit()
    second_run = await service.sync_source(source.id, T0 + timedelta(days=2))
    await sqlite_session.commit()

    assert first_run.items_fetched == 2  # since=None on first sync: everything
    assert second_run.items_fetched == 1  # since=checkpoint: only the late story


async def test_sync_source_unknown_source_raises(sqlite_session):
    service, _sources = _service(sqlite_session)

    try:
        await service.sync_source(NewsSourceId(uuid4()), T0)
        assert False, "expected ValueError"
    except ValueError:
        pass


async def test_sync_source_provider_failure_marks_run_failed(sqlite_session):
    class _FailingProvider:
        provider_key = "failing"

        async def fetch_articles(self, source_url, since=None, cursor=None):
            raise RuntimeError("provider unreachable")

    service, sources = _service(sqlite_session, _FailingProvider())
    source = await _seed_source(sources, sqlite_session)

    run = await service.sync_source(source.id, T0, trigger=SyncTrigger.MANUAL)
    await sqlite_session.commit()

    assert run.status == SyncStatus.FAILED
    assert "provider unreachable" in run.error_message

    checkpoint = await service.checkpoints.get(run.channel_type, run.channel_key)
    assert checkpoint.consecutive_failures == 1


async def test_sync_source_missing_provider_raises(sqlite_session):
    service, sources = _service(sqlite_session)  # no provider registered for rss_feed
    source = await _seed_source(sources, sqlite_session)

    try:
        await service.sync_source(source.id, T0)
        assert False, "expected ValueError"
    except ValueError:
        pass
