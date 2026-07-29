# TitanIQ — Community Intelligence Platform (Milestone 8)

Status: **Operational.** Ingests community discussion (Reddit, X/Twitter, YouTube metadata,
official fan communities) as a supporting confidence signal. Community Intelligence **never**
overrides verified facts, never becomes a direct prediction output, and shares the Sentiment
Engine and Knowledge Graph/Feature Store enrichment services with
[news_intelligence.md](news_intelligence.md) rather than duplicating them.

## 1. Scope

`CommunityIngestionService` (`backend/modules/intelligence/application/community_ingestion_service.py`)
covers every platform the constitution names (`CommunityPlatform`: Reddit, Twitter, YouTube,
Official Fan Community) through one provider-abstracted pipeline, structurally mirroring
`NewsIngestionService` (same `IntelligenceSyncRun`/`IntelligenceSyncCheckpoint` shape) but with
its own filtering pipeline, since community content has a different noise/abuse profile than
published news.

## 2. Provider Abstraction

`CommunityProviderPort.fetch_posts(topic, since, cursor)`. `MockCommunityProvider` (one class,
parameterized by `platform`, since the mock's job is fixed test data rather than platform-
specific behavior) ships this milestone; a real per-platform adapter (each with its own auth/
rate-limit shape) is future work once live credentials exist ([ADR-008](decisions.md)).

## 3. Filtering Pipeline

Every fetched post passes through, in order, before being persisted as a `CommunityPost`:

1. **Noise reduction** (`is_noise`) — rejects posts under 5 characters or containing no
   alphanumeric content at all (pure punctuation/emoji).
2. **Spam filtering** (`is_spam`) — rejects posts containing known spam markers ("click here",
   "buy now", "free followers", "bit.ly", ...), excessive all-caps shouting (>80% of letters
   uppercase in a post of 12+ letters), or excessive exclamation punctuation (4+ `!`).
3. **Bot detection** (`is_bot_author`) — rejects posts from an author handle matching the common
   auto-generated pattern (5+ trailing digits, e.g. `footballfan1234567`). A heuristic, not a
   trained model — catches the common pattern, not sophisticated evasion.
4. **Duplicate filtering** (`post_content_hash`) — within one sync batch, identical-text posts
   (copy-paste spam reposted under different accounts) are deduped via an in-memory hash set;
   across batches, the platform's own external id is checked against persisted history.
   Deliberately *not* a permanent cross-time content-hash index — a tweet saying "yes!!" many
   times across a season is not a meaningful duplicate the way a republished news article is,
   and persisting that index for every short community post would be disproportionate to the
   actual problem this milestone needs solved.

A post that survives all four checks is persisted with a **Source Credibility** score
(`credibility_score`, bounded to [0.3, 1.0] from the provider's own engagement signal) — this
reflects the *author's* standing, not a verdict on the post's factual content.

## 4. Community Topics

`CommunityTopic` is the aggregate unit the "Community Topics" API returns — a clustered
discussion topic (platform + label) with a related-entity-refs list, post count, and momentum,
distinct from individual posts.

## 5. Sentiment (shared with News Intelligence)

See [news_intelligence.md](news_intelligence.md) §6 — `SentimentService` is called identically
for a community post's text as for a news article's, tagging the `SentimentResult.source_ref`
with the post id instead of an article id. Sentiment from community content is exactly as
auxiliary as sentiment from news — never authoritative, never overriding a verified fact.

## 6. Knowledge Graph / Feature Store Enrichment (shared with News Intelligence)

Community-derived signals (Community Momentum) feed the same `FeatureStoreEnrichmentService`
publishers News Intelligence uses (see [news_intelligence.md](news_intelligence.md) §10) — no
separate community-specific enrichment mechanism exists, since the destination (a Feature Store
value keyed by entity) doesn't care which pipeline produced the number. Community content does
not, on its own, create Knowledge Graph nodes or edges — `CommunityPost`/`CommunityTopic` don't
carry the same structured entity/event extraction News Intelligence's `EntityExtractionService`/
`EventExtractionService` perform; enrichment from community text remains future scope should
that need arise.

## 7. Monitoring

Community Activity (recent post count) is one of `IntelligenceMonitoringService`'s nine metrics
— see [news_intelligence.md](news_intelligence.md) §12 for the full list, all shared across both
pipelines through one `IntelligenceMonitoringService`/`IntelligenceMetricsRecorder`.

## 8. API

`GET /api/v1/intelligence/community/topics` (optionally filtered by `platform`) — see
[api_specification.md](api_specification.md) §2c. Sentiment/Impact/Analytics endpoints are
shared with News Intelligence and documented there.
