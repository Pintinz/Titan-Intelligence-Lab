"""POST-M24 Phase 3 Step 9: news capability taxonomy — kept separate from the sports-provider
capability model, matching the existing separation between `NewsProviderPort` and
`TextIntelligenceProviderPort`."""

from __future__ import annotations

from modules.intelligence.domain.news_capabilities import NEWS_SOURCE_CAPABILITIES, NewsCapabilityDomain, supports


def test_rss_feed_supports_ingestion_and_retrieval_only():
    assert supports("rss_feed", NewsCapabilityDomain.RSS_INGESTION)
    assert supports("rss_feed", NewsCapabilityDomain.ARTICLE_RETRIEVAL)
    assert not supports("rss_feed", NewsCapabilityDomain.GEMINI_ENRICHMENT)


def test_gemini_supports_enrichment_only():
    assert supports("gemini", NewsCapabilityDomain.GEMINI_ENRICHMENT)
    assert not supports("gemini", NewsCapabilityDomain.RSS_INGESTION)


def test_unknown_source_key_returns_false_not_an_error():
    assert supports("nonexistent_source", NewsCapabilityDomain.RSS_INGESTION) is False


def test_registry_has_exactly_the_two_real_sources():
    assert set(NEWS_SOURCE_CAPABILITIES.keys()) == {"rss_feed", "gemini"}
