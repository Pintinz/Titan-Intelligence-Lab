"""News source capability taxonomy (POST-M24 Phase 3 Step 9). Deliberately separate from
`modules.sports.domain.provider_capabilities` — RSS ingestion and Gemini enrichment are already
two distinct ports in this codebase (`NewsProviderPort` vs `TextIntelligenceProviderPort`), never
merged, and this module preserves that separation rather than forcing news into the sports-
provider vocabulary.

Two real sources exist today: `rss_feed` (backed by `RssNewsProvider`, real HTTP/XML, no paid key)
and `gemini` (backed by `GeminiAdapter`/`MockGeminiAdapter` via `TextIntelligenceRouter`).
Relevance filtering (`NewsRelevanceFilter`) is deliberately not represented as a capability here —
it's a deterministic in-process pipeline stage applied to every article regardless of source, not
a capability any one external provider offers or withholds."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NewsCapabilityDomain(str, Enum):
    RSS_INGESTION = "rss_ingestion"
    ARTICLE_RETRIEVAL = "article_retrieval"
    GEMINI_ENRICHMENT = "gemini_enrichment"


@dataclass(frozen=True)
class NewsSourceCapabilities:
    source_key: str
    domains: frozenset[NewsCapabilityDomain]

    def supports_domain(self, domain: NewsCapabilityDomain) -> bool:
        return domain in self.domains


NEWS_SOURCE_CAPABILITIES: dict[str, NewsSourceCapabilities] = {
    # NewsIngestionService._resolve_provider only ever looks up the "rss_feed" NewsSourceType key
    # (modules/intelligence/application/news_ingestion_service.py) — the real, working adapter.
    "rss_feed": NewsSourceCapabilities(
        source_key="rss_feed",
        domains=frozenset({NewsCapabilityDomain.RSS_INGESTION, NewsCapabilityDomain.ARTICLE_RETRIEVAL}),
    ),
    # GeminiAdapter.provider_key == "gemini" (modules/intelligence/infrastructure/gemini_adapter.py).
    "gemini": NewsSourceCapabilities(
        source_key="gemini", domains=frozenset({NewsCapabilityDomain.GEMINI_ENRICHMENT}),
    ),
}


def supports(source_key: str, domain: NewsCapabilityDomain) -> bool:
    caps = NEWS_SOURCE_CAPABILITIES.get(source_key)
    return caps is not None and caps.supports_domain(domain)
