# TitanIQ — News Intelligence Platform (Milestone 8)

Status: **Operational.** Transforms unstructured news content into structured, Knowledge-Graph-
linked, Feature-Store-consumable intelligence. News and community information are supporting
evidence only — they **never** become direct prediction outputs, and nothing in this pipeline
generates a prediction probability, predicts a match outcome, or recommends a betting decision.

## 1. Scope

News Intelligence covers everything from ingesting a raw article to publishing derived signals
other subsystems consume: multi-source ingestion, entity/event extraction, source reliability
scoring, sentiment analysis, news impact scoring, summarization, Knowledge Graph enrichment,
and Feature Store enrichment. See [community_intelligence.md](community_intelligence.md) for
the parallel Community Intelligence pipeline (shares the Sentiment Engine and the Knowledge
Graph/Feature Store enrichment services, but is ingested and filtered separately).

## 2. News Ingestion

`NewsIngestionService` (`backend/modules/intelligence/application/news_ingestion_service.py`)
supports every source category the constitution names — Official Club Websites, League
Websites, Competition Websites, Sports News APIs, RSS Feeds, Approved Sports Publishers, Press
Releases, Official Federation Announcements (`NewsSourceType`) — through one provider-abstracted
pipeline:

- **Provider abstraction**: `NewsProviderPort.fetch_articles(source_url, since, cursor)`. Two
  adapters ship this milestone: `MockNewsProvider` (deterministic, for tests) and
  `RssNewsProvider` (real — genuine `httpx` GET + `xml.etree.ElementTree` parsing of RSS 2.0 and
  Atom feeds, no paid API key required).
- **Incremental synchronization**: `IntelligenceSyncCheckpoint` tracks `last_synced_at`/`cursor`
  per source; each sync only asks the provider for records since the last successful run.
- **Deduplication**: `content_hash()` — a SHA-256 of the normalized (lowercased, whitespace-
  collapsed) title+body — is a persistent, cross-time dedup key. The same story republished
  verbatim by a different source, or re-fetched on the next sync, resolves to the same hash.
- **Versioning**: re-fetching an already-seen URL with materially different content bumps
  `NewsArticle.version` in place rather than creating a duplicate row.
- **Retry**: a failed sync increments `IntelligenceSyncCheckpoint.consecutive_failures` and
  marks the `IntelligenceSyncRun` `FAILED` rather than looping internally — a Celery task or
  caller re-invokes with `trigger=RETRY`, mirroring `modules.ingestion`'s Milestone 5 pattern.
- **Scheduling**: a `trigger` (`SCHEDULED`/`MANUAL`/`RETRY`) is recorded per run; wiring a Celery
  beat schedule to call `sync_source` periodically reuses Milestone 5's existing Celery app.
