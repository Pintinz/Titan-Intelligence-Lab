"""Summarization (Milestone 8 "SUMMARIZATION": "Generate: Short Summary, Executive Summary, AI
Match Briefing, Timeline Summary, Player Summary, Team Summary, Competition Summary.").

Six of the seven named kinds are the same generic operation at a different word budget —
concatenate the relevant articles' text and call `TextIntelligenceProviderPort.summarize` —
mirroring `ContextEngine`'s "one generic builder, many named wrappers" shape (Milestone 7).
Timeline Summary is the exception: a chronological list of already-extracted event summaries is
factual record, not prose to compress, so it's assembled deterministically rather than passed
through the LLM — paraphrasing away exact timestamps/order would defeat the point of a timeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.intelligence.domain.entities import NewsArticle, NewsEvent, Summary
from modules.intelligence.domain.value_objects import SummaryId, SummaryType
from modules.intelligence.ports.repositories import SummaryRepositoryPort
from modules.intelligence.ports.text_intelligence_provider import TextIntelligenceProviderPort

_MAX_WORDS_BY_TYPE = {
    SummaryType.SHORT: 40,
    SummaryType.EXECUTIVE: 150,
    SummaryType.AI_MATCH_BRIEFING: 200,
    SummaryType.PLAYER: 100,
    SummaryType.TEAM: 100,
    SummaryType.COMPETITION: 100,
}


@dataclass
class SummarizationService:
    text_intelligence: TextIntelligenceProviderPort
    summaries: SummaryRepositoryPort

    async def summarize_short(self, subject_ref: str, articles: list[NewsArticle], now: datetime) -> Summary:
        return await self._summarize(subject_ref, SummaryType.SHORT, articles, now)

    async def summarize_executive(self, subject_ref: str, articles: list[NewsArticle], now: datetime) -> Summary:
        return await self._summarize(subject_ref, SummaryType.EXECUTIVE, articles, now)

    async def summarize_match_briefing(self, subject_ref: str, articles: list[NewsArticle], now: datetime) -> Summary:
        return await self._summarize(subject_ref, SummaryType.AI_MATCH_BRIEFING, articles, now)

    async def summarize_player(self, subject_ref: str, articles: list[NewsArticle], now: datetime) -> Summary:
        return await self._summarize(subject_ref, SummaryType.PLAYER, articles, now)

    async def summarize_team(self, subject_ref: str, articles: list[NewsArticle], now: datetime) -> Summary:
        return await self._summarize(subject_ref, SummaryType.TEAM, articles, now)

    async def summarize_competition(self, subject_ref: str, articles: list[NewsArticle], now: datetime) -> Summary:
        return await self._summarize(subject_ref, SummaryType.COMPETITION, articles, now)

    async def summarize_timeline(self, subject_ref: str, events: list[NewsEvent], now: datetime) -> Summary:
        ordered = sorted(events, key=lambda e: e.occurred_at)
        lines = [f"{e.occurred_at.date().isoformat()}: {e.summary}" for e in ordered]
        text = "\n".join(lines) if lines else "No events recorded."
        summary = Summary(
            id=SummaryId(uuid4()),
            summary_type=SummaryType.TIMELINE,
            subject_ref=subject_ref,
            text=text,
            generated_at=now,
            source_article_ids=(),
        )
        return await self.summaries.record(summary)

    async def _summarize(
        self, subject_ref: str, summary_type: SummaryType, articles: list[NewsArticle], now: datetime
    ) -> Summary:
        combined_text = "\n\n".join(a.raw_text for a in articles)
        if not combined_text.strip():
            text = "No source material available."
        else:
            text = await self.text_intelligence.summarize(combined_text, max_words=_MAX_WORDS_BY_TYPE[summary_type])
        summary = Summary(
            id=SummaryId(uuid4()),
            summary_type=summary_type,
            subject_ref=subject_ref,
            text=text,
            generated_at=now,
            source_article_ids=tuple(str(a.id) for a in articles),
        )
        return await self.summaries.record(summary)
