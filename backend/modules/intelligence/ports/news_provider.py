"""News provider gateway port (Milestone 8, mirrors docs/architecture.md §5's Provider Adapter
Pattern already used for sports data — docs/decisions.md ADR-008 mock-first, real+mock adapter
per port). Adapters return normalized ``RawArticleRecord``s, never a provider's raw payload
shape; resolving one into a persisted `NewsArticle` (dedup by content hash, versioning) is
`NewsIngestionService`'s job, not the provider's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RawArticleRecord:
    external_ref: str
    title: str
    url: str
    body: str
    published_at: datetime
    author: str | None = None


class NewsProviderPort(Protocol):
    provider_key: str

    async def fetch_articles(
        self, source_url: str, since: datetime | None = None, cursor: str | None = None
    ) -> list[RawArticleRecord]:
        """Every record published at ``source_url`` since ``since`` (incremental sync);
        ``cursor`` is an opaque provider-specific pagination token, passed through unexamined."""
        ...
