"""Direct repository tests filling gaps not already exercised indirectly through the
application-service test files (e.g. plain `get`/`get_by_*`/list-with-filter methods no service
happens to call)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.intelligence.domain.entities import (
    CommunityPost,
    CommunityTopic,
    ImpactScore,
    IntelligenceSyncRun,
    NewsArticle,
    NewsEvent,
    NewsSource,
    Summary,
)
from modules.intelligence.domain.value_objects import (
    ArticleStatus,
    CommunityPlatform,
    CommunityPostId,
    CommunityTopicId,
    ImpactScoreId,
    IntelligenceChannelType,
    IntelligenceSyncRunId,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
    NewsSourceType,
    SummaryId,
    SummaryType,
    SyncStatus,
    SyncTrigger,
)
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyCommunityPostRepository,
    SqlAlchemyCommunityTopicRepository,
    SqlAlchemyImpactScoreRepository,
    SqlAlchemyIntelligenceSyncRunRepository,
    SqlAlchemyNewsArticleRepository,
    SqlAlchemyNewsEventRepository,
    SqlAlchemyNewsSourceRepository,
    SqlAlchemySummaryRepository,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


async def test_news_source_get_by_url(sqlite_session):
    repo = SqlAlchemyNewsSourceRepository(session=sqlite_session)
    source = NewsSource(
        id=NewsSourceId(uuid4()), source_type=NewsSourceType.RSS_FEED, name="Feed", url="https://a.example.com",
        created_at=T0,
    )
    await repo.upsert(source)
    await sqlite_session.commit()

    found = await repo.get_by_url("https://a.example.com")
    missing = await repo.get_by_url("https://missing.example.com")

    assert found is not None and found.id == source.id
    assert missing is None


async def test_news_source_list_by_type_and_list_all(sqlite_session):
    repo = SqlAlchemyNewsSourceRepository(session=sqlite_session)
    await repo.upsert(
        NewsSource(id=NewsSourceId(uuid4()), source_type=NewsSourceType.RSS_FEED, name="A", url="https://a.example.com")
    )
    await repo.upsert(
        NewsSource(
            id=NewsSourceId(uuid4()), source_type=NewsSourceType.PRESS_RELEASE, name="B", url="https://b.example.com"
        )
    )
    await sqlite_session.commit()

    rss_only = await repo.list_by_type(NewsSourceType.RSS_FEED)
    everything = await repo.list_all()

    assert len(rss_only) == 1
    assert len(everything) == 2


async def test_news_article_get_by_id(sqlite_session):
    repo = SqlAlchemyNewsArticleRepository(session=sqlite_session)
    article = NewsArticle(
        id=NewsArticleId(uuid4()), source_id=NewsSourceId(uuid4()), title="t", url="https://x.example.com/1",
        content_hash=str(uuid4()), raw_text="body", published_at=T0, fetched_at=T0, status=ArticleStatus.ACTIVE,
    )
    await repo.upsert(article)
    await sqlite_session.commit()

    found = await repo.get(article.id)
    missing = await repo.get(NewsArticleId(uuid4()))

    assert found is not None and found.title == "t"
    assert missing is None


async def test_news_article_search_filters_by_source_id(sqlite_session):
    repo = SqlAlchemyNewsArticleRepository(session=sqlite_session)
    source_a, source_b = NewsSourceId(uuid4()), NewsSourceId(uuid4())
    await repo.upsert(
        NewsArticle(
            id=NewsArticleId(uuid4()), source_id=source_a, title="From A", url="https://x.example.com/a",
            content_hash=str(uuid4()), raw_text="body", published_at=T0, fetched_at=T0,
        )
    )
    await repo.upsert(
        NewsArticle(
            id=NewsArticleId(uuid4()), source_id=source_b, title="From B", url="https://x.example.com/b",
            content_hash=str(uuid4()), raw_text="body", published_at=T0, fetched_at=T0,
        )
    )
    await sqlite_session.commit()

    results = await repo.search(source_id=source_a)

    assert len(results) == 1
    assert results[0].title == "From A"


async def test_news_article_list_since_filters_by_published_at(sqlite_session):
    repo = SqlAlchemyNewsArticleRepository(session=sqlite_session)
    await repo.upsert(
        NewsArticle(
            id=NewsArticleId(uuid4()), source_id=NewsSourceId(uuid4()), title="Old", url="https://x.example.com/old",
            content_hash=str(uuid4()), raw_text="body", published_at=T0 - timedelta(days=10), fetched_at=T0,
        )
    )
    await repo.upsert(
        NewsArticle(
            id=NewsArticleId(uuid4()), source_id=NewsSourceId(uuid4()), title="New", url="https://x.example.com/new",
            content_hash=str(uuid4()), raw_text="body", published_at=T0, fetched_at=T0,
        )
    )
    await sqlite_session.commit()

    results = await repo.list_since(T0 - timedelta(days=1))

    assert len(results) == 1
    assert results[0].title == "New"


async def test_news_event_get_by_id(sqlite_session):
    repo = SqlAlchemyNewsEventRepository(session=sqlite_session)
    event = NewsEvent(
        id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary="x", confidence=0.5,
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0, detected_at=T0,
    )
    await repo.record(event)
    await sqlite_session.commit()

    found = await repo.get(event.id)
    missing = await repo.get(NewsEventId(uuid4()))

    assert found is not None
    assert missing is None


async def test_news_event_list_timeline_filters_by_since_and_until(sqlite_session):
    repo = SqlAlchemyNewsEventRepository(session=sqlite_session)
    for label, occurred_at in (("early", T0 - timedelta(days=5)), ("mid", T0), ("late", T0 + timedelta(days=5))):
        await repo.record(
            NewsEvent(
                id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary=label, confidence=0.5,
                source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=occurred_at,
                detected_at=occurred_at,
            )
        )
    await sqlite_session.commit()

    since_only = await repo.list_timeline(since=T0 - timedelta(days=1))
    until_only = await repo.list_timeline(until=T0 + timedelta(days=1))
    bounded = await repo.list_timeline(since=T0 - timedelta(days=1), until=T0 + timedelta(days=1))

    assert {e.summary for e in since_only} == {"mid", "late"}
    assert {e.summary for e in until_only} == {"early", "mid"}
    assert {e.summary for e in bounded} == {"mid"}


async def test_impact_score_get_by_id(sqlite_session):
    repo = SqlAlchemyImpactScoreRepository(session=sqlite_session)
    score = ImpactScore(id=ImpactScoreId(uuid4()), news_event_id=NewsEventId(uuid4()), impact_score=0.5, confidence=0.5)
    await repo.record(score)
    await sqlite_session.commit()

    found = await repo.get(score.id)
    missing = await repo.get(ImpactScoreId(uuid4()))

    assert found is not None
    assert missing is None


async def test_impact_score_get_for_event(sqlite_session):
    repo = SqlAlchemyImpactScoreRepository(session=sqlite_session)
    event_id = NewsEventId(uuid4())
    await repo.record(ImpactScore(id=ImpactScoreId(uuid4()), news_event_id=event_id, impact_score=0.5, confidence=0.5))
    await sqlite_session.commit()

    found = await repo.get_for_event(event_id)
    missing = await repo.get_for_event(NewsEventId(uuid4()))

    assert found is not None
    assert missing is None


async def test_summary_get_by_id(sqlite_session):
    repo = SqlAlchemySummaryRepository(session=sqlite_session)
    summary = Summary(
        id=SummaryId(uuid4()), summary_type=SummaryType.SHORT, subject_ref="s1", text="t", generated_at=T0
    )
    await repo.record(summary)
    await sqlite_session.commit()

    found = await repo.get(summary.id)
    missing = await repo.get(SummaryId(uuid4()))

    assert found is not None
    assert missing is None


async def test_community_post_list_recent_filters_by_platform(sqlite_session):
    repo = SqlAlchemyCommunityPostRepository(session=sqlite_session)
    await repo.upsert(
        CommunityPost(
            id=CommunityPostId(uuid4()), platform=CommunityPlatform.REDDIT, external_id="p1", author_ref="a",
            text="hello reddit", posted_at=T0, fetched_at=T0,
        )
    )
    await repo.upsert(
        CommunityPost(
            id=CommunityPostId(uuid4()), platform=CommunityPlatform.TWITTER, external_id="p2", author_ref="a",
            text="hello twitter", posted_at=T0, fetched_at=T0,
        )
    )
    await sqlite_session.commit()

    reddit_only = await repo.list_recent(platform=CommunityPlatform.REDDIT)

    assert len(reddit_only) == 1
    assert reddit_only[0].platform == CommunityPlatform.REDDIT


async def test_community_topic_get_and_get_by_label(sqlite_session):
    repo = SqlAlchemyCommunityTopicRepository(session=sqlite_session)
    topic = CommunityTopic(id=CommunityTopicId(uuid4()), platform=CommunityPlatform.REDDIT, topic_label="transfers")
    await repo.upsert(topic)
    await sqlite_session.commit()

    by_id = await repo.get(topic.id)
    by_label = await repo.get_by_label(CommunityPlatform.REDDIT, "transfers")
    missing = await repo.get_by_label(CommunityPlatform.REDDIT, "nonexistent")

    assert by_id is not None
    assert by_label is not None and by_label.id == topic.id
    assert missing is None


async def test_community_topic_list_all_filters_by_platform(sqlite_session):
    repo = SqlAlchemyCommunityTopicRepository(session=sqlite_session)
    await repo.upsert(CommunityTopic(id=CommunityTopicId(uuid4()), platform=CommunityPlatform.REDDIT, topic_label="a"))
    await repo.upsert(CommunityTopic(id=CommunityTopicId(uuid4()), platform=CommunityPlatform.TWITTER, topic_label="b"))
    await sqlite_session.commit()

    reddit_only = await repo.list_all(platform=CommunityPlatform.REDDIT)

    assert len(reddit_only) == 1
    assert reddit_only[0].topic_label == "a"


async def test_intelligence_sync_run_get_and_list_recent_filters_by_channel_type(sqlite_session):
    repo = SqlAlchemyIntelligenceSyncRunRepository(session=sqlite_session)
    news_run = await repo.record(
        IntelligenceSyncRun(
            id=IntelligenceSyncRunId(uuid4()), channel_type=IntelligenceChannelType.NEWS, channel_key="s1",
            trigger=SyncTrigger.SCHEDULED, status=SyncStatus.SUCCEEDED, started_at=T0,
        )
    )
    await repo.record(
        IntelligenceSyncRun(
            id=IntelligenceSyncRunId(uuid4()), channel_type=IntelligenceChannelType.COMMUNITY, channel_key="c1",
            trigger=SyncTrigger.SCHEDULED, status=SyncStatus.SUCCEEDED, started_at=T0,
        )
    )
    await sqlite_session.commit()

    found = await repo.get(news_run.id)
    news_only = await repo.list_recent(channel_type=IntelligenceChannelType.NEWS)

    assert found is not None
    assert len(news_only) == 1
    assert news_only[0].channel_type == IntelligenceChannelType.NEWS
