"""Deterministic mock for `NewsProviderPort` — lets `NewsIngestionService` and every consumer
be built and tested without live credentials for any real news API (docs/decisions.md
ADR-008)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.intelligence.ports.news_provider import RawArticleRecord


@dataclass
class MockNewsProvider:
    provider_key: str = "mock_news"
    fixed_articles: tuple[RawArticleRecord, ...] = field(default_factory=tuple)

    async def fetch_articles(
        self, source_url: str, since: datetime | None = None, cursor: str | None = None
    ) -> list[RawArticleRecord]:
        if not self.fixed_articles:
            return []
        if since is None:
            return list(self.fixed_articles)
        return [a for a in self.fixed_articles if a.published_at > since]
