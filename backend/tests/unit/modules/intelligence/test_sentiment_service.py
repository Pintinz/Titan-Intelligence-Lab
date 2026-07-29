from __future__ import annotations

from datetime import datetime, timedelta, timezone

from modules.intelligence.application.sentiment_service import SentimentService
from modules.intelligence.domain.value_objects import SentimentLabel
from modules.intelligence.infrastructure.mock_gemini_adapter import MockGeminiAdapter
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemySentimentResultRepository

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _service(sqlite_session, adapter=None):
    return SentimentService(
        text_intelligence=adapter or MockGeminiAdapter(),
        results=SqlAlchemySentimentResultRepository(session=sqlite_session),
    )


async def test_analyze_classifies_positive_text(sqlite_session):
    service = _service(sqlite_session)

    result = await service.analyze(
        "Great win, the team looked strong and confident!", target_entity_ref="team-1",
        target_entity_type="team", source_ref="article-1", now=T0,
    )
    await sqlite_session.commit()

    assert result.label == SentimentLabel.POSITIVE
    assert result.confidence == 1.0


async def test_analyze_classifies_negative_text(sqlite_session):
    service = _service(sqlite_session)

    result = await service.analyze(
        "Terrible loss, major injury doubt looms.", target_entity_ref="team-1",
        target_entity_type="team", source_ref="article-1", now=T0,
    )
    await sqlite_session.commit()

    assert result.label == SentimentLabel.NEGATIVE


async def test_analyze_detects_mixed_sentiment_across_sentences(sqlite_session):
    service = _service(sqlite_session)
    text = "Great win, the team looked strong and confident! Terrible loss, major injury doubt looms."

    result = await service.analyze(
        text, target_entity_ref="team-1", target_entity_type="team", source_ref="article-1", now=T0
    )
    await sqlite_session.commit()

    assert result.label == SentimentLabel.MIXED
    assert result.confidence == 1.0  # both sentences polarized, none neutral


async def test_analyze_momentum_is_zero_with_no_prior_reading(sqlite_session):
    service = _service(sqlite_session)

    result = await service.analyze(
        "Great win, the team looked strong and confident!", target_entity_ref="team-1",
        target_entity_type="team", source_ref="article-1", now=T0,
    )
    await sqlite_session.commit()

    assert result.momentum == 1.0  # positive (1.0) minus baseline (0.0)


async def test_analyze_momentum_reflects_change_from_prior_reading(sqlite_session):
    service = _service(sqlite_session)
    await service.analyze(
        "Great win, the team looked strong and confident!", target_entity_ref="team-1",
        target_entity_type="team", source_ref="article-1", now=T0,
    )
    await sqlite_session.commit()

    second = await service.analyze(
        "Terrible loss, major injury doubt looms.", target_entity_ref="team-1",
        target_entity_type="team", source_ref="article-2", now=T0 + timedelta(days=1),
    )
    await sqlite_session.commit()

    assert second.momentum == -2.0  # negative (-1.0) minus previous positive (1.0)


async def test_analyze_uses_neutral_for_unrecognized_label(sqlite_session):
    class _WeirdAdapter(MockGeminiAdapter):
        async def interpret_sentiment(self, text):
            return "ecstatic"  # not a recognized SentimentLabel value

    service = _service(sqlite_session, _WeirdAdapter())

    result = await service.analyze(
        "Some text.", target_entity_ref="team-1", target_entity_type="team", source_ref="article-1", now=T0
    )
    await sqlite_session.commit()

    assert result.label == SentimentLabel.NEUTRAL


async def test_analyze_target_entity_is_recorded(sqlite_session):
    service = _service(sqlite_session)

    result = await service.analyze(
        "The match is scheduled for Sunday.", target_entity_ref="player-42",
        target_entity_type="player", source_ref="article-1", now=T0,
    )
    await sqlite_session.commit()

    assert result.target_entity_ref == "player-42"
    assert result.target_entity_type == "player"
