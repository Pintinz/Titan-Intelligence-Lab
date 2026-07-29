from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.intelligence.application.summarization_service import SummarizationService
from modules.intelligence.domain.entities import NewsArticle, NewsEvent
from modules.intelligence.domain.value_objects import (
    ArticleStatus,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
    SummaryType,
)
from modules.intelligence.infrastructure.mock_gemini_adapter import MockGeminiAdapter
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemySummaryRepository

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _article(text: str, **overrides) -> NewsArticle:
    defaults = dict(
        id=NewsArticleId(uuid4()), source_id=NewsSourceId(uuid4()), title="Headline", url=f"https://example.com/{uuid4()}",
        content_hash=str(uuid4()), raw_text=text, published_at=T0, fetched_at=T0, status=ArticleStatus.ACTIVE,
    )
    defaults.update(overrides)
    return NewsArticle(**defaults)


def _event(summary: str, occurred_at: datetime) -> NewsEvent:
    return NewsEvent(
        id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary=summary, confidence=0.7,
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=occurred_at,
        detected_at=occurred_at,
    )


def _service(sqlite_session) -> SummarizationService:
    return SummarizationService(text_intelligence=MockGeminiAdapter(), summaries=SqlAlchemySummaryRepository(session=sqlite_session))


async def test_summarize_short_uses_low_word_budget(sqlite_session):
    service = _service(sqlite_session)
    article = _article(" ".join(f"word{i}" for i in range(200)))

    summary = await service.summarize_short("team-1", [article], T0)
    await sqlite_session.commit()

    assert summary.summary_type == SummaryType.SHORT
    assert len(summary.text.split()) <= 41  # 40 words + trailing "..."


async def test_summarize_executive_uses_higher_word_budget(sqlite_session):
    service = _service(sqlite_session)
    article = _article(" ".join(f"word{i}" for i in range(200)))

    summary = await service.summarize_executive("team-1", [article], T0)
    await sqlite_session.commit()

    assert summary.summary_type == SummaryType.EXECUTIVE
    assert len(summary.text.split()) <= 151


async def test_summarize_records_source_article_ids(sqlite_session):
    service = _service(sqlite_session)
    article = _article("Some real match reporting content here.")

    summary = await service.summarize_team("team-1", [article], T0)
    await sqlite_session.commit()

    assert summary.source_article_ids == (str(article.id),)


async def test_summarize_handles_no_articles_gracefully(sqlite_session):
    service = _service(sqlite_session)

    summary = await service.summarize_player("player-1", [], T0)
    await sqlite_session.commit()

    assert summary.text == "No source material available."
    assert summary.source_article_ids == ()


async def test_summarize_competition_tags_correct_type(sqlite_session):
    service = _service(sqlite_session)
    article = _article("The competition standings shifted after a big result.")

    summary = await service.summarize_competition("comp-1", [article], T0)
    await sqlite_session.commit()

    assert summary.summary_type == SummaryType.COMPETITION
    assert summary.subject_ref == "comp-1"


async def test_summarize_match_briefing_tags_correct_type(sqlite_session):
    service = _service(sqlite_session)
    article = _article("Match preview content ahead of kickoff.")

    summary = await service.summarize_match_briefing("fixture-1", [article], T0)
    await sqlite_session.commit()

    assert summary.summary_type == SummaryType.AI_MATCH_BRIEFING


async def test_summarize_timeline_orders_events_chronologically(sqlite_session):
    service = _service(sqlite_session)
    later_event = _event("Second event happened.", T0 + timedelta(days=1))
    earlier_event = _event("First event happened.", T0)

    summary = await service.summarize_timeline("player-1", [later_event, earlier_event], T0 + timedelta(days=2))
    await sqlite_session.commit()

    assert summary.summary_type == SummaryType.TIMELINE
    first_line_index = summary.text.index("First event happened.")
    second_line_index = summary.text.index("Second event happened.")
    assert first_line_index < second_line_index


async def test_summarize_timeline_handles_no_events(sqlite_session):
    service = _service(sqlite_session)

    summary = await service.summarize_timeline("player-1", [], T0)
    await sqlite_session.commit()

    assert summary.text == "No events recorded."
