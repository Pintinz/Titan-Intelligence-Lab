from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.security import MockJWTValidator
from modules.intelligence.domain.entities import (
    CommunityTopic,
    ImpactScore,
    NewsArticle,
    NewsEvent,
    NewsSource,
    SentimentResult,
    SourceReliabilityScore,
    Summary,
)
from modules.intelligence.domain.value_objects import (
    ArticleStatus,
    CommunityPlatform,
    CommunityTopicId,
    ImpactScoreId,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
    NewsSourceType,
    SentimentLabel,
    SentimentResultId,
    SourceReliabilityId,
    SummaryId,
    SummaryType,
    TrustLevel,
    VerificationStatus,
)
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyCommunityTopicRepository,
    SqlAlchemyImpactScoreRepository,
    SqlAlchemyNewsArticleRepository,
    SqlAlchemyNewsEventRepository,
    SqlAlchemyNewsSourceRepository,
    SqlAlchemySentimentResultRepository,
    SqlAlchemySourceReliabilityRepository,
    SqlAlchemySummaryRepository,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"identity": None, "intelligence": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(IntelligenceBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(db_session_factory):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    yield TestClient(app)
    app.dependency_overrides.clear()


def register_and_login(client, email, password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login.json()["data"]["access_token"]


@pytest.fixture
def auth_headers(client):
    token = register_and_login(client, "intel-user@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def seeded(db_session_factory):
    async with db_session_factory() as session:
        sources = SqlAlchemyNewsSourceRepository(session=session)
        source = NewsSource(
            id=NewsSourceId(uuid4()), source_type=NewsSourceType.OFFICIAL_CLUB_WEBSITE, name="Club Site",
            url="https://club.example.com", is_official=True, created_at=T0,
        )
        await sources.upsert(source)

        articles = SqlAlchemyNewsArticleRepository(session=session)
        article = NewsArticle(
            id=NewsArticleId(uuid4()), source_id=source.id, title="Striker Signs New Deal",
            url="https://club.example.com/1", content_hash=str(uuid4()), raw_text="The striker signed a new deal.",
            published_at=T0, fetched_at=T0, status=ArticleStatus.ACTIVE,
        )
        await articles.upsert(article)

        events = SqlAlchemyNewsEventRepository(session=session)
        event = NewsEvent(
            id=NewsEventId(uuid4()), event_type=NewsEventType.TRANSFER, summary="Transfer confirmed.",
            confidence=0.7, source_id=source.id, article_id=article.id, occurred_at=T0, detected_at=T0,
            affected_entity_refs=("player-1", "team-1"),
        )
        await events.record(event)

        topics = SqlAlchemyCommunityTopicRepository(session=session)
        topic = CommunityTopic(
            id=CommunityTopicId(uuid4()), platform=CommunityPlatform.REDDIT, topic_label="transfer-talk",
            related_entity_refs=("team-1",), post_count=5, momentum=0.2, created_at=T0,
        )
        await topics.upsert(topic)

        sentiments = SqlAlchemySentimentResultRepository(session=session)
        sentiment = SentimentResult(
            id=SentimentResultId(uuid4()), target_entity_ref="player-1", target_entity_type="player",
            label=SentimentLabel.POSITIVE, momentum=0.5, confidence=0.8, source_ref=str(article.id), computed_at=T0,
        )
        await sentiments.record(sentiment)

        impacts = SqlAlchemyImpactScoreRepository(session=session)
        impact = ImpactScore(
            id=ImpactScoreId(uuid4()), news_event_id=event.id, impact_score=0.6, confidence=0.7,
            factors={"transfer_importance": 0.6}, affected_teams=("team-1",), computed_at=T0,
        )
        await impacts.record(impact)

        summaries = SqlAlchemySummaryRepository(session=session)
        summary = Summary(
            id=SummaryId(uuid4()), summary_type=SummaryType.TEAM, subject_ref="team-1", text="Team recap.",
            generated_at=T0, source_article_ids=(str(article.id),),
        )
        await summaries.record(summary)

        reliability = SqlAlchemySourceReliabilityRepository(session=session)
        score = SourceReliabilityScore(
            id=SourceReliabilityId(uuid4()), source_id=source.id, reliability_score=0.75, historical_accuracy=0.7,
            bias_rating=0.0, verification_status=VerificationStatus.VERIFIED, trust_level=TrustLevel.OFFICIAL,
            updated_at=T0,
        )
        await reliability.upsert(score)

        await session.commit()
        return {"source": source, "article": article, "event": event}


def test_news_search_returns_articles(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/news/search", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["title"] == "Striker Signs New Deal"


def test_news_search_by_query(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/news/search", params={"query": "Striker"}, headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_news_search_invalid_source_id(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/news/search", params={"source_id": "not-a-uuid"}, headers=auth_headers)

    assert response.status_code == 422


def test_get_article_by_id(client, seeded, auth_headers):
    article_id = str(seeded["article"].id)
    response = client.get(f"/api/v1/intelligence/news/articles/{article_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "Striker Signs New Deal"


def test_get_unknown_article_returns_404(client, seeded, auth_headers):
    response = client.get(f"/api/v1/intelligence/news/articles/{uuid4()}", headers=auth_headers)

    assert response.status_code == 404


def test_get_article_invalid_id_returns_422(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/news/articles/not-a-uuid", headers=auth_headers)

    assert response.status_code == 422


def test_news_timeline_returns_events(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/news/timeline", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["event_type"] == "transfer"


def test_entity_news_returns_matching_events(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/news/entity/player-1", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_entity_news_empty_for_unrelated_entity(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/news/entity/unrelated-entity", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_community_topics_returns_seeded_topic(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/community/topics", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"][0]["topic_label"] == "transfer-talk"


def test_community_topics_filters_by_platform(client, seeded, auth_headers):
    response = client.get(
        "/api/v1/intelligence/community/topics", params={"platform": "youtube"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_community_topics_invalid_platform(client, seeded, auth_headers):
    response = client.get(
        "/api/v1/intelligence/community/topics", params={"platform": "not-a-platform"}, headers=auth_headers
    )

    assert response.status_code == 422


def test_sentiment_for_entity(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/sentiment/player-1", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"][0]["label"] == "positive"


def test_recent_impact_scores(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/impact", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"][0]["impact_score"] == 0.6


def test_impact_score_for_event(client, seeded, auth_headers):
    event_id = seeded["event"].id

    response = client.get(f"/api/v1/intelligence/impact/event/{event_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["affected_teams"] == ["team-1"]


def test_impact_score_for_event_not_found(client, seeded, auth_headers):
    response = client.get(f"/api/v1/intelligence/impact/event/{uuid4()}", headers=auth_headers)

    assert response.status_code == 404


def test_impact_score_for_event_invalid_id(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/impact/event/not-a-uuid", headers=auth_headers)

    assert response.status_code == 422


def test_latest_summary(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/summaries/team-1/team", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["text"] == "Team recap."


def test_latest_summary_not_found(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/summaries/unknown-subject/team", headers=auth_headers)

    assert response.status_code == 404


def test_latest_summary_invalid_type(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/summaries/team-1/not-a-type", headers=auth_headers)

    assert response.status_code == 422


def test_source_reliability(client, seeded, auth_headers):
    source_id = seeded["source"].id

    response = client.get(f"/api/v1/intelligence/sources/{source_id}/reliability", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["trust_level"] == "official"


def test_source_reliability_not_found(client, seeded, auth_headers):
    response = client.get(f"/api/v1/intelligence/sources/{uuid4()}/reliability", headers=auth_headers)

    assert response.status_code == 404


def test_news_analytics(client, seeded, auth_headers):
    response = client.get("/api/v1/intelligence/analytics", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["article_count"] == 1
    assert data["average_source_reliability"] == 0.75


def test_routes_require_authentication(client, seeded):
    response = client.get("/api/v1/intelligence/analytics")

    assert response.status_code == 401
