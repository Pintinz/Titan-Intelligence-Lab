"""News Intelligence & Community Intelligence API — Milestone 8
(docs/api_specification.md `/api/v1/intelligence`). Exposes the nine categories the
constitution names: News Search, News Timeline, Entity News, Community Topics, Sentiment,
Impact Scores, Summaries, Source Reliability, News Analytics.

Read-only by design — every route here queries data written by the News Ingestion, Community
Intelligence, Entity/Event Extraction, Source Reliability, Sentiment, and News Impact services;
nothing in this router mutates it. Gated at ``get_current_user`` (any authenticated user), the
same broad-read posture as `graph_router.py` (Milestone 7) — this data is not per-organization/
per-user sensitive.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import (
    build_event_extraction_service,
    build_intelligence_monitoring_service,
    build_news_impact_engine,
    build_news_ingestion_service,
    build_sentiment_service,
    build_source_reliability_service,
    build_summarization_service,
    get_session,
)
from modules.identity.domain.entities import User
from modules.intelligence.domain.entities import (
    CommunityTopic,
    ImpactScore,
    NewsArticle,
    NewsEvent,
    SentimentResult,
    SourceReliabilityScore,
    Summary,
)
from modules.intelligence.domain.value_objects import (
    CommunityPlatform,
    NewsArticleId,
    NewsEventId,
    NewsSourceId,
    SummaryType,
)
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemyCommunityTopicRepository

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_source_id(value: str) -> NewsSourceId:
    try:
        return NewsSourceId(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid source id: {value}") from None


def _parse_platform(value: str | None) -> CommunityPlatform | None:
    if value is None:
        return None
    try:
        return CommunityPlatform(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized platform '{value}'") from None


def _parse_summary_type(value: str) -> SummaryType:
    try:
        return SummaryType(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized summary_type '{value}'") from None


def _serialize_article(article: NewsArticle) -> dict:
    return {
        "id": str(article.id),
        "source_id": str(article.source_id),
        "title": article.title,
        "url": article.url,
        "published_at": article.published_at.isoformat(),
        "language": article.language,
        "version": article.version,
        "status": article.status.value,
    }


def _serialize_event(event: NewsEvent) -> dict:
    return {
        "id": str(event.id),
        "event_type": event.event_type.value,
        "summary": event.summary,
        "confidence": event.confidence,
        "source_id": str(event.source_id),
        "article_id": str(event.article_id),
        "occurred_at": event.occurred_at.isoformat(),
        "detected_at": event.detected_at.isoformat(),
        "affected_entity_refs": list(event.affected_entity_refs),
    }


def _serialize_topic(topic: CommunityTopic) -> dict:
    return {
        "id": str(topic.id),
        "platform": topic.platform.value,
        "topic_label": topic.topic_label,
        "related_entity_refs": list(topic.related_entity_refs),
        "post_count": topic.post_count,
        "momentum": topic.momentum,
    }


def _serialize_sentiment(result: SentimentResult) -> dict:
    return {
        "id": str(result.id),
        "target_entity_ref": result.target_entity_ref,
        "target_entity_type": result.target_entity_type,
        "label": result.label.value,
        "momentum": result.momentum,
        "confidence": result.confidence,
        "source_ref": result.source_ref,
        "computed_at": result.computed_at.isoformat(),
    }


def _serialize_impact(score: ImpactScore) -> dict:
    return {
        "id": str(score.id),
        "news_event_id": str(score.news_event_id),
        "impact_score": score.impact_score,
        "confidence": score.confidence,
        "factors": score.factors,
        "affected_teams": list(score.affected_teams),
        "affected_players": list(score.affected_players),
        "affected_competitions": list(score.affected_competitions),
    }


def _serialize_summary(summary: Summary) -> dict:
    return {
        "id": str(summary.id),
        "summary_type": summary.summary_type.value,
        "subject_ref": summary.subject_ref,
        "text": summary.text,
        "generated_at": summary.generated_at.isoformat(),
        "source_article_ids": list(summary.source_article_ids),
    }


def _serialize_reliability(score: SourceReliabilityScore) -> dict:
    return {
        "source_id": str(score.source_id),
        "reliability_score": score.reliability_score,
        "historical_accuracy": score.historical_accuracy,
        "bias_rating": score.bias_rating,
        "verification_status": score.verification_status.value,
        "trust_level": score.trust_level.value,
        "updated_at": score.updated_at.isoformat(),
    }


# -- News Search ------------------------------------------------------------------------------------


@router.get("/news/search")
async def search_news(
    query: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    articles = build_news_ingestion_service(session).articles
    results = await articles.search(
        query=query, source_id=_parse_source_id(source_id) if source_id else None, limit=limit
    )
    return envelope([_serialize_article(a) for a in results])


@router.get("/news/articles/{article_id}")
async def get_article(
    article_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    """Single-article lookup — added alongside News Center (Milestone 10) since `/news/search`
    only ever returned lists; a detail page needs a stable, shareable per-article URL. Uses the
    existing `NewsArticleRepositoryPort.get`, no new repository capability required."""
    try:
        aid = NewsArticleId(uuid.UUID(article_id))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid article id: {article_id}") from None
    article = await build_news_ingestion_service(session).articles.get(aid)
    if article is None:
        raise HTTPException(status_code=404, detail="article not found")
    return envelope(_serialize_article(article))


# -- News Timeline -----------------------------------------------------------------------------------


@router.get("/news/timeline")
async def news_timeline(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    events = build_event_extraction_service(session).events
    results = await events.list_timeline(since=since, until=until, limit=limit)
    return envelope([_serialize_event(e) for e in results])


# -- Entity News --------------------------------------------------------------------------------------


@router.get("/news/entity/{entity_ref}")
async def entity_news(
    entity_ref: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    events = build_event_extraction_service(session).events
    results = await events.list_for_entity(entity_ref, limit=limit)
    return envelope([_serialize_event(e) for e in results])


# -- Community Topics ----------------------------------------------------------------------------------


@router.get("/community/topics")
async def community_topics(
    platform: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    topics_repo = SqlAlchemyCommunityTopicRepository(session=session)
    results = await topics_repo.list_all(platform=_parse_platform(platform))
    return envelope([_serialize_topic(t) for t in results])


# -- Sentiment -----------------------------------------------------------------------------------------


@router.get("/sentiment/{entity_ref}")
async def sentiment_for_entity(
    entity_ref: str,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    results = await build_sentiment_service(session).results.list_for_entity(entity_ref, limit=limit)
    return envelope([_serialize_sentiment(r) for r in results])


# -- Impact Scores -------------------------------------------------------------------------------------


@router.get("/impact")
async def recent_impact_scores(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    results = await build_news_impact_engine(session).impact_scores.list_recent(limit=limit)
    return envelope([_serialize_impact(s) for s in results])


@router.get("/impact/event/{news_event_id}")
async def impact_score_for_event(
    news_event_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    try:
        event_id = NewsEventId(uuid.UUID(news_event_id))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid news_event_id: {news_event_id}") from None

    score = await build_news_impact_engine(session).impact_scores.get_for_event(event_id)
    if score is None:
        raise HTTPException(status_code=404, detail="impact score not found")
    return envelope(_serialize_impact(score))


# -- Summaries -----------------------------------------------------------------------------------------


@router.get("/summaries/{subject_ref}/{summary_type}")
async def latest_summary(
    subject_ref: str,
    summary_type: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    summary = await build_summarization_service(session).summaries.get_latest(
        subject_ref, _parse_summary_type(summary_type)
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="summary not found")
    return envelope(_serialize_summary(summary))


# -- Source Reliability --------------------------------------------------------------------------------


@router.get("/sources/{source_id}/reliability")
async def source_reliability(
    source_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    score = await build_source_reliability_service(session).reliability.get_for_source(_parse_source_id(source_id))
    if score is None:
        raise HTTPException(status_code=404, detail="no reliability score for this source")
    return envelope(_serialize_reliability(score))


# -- News Analytics ------------------------------------------------------------------------------------


@router.get("/analytics")
async def news_analytics(session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)):
    monitoring = build_intelligence_monitoring_service(session)
    snapshot = await monitoring.snapshot(_now())
    return envelope(
        {
            "article_count": snapshot.article_count,
            "news_ingestion_runs_recent": snapshot.news_ingestion_runs_recent,
            "news_duplicate_rate": snapshot.news_duplicate_rate,
            "avg_processing_seconds": snapshot.avg_processing_seconds,
            "gemini_call_count": snapshot.gemini_call_count,
            "extraction_accuracy": snapshot.extraction_accuracy,
            "average_source_reliability": snapshot.average_source_reliability,
            "community_post_count": snapshot.community_post_count,
            "provider_health": snapshot.provider_health,
        }
    )