- **Caching**: request-level caching would use the same generic `SyncCachePort`/Redis
  integration Milestone 5 built — reused, not reinvented (see §7 below for where this pattern
  is actually exercised, in `CachedKGNodeRepository`'s Knowledge Graph analog).
- **Monitoring**: every sync produces an `IntelligenceSyncRun` (items fetched/created/
  duplicate/rejected) — see §8.

## 3. Entity Extraction

`EntityExtractionService` calls `TextIntelligenceProviderPort.extract_entities` (NER) and
resolves each mention against the Knowledge Graph via `EntityResolutionService.find_by_alias`
(Milestone 7) — reused, not reimplemented. A resolved mention carries a `KGNodeId`; an
unresolved one does not — this service identifies and attempts to resolve, it does not
autonomously create graph nodes for every NER hit (that's Knowledge Graph Enrichment, §6).

## 4. Event Extraction

`EventExtractionService` wraps `TextIntelligenceProviderPort.extract_events` and persists a
`NewsEvent` for every one of the fourteen event categories the constitution names: Transfers,
Injuries, Recoveries, Suspensions, Manager Changes, Formation Changes, Tactical Changes,
Training Updates, Weather Reports, Travel Delays, Stadium Changes, Match Postponements, Player
Availability, Lineup Expectations (`NewsEventType`). Every event carries Confidence, Source,
Timestamp, Affected Entities (the provider's own entity list unioned with `EntityExtractionService`'s
resolved Knowledge Graph refs), and — once `KnowledgeGraphEnrichmentService` has processed it —
Knowledge Graph links.

## 5. Source Reliability Engine

`SourceReliabilityService` gives every `NewsSource` a `SourceReliabilityScore`: Reliability
Score, Historical Accuracy, Bias Rating, Verification Status, Trust Level. Publisher Metadata
and Official/Unofficial classification live on `NewsSource` itself. An official source starts
at `TrustLevel.OFFICIAL` immediately (a structural fact); `record_outcome()` nudges reliability/
accuracy via an exponentially-weighted moving average toward each new observed outcome, and
enough consistently-inaccurate outcomes still demotes even an official source to `UNRELIABLE`.
Consumed as a Feature Store input (§7) — never used to override a verified fact.

## 6. Sentiment Engine

`SentimentService` (shared with Community Intelligence) supports Positive/Negative/Neutral/
Mixed, Momentum, Confidence, Target entity. `TextIntelligenceProviderPort.interpret_sentiment`
returns one label per call with no Mixed option and no confidence figure — this engine derives
both by splitting input into sentences and interpreting each one: disagreement across sentences
(some positive, some negative) is Mixed; confidence is the majority label's agreement ratio.
Momentum is the signed change in a [-1, +1] sentiment score against the target entity's most
recent prior reading. Sentiment remains an auxiliary feature only.

## 7. News Impact Engine

`NewsImpactEngine` evaluates eight named factors — Injury Severity, Transfer Importance, Manager
Influence, Player Importance, Competition Importance, Timing, Historical Impact, Community
Momentum — each a real, deterministic heuristic computed from data this milestone persists (no
ML model): keyword severity scanning for injuries, affected-entity-count scaling for transfers,
a fixed weight table per event type for competition importance, exponential time-decay for
timing, a rolling average of recent `ImpactScore`s for historical impact, and recent
`SentimentResult` momentum magnitude for community momentum. The composite `impact_score` is
their unweighted mean, clamped to [0, 1]; `confidence` inherits the underlying event's own
extraction confidence. Affected Teams/Players/Competitions are populated by looking up any
resolved Knowledge Graph ref among the event's affected entities.

## 8. Summarization

`SummarizationService` generates all seven named kinds: Short Summary, Executive Summary, AI
Match Briefing, Player Summary, Team Summary, Competition Summary (six of these are the same
generic "concatenate source articles, call `TextIntelligenceProviderPort.summarize` at a kind-
specific word budget" operation — mirroring `ContextEngine`'s Milestone 7 "one builder, many
named wrappers" shape) and Timeline Summary (the exception — a chronological list of already-
extracted event summaries, assembled deterministically rather than passed through the LLM, since
paraphrasing away exact timestamps/order would defeat the point of a timeline).

## 9. Knowledge Graph Enrichment

`KnowledgeGraphEnrichmentService` creates Nodes, Edges, Relationships, Temporal Events, and
Aliases using **existing Graph APIs only** (Milestone 5/7's `KnowledgeGraphPopulationService`/
`TemporalGraphService`, composed in — nothing new added to `modules.knowledge_graph` itself):

- **Nodes + Aliases** (`enrich_from_mentions`): a resolved mention contributes its literal text
  as a new alias on the existing node; an unresolved mention with a known ontology type becomes
  a brand-new node, source-tagged `"news_intelligence"`.
- **Edges + Relationships + Temporal Events** (`enrich_from_event`): `TRANSFER` events create/
  supersede a `PLAYS_FOR` edge (closing the player's prior team relationship via
  `TemporalGraphService.supersede_edge` if one exists); `MANAGER_CHANGE` events create a
  `COACHED_BY` edge. Every other event type enriches nodes/aliases only — no edge — since
  guessing an unambiguous relationship for e.g. an `INJURY` event with no linked match/venue
  would be worse than enriching nothing.
- **Historical references**: fall out of the existing machinery for free — any edge this
  service creates is immediately queryable via `GraphQueryService.edge_history`/
  `entity_evolution` (Milestone 7); nothing new was built for this.

## 10. Feature Store Enrichment

`FeatureStoreEnrichmentService` registers and publishes ten generic, cross-sport features
(`sport_code="generic"`, `category=CONTEXTUAL`): Injury Impact, Transfer Stability, Manager
Stability, Community Momentum, News Momentum, Squad Availability, Media Pressure, Travel
Fatigue, Weather Impact, Source Reliability. Registration goes through the real
`FeatureRegistrationService` DRAFT → IN_REVIEW → ACTIVE workflow (Milestone 4) with a "system"
reviewer, then `publish()` writes through the ordinary `FeatureStoreService.write()` path — no
sport-specific engineered features are computed this milestone, per the constitution's explicit
scope line.

## 11. RAG Foundation

See [knowledge_graph.md](knowledge_graph.md) §11 for Milestone 7's Knowledge Graph retrieval;
Milestone 8 adds `NewsRetrieval` and `AIReportRetrieval` (over `Summary` records) implementing
the new modality-general `IntelligenceRetrievalPort`, fanned out by
`IntelligenceRetrievalService.retrieve_all()` alongside a `KnowledgeGraphRetrievalAdapter` that
wraps Milestone 7's `GraphRetrievalPort` unchanged. No vector embeddings, no LLM prompting layer.

## 12. Monitoring

`IntelligenceMonitoringService` reports Ingestion Rate (sync runs/hour in a window), Article
Count (total, via `NewsArticleRepositoryPort.count_all`), Duplicate Rate (duplicates ÷ fetched
across recent runs), Extraction Accuracy (an opt-in-recorded proxy — undefined until a caller
records at least one verified outcome), Processing Time (`IntelligenceMetricsRecorder`'s timing
context manager), Gemini Usage (call counter), Provider Health (per-channel-key recent success
rate and consecutive-failure streak, derived from `IntelligenceSyncRun` history — reusing that
history rather than duplicating `modules.admin`'s `HealthIntelligenceEngine`), Source
Reliability (fleet-wide average), Community Activity (recent post count).

## 13. API

`apps/api/routers/intelligence_router.py`, prefix `/api/v1/intelligence`, all GET/read-only,
gated at `get_current_user`: News Search, News Timeline, Entity News, Community Topics,
Sentiment, Impact Scores, Summaries, Source Reliability, News Analytics. See
[api_specification.md](api_specification.md) §2c.
