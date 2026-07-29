# TitanIQ — Architecture

Status: Milestones 1–9.1 implemented (Sports Domain, Provider Foundation, Feature Intelligence,
Ingestion/Knowledge Graph, Enterprise Identity/Tenancy/Billing, Sports Semantic Intelligence,
News/Community Intelligence, Prediction Intelligence Platform — §5i, Enterprise Machine Learning
Platform — §5j). See [decisions.md](decisions.md) for the ADRs backing the choices below.

## 1. Architectural Style

**Modular Monolith** with strict internal service boundaries, deployed as a small number of
independently scalable processes (API, worker, scheduler), not as one giant undifferentiated
app. Boundaries are drawn so that any module can be extracted into its own service later without
touching its callers — only the adapter that invokes it changes.

Why not microservices on day one (see ADR-002): a funded team building 4 sports × N prediction
markets × N AI subsystems already has enormous *domain* complexity. Adding network-boundary
complexity between modules that are still co-evolving multiplies coordination cost for no
present benefit. Every module below is built as if it *were* a service — own schema namespace,
own repository interface, communicates only through defined ports — so extraction later is a
deployment change, not a rewrite.

## 2. Guiding Principles

- **Clean Architecture / Hexagonal**: dependencies point inward. Domain has zero imports from
  FastAPI, SQLAlchemy, Supabase SDKs, or any provider SDK.
- **Domain-Driven Design**: each bounded context (Sports, Features, Predictions, Knowledge
  Graph, Identity, Billing, Content/News, Community) owns its own models and language.
- **SOLID** at the module level, enforced in code review, not just aspiration.
- **Repository Pattern** for all persistence access — no ORM session leaks into service/domain
  code.
- **Dependency Injection** via FastAPI's `Depends` graph, composed in `app/composition.py` per
  module — no service-locator globals.
- **OpenAPI-first**: Pydantic v2 models define the contract; the OpenAPI schema is generated,
  not hand-written, and is the source of truth for the TypeScript client.
- **Event-driven** for cross-module reactions (e.g., "MatchCompleted" triggers Outcome Learning)
  via an internal event bus (Redis Streams initially — see ADR-004), not direct cross-module
  function calls.
- **CQRS where beneficial**: read-heavy analytics/dashboard queries go through dedicated
  read-models (materialized views / projections), not the same path as write commands.

## 3. Layering

```
apps/
  api/                  FastAPI HTTP entrypoint — routers, request/response schemas, auth deps
  worker/                Celery worker entrypoint — task registration only
  scheduler/              Celery beat / cron entrypoint — schedule definitions only

modules/<bounded-context>/
  domain/                Entities, value objects, domain services, domain events
                          — no framework imports, no I/O
  application/            Use cases / application services — orchestrate domain + ports
                          — depends on domain + port interfaces only
  ports/                  Abstract interfaces the application layer depends on
                          (Repository, Clock, ProviderGateway, EventPublisher, ModelStore...)
  infrastructure/         Concrete adapters implementing ports:
                          - persistence/ (SQLAlchemy repositories, Alembic migrations)
                          - providers/ (API-Football adapter, Gemini adapter, ...)
                          - cache/ (Redis)
                          - messaging/ (event bus publisher/consumer)
  interfaces/              Inbound adapters: FastAPI routers, Celery tasks, CLI commands
                          — translate transport concerns into application-layer calls
```

Bounded contexts under `modules/`: `sports`, `features`, `ingestion` (Milestone 5 —
Sports Data Ingestion Engine, see §5d), `knowledge_graph` (population Milestone 5, full Sports
Semantic Intelligence Platform Milestone 7 — see §5e), `predictions`, `outcome_learning`,
`identity`, `tenancy`, `billing`, `webhooks` (Milestone 6), `content` (news/community),
`personalization`, `analytics`, `admin`, `intelligence` (Gemini text-intelligence port,
Milestone 3; full News Intelligence & Community Intelligence Platform, Milestone 8, §5h).

Dependency rule: `interfaces → application → domain`, `infrastructure → ports (implements)`,
`application → ports (depends on abstraction)`. `domain` depends on nothing in this repo except
another module's `domain` (rare, and only for shared kernel concepts like `SportId`).

## 4. Sport Plugin Boundary

Every sport is a plugin against a fixed set of domain contracts, not a fork of the codebase.

```
modules/sports/domain/contracts/
  competition.py    CompetitionStructure, SeasonLifecycle
  participant.py     Team, Player, CoachingStaff, Official
  fixture.py          Fixture, MatchLifecycle, MatchEvent
  statistics.py        TeamStatistics, PlayerStatistics (sport-specific payload, common envelope)

modules/sports/football/       # implements the contracts above for football
modules/sports/basketball/
modules/sports/baseball/
modules/sports/table_tennis/
```

A new sport is added by implementing the contracts above plus a feature-engineering pipeline
and prediction-market set — it never requires modifying `predictions`, `features`, or
`knowledge_graph` module internals. Those modules consume sports through
`SportPluginRegistry`, resolved at startup.

## 5. Provider Adapter Pattern

No provider-specific field name, payload shape, or SDK type may exist outside
`modules/*/infrastructure/providers/`. Each adapter implements a module-owned port
(e.g., `SportsDataProviderPort`) and returns normalized DTOs — not persisted domain entities
directly, since a freshly fetched record has no database identity yet (`TeamId`, `SeasonId`,
...). Resolving a normalized DTO into a persisted domain entity is the ingestion pipeline's job
(Milestone 5); see [decisions.md](decisions.md) ADR-009 for the reasoning behind this
refinement from the original "adapters return domain entities" phrasing.

```
ports/provider_gateway.py           # Protocol: fetch_teams/fetch_fixtures(...) -> normalized DTOs
infrastructure/providers/
  api_sports_adapter.py             # real httpx adapters: ApiFootballAdapter, ApiBasketballAdapter, ApiBaseballAdapter
  mock_provider.py                  # MockSportsDataProvider — implements the same port, deterministic fake data
  provider_router.py                # SportsProviderRouter — picks mock vs real, applies circuit breaker + quota engine + cache
```

Swapping or adding a provider means adding an adapter class and a registration entry in the
Provider Management System (below) — zero changes to application or domain code. Every port has
both a real adapter and a deterministic mock implementing it, so no milestone blocks on missing
production credentials ([decisions.md](decisions.md) ADR-008). Multiple providers may implement
the same port simultaneously; `SportsProviderRouter` selects/falls back based on credential
availability, circuit state, and quota (see [admin_center.md](admin_center.md) §"API Provider
Center").

**Milestone 5 expansion**: `SportsDataProviderPort` grew from 2 methods (`fetch_teams`,
`fetch_fixtures`) to 7 — `fetch_countries`, `fetch_players`, `fetch_standings`,
`fetch_team_statistics`, `fetch_lineups` were added, each with a matching DTO
(`ProviderCountryRecord`, `ProviderPlayerRecord`, `ProviderStandingRecord`,
`ProviderTeamStatisticsRecord`, `ProviderLineupRecord`), a `MockSportsDataProvider`
implementation, and a real `ApiFootballAdapter`/`ApiBasketballAdapter`/`ApiBaseballAdapter`
implementation. Two of the five new real-adapter methods are honestly weaker than the rest:
`fetch_team_statistics`'s endpoint path for basketball/baseball is a best-effort guess (API-
Football's `/fixtures/statistics` is well-documented; the basketball/baseball equivalent isn't),
and `fetch_lineups` returns an empty list for basketball/baseball rather than guessing at a
nonexistent endpoint — API-Football has a genuine, documented lineups endpoint the other two
sports' APIs don't appear to.

## 5d. Sports Data Ingestion Engine & Knowledge Graph (Milestone 5)

`modules/ingestion/` turns validated provider DTOs into persisted, versioned, KG-populated
domain entities — the pipeline every other subsystem in §5-§5c was built anticipating but that
didn't exist until this milestone:

```
modules/ingestion/
  domain/           SyncRun, SyncCheckpoint, TimelineEvent, DataQualityReport, ProviderRefIndexEntry
  ports/              {SyncRun,SyncCheckpoint,TimelineEvent,DataQualityReport,ProviderRefIndex}RepositoryPort,
                        DistributedLockPort, SyncCachePort, FeatureCalculatorPort
  application/          DataValidationEngine, IngestionQualityEngine, EntityReconciliationService,
                          SyncOrchestrator, FeaturePipeline, MonitoringService
  infrastructure/         persistence/ (Postgres, `ingestion` schema), cache/ (Redis lock + cache),
                          celery/ (celery_app, tasks, dead_letter, beat_schedule)
```

**Reconciliation, not just persistence**: `EntityReconciliationService` resolves "have I seen
this external id before" via `ProviderRefIndexRepositoryPort` — an O(1) lookup table
(`provider_ref_index`) rather than scanning every entity's `provider_ref` JSON column — decides
create-vs-update, bumps `version`, merges `provider_refs`, populates the Knowledge Graph, and
emits a `TimelineEvent`, all as one atomic unit of work per entity. One method per canonical
entity (11 for the Entity Expansion Matrix's "fully wired" set, see
[database_schema.md](database_schema.md) §11) rather than a single generic dispatcher — each
entity's field mapping differs enough that forced genericity would just hide the same
branching behind one signature.

**SyncOrchestrator is the incremental/scheduling layer above reconciliation**: one generic
`_run_sync` handles distributed locking (`DistributedLockPort`, Redis-backed — no two workers
sync the same scope concurrently), incremental skip (a `SyncCheckpoint.last_synced_at` within
the configured interval means nothing to do — "never reload complete datasets
unnecessarily"), `SyncRun` lifecycle (PENDING → RUNNING → SUCCEEDED/PARTIAL/FAILED),
retry/failure bookkeeping (`consecutive_failures` on the checkpoint), quality-report generation,
and timeline events. `SyncTrigger.LIVE` always bypasses the incremental skip — live fixtures
poll every 30s regardless of the last sync time, everything else respects its interval.

**Data Validation Engine is stateless and pre-persistence**: `DataValidationEngine` validates
provider DTOs — schema/required fields, relationships (no fixture with identical home/away
team), duplicates (batch-level, via `find_duplicate_refs`), date/competition/season
consistency, provider integrity (every ref in a fixture shares the fixture's provider) — before
a record ever reaches `EntityReconciliationService`. Invalid records are rejected, not
persisted; the sync run still succeeds (as PARTIAL) with the rejection counted.

**Ingestion-level Data Quality Engine is distinct from Feature Quality (§5c)**:
`IngestionQualityEngine` scores *raw ingested provider data* (completeness, consistency,
freshness, accuracy, validity, reliability, coverage, provider quality, composite quality
score) — `FeatureQualityEngine` scores *derived ML features*. Same shape (windowed metrics,
persisted report, documented formula), different layer of the pipeline, never merged into one
engine because "is the raw data good" and "is the derived feature good" are different
questions with different remediation paths.

**Feature Pipeline Foundation is architecture only**: `FeaturePipeline`
(Raw → Normalized → Validated → Clean → `FeatureCalculatorPort` → Feature Store) exists and is
tested with zero registered calculators — no sport-specific engineered feature exists yet, per
the constitution's explicit Milestone 5 scope. Milestone 6+ registers the first real
calculators against this same pipeline.

**Knowledge Graph population** (Milestone 5 scope, now one layer of a larger platform — see
§5e): `modules/knowledge_graph/` (`KGNode`, `KGEdge`, `KnowledgeGraphPopulationService`) is
called directly by `EntityReconciliationService` after each entity is persisted — there is no
separate "graph sync" pass. See [knowledge_graph.md](knowledge_graph.md) for node/edge types.

**Redis integration beyond the feature-store cache (§5b)**: `RedisDistributedLock`
(SET NX EX + ownership-token GET/DEL release — deliberately not redis-py's built-in `Lock`,
whose release relies on EVALSHA/Lua scripting that `fakeredis` doesn't support, see
[decisions.md](decisions.md)) and `RedisSyncCache` (generic JSON get/set/delete with TTL, for
sync results and provider ETags — deliberately untyped, unlike `OnlineFeatureStorePort`, since
ingestion caches heterogeneous things).

**Celery background processing**: a real `Celery` app (`celery_app.py`) with Redis as broker
and result backend, `task_acks_late` + bounded `worker_prefetch_multiplier=1`, a `live` queue
(routed via `task_routes`) for live-fixture syncs and a `default` queue for everything else, a
dead letter queue (`dead_letter.py` — a Redis list, not a second Celery queue, since a DLQ is a
record for humans to review, not more work for a worker to pick back up) wired via the
`task_failure` signal once retries are exhausted, and a Beat schedule
(`beat_schedule.py`) with a pure, tested `compute_adaptive_interval()` policy function for
quota-aware scheduling — lengthening sync intervals as a provider's remaining quota shrinks.
Full dynamic runtime rescheduling (a custom `celery.beat.Scheduler` polling live quota state
every tick) is a documented follow-up, not implemented this milestone; what's here is the
policy function a future scheduler would call.

**Monitoring**: `MonitoringService` exposes sync status/duration/records-imported-updated-
rejected/validation-failures (from `SyncRun` history), Redis health (a `PING` + latency), queue
length (`LLEN` on the Celery Redis-backed queue key), and worker health (via
`celery_app.control.inspect()`). Provider health itself is `HealthIntelligenceEngine` (§5a) —
exposed alongside these, never reimplemented.

## 5e. Entity Expansion Matrix

Milestone 5 fully wires 11 representative canonical entities (Sport, Competition, Country,
Season, Venue, Team, Player, Fixture, Match Statistics, Lineup, Standing) end-to-end through
the pipeline above. The remaining constitution-named entities (Rounds, Coaches, Officials,
Player Statistics, Injuries, Suspensions, Transfers, Rankings, Match Events, Historical
Results) have their Milestone 2 domain models but no provider DTO/reconciler/KG population yet
— the full status table, and the rule gating Milestone 6+ prediction markets on it, lives in
[database_schema.md](database_schema.md) §11.

## 5f. Enterprise Identity, Tenancy, Billing & Webhooks (Milestone 6)

Four bounded contexts, each following the standard domain/application/ports/infrastructure
layering (§3), built against a real provisioned Supabase project (`titaniq` —
[supabase.md](supabase.md)) rather than the mock-first placeholder assumption used through
Milestone 5:

```
modules/identity/     User/Profile, RBAC roles, federated identity, PATs, sessions,
                       security events, audit log — see authentication.md, rls.md
modules/tenancy/       Organizations, Teams, Memberships, Invitations
modules/billing/       Plans, Entitlements, Subscriptions, Usage Counters — state only,
                       no payment provider wired
modules/webhooks/      Endpoint registration + delivery/retry ledger — HMAC-signed via
                       the same CredentialVaultPort as modules.admin's provider credentials
```

**Dual authentication path** ([authentication.md](authentication.md), [ADR-025](decisions.md)):
Supabase Auth (GoTrue) is the real production credential store — FastAPI validates its JWTs
(`SupabaseJWKSValidator`, JWKS-based, same asymmetric-key pattern as every other
security-sensitive port in this codebase) and provisions a local `identity.users` shadow row
keyed by the same id as Supabase's `auth.users.id`. A parallel bcrypt-based path
(`IdentityService.register`/`authenticate`) exists purely for the fast offline test suite and
non-Supabase dev, following the same mock-first rationale as `fakeredis`/`FakeSportsProvider`
([ADR-008](decisions.md)).

**Row Level Security is real, not blanket** ([rls.md](rls.md), [ADR-026](decisions.md)): a
single SQL function mirrors the Python RBAC ladder's ordinal comparison
(`identity.has_role_at_least`), so one threshold-based policy per table covers every role above
it. Identity/tenancy/billing/webhooks carry genuine ownership + org-membership + role-ladder
policies; the M2-M5 catalog schemas (no per-user ownership concept) are analyst+ read-only;
security-internal tables (audit log, account lock state) have no self-access policy at all.
Every elevated-read policy is read-only — all writes flow through FastAPI's service-role
connection exclusively, so there is exactly one audited mutation path per table.

**Storage and Realtime are configured, not assumed**: 7 Storage buckets with
ownership-path-convention policies (`{bucket}/{owner_id}/filename`, same shape as the database
RLS ownership checks, just applied to `storage.objects`); 8 of 62 tables enabled for Realtime,
each mapped to a concrete named use case from the Milestone 6 spec rather than enabled
blanket-wide ([ADR-028](decisions.md)).

## 5g. Sports Semantic Intelligence Platform (Milestone 7)

Milestone 7 extends `modules/knowledge_graph/` from a population-only write path (Milestone 5,
§5d) into the platform every future AI subsystem (Explainability, AI Assistant, Recommendation
Engine, future RAG) is meant to obtain contextual intelligence from, rather than each rebuilding
relationship logic independently:

```
modules/knowledge_graph/
  domain/          KGNode/KGEdge gain provider_refs, aliases, source, version, status,
                     confidence, created_at/updated_at, merged_into (all defaulted — additive,
                     no breaking change to Milestone 5 call sites); NodeType/EdgeType complete
                     the full ontology (see ontology.md) as additive enum members
  ports/             GraphQueryPort (Subgraph), SimilarityPort, GraphRetrievalPort
  application/         GraphQueryService, EntityResolutionService, SimilarityService,
                         SemanticSearchService, ContextEngine, TemporalGraphService,
                         GraphPopulationBatchService, GraphMonitoringService
  infrastructure/        similarity/graph_structural.py (Jaccard-overlap heuristic),
                         caching/cached_node_repository.py (generic SyncCachePort reuse),
                         retrieval/graph_native_retrieval.py (structured facts, no LLM)
```

**Graph Query Engine is pure-Python BFS, not recursive SQL CTEs** ([ADR-029](decisions.md)):
`GraphQueryService` implements shortest path, neighborhood/subgraph expansion, relationship
traversal (forward/reverse), connected components (union-find), and historical
snapshot/timeline queries by walking `KGEdgeRepositoryPort.list_from`/`list_to` in Python —
portable across the SQLite fast-test engine and Postgres without dialect-specific SQL, and
simple enough to reason about at this milestone's traffic scale, the same "relational not graph
DB" scope call ADR-005 already made one level up. Every traversal is bounded (`max_nodes`/
`max_hops`/`max_depth`).

**Entity Resolution is non-destructive**: `EntityResolutionService.merge()` never deletes a
duplicate node — it marks `status="merged"` with a `merged_into` pointer, redirects the
duplicate's edges onto the canonical node via the existing idempotent `upsert_edge`, and folds
aliases/provider_refs into the canonical. `resolve_canonical()` follows merge chains (with a
cycle guard) to the current canonical node. Original edges are left as historical record.

**Similarity is a framework, not ML**: `SimilarityPort` has exactly one implementation this
milestone, `GraphStructuralSimilarity` (Jaccard overlap of shared graph neighbors) — real,
deterministic, explainable, and enough to serve every entity kind the ontology names (Player,
Team, Coach, Venue, Competition, Model, Feature) identically, since the metric only cares which
other nodes an entity is connected to. A future embedding-backed adapter implements the same
port without touching `SimilarityService` or any consumer (ADR-008's mock-first/adapter-swap
pattern, applied here).

**Context Engine is one builder, many names**: `ContextEngine.build_context()` does a bounded
neighborhood expansion and groups the result by `NodeType` — every named `context_for_*` method
(fixture, match, player, team, competition, prediction, news, feature, model, explainability,
historical comparison) is a thin wrapper choosing a depth/breadth appropriate to that entity's
typical fan-out, not a distinct implementation, mirroring the Similarity Engine's "one metric,
many entity kinds" shape.

**Temporal Graph adds exactly one new operation**: time-valid edges (`valid_from`/`valid_to`)
and historical snapshot/traversal already existed via Milestone 5's schema and this milestone's
`GraphQueryService.at_time`/`edge_history`. `TemporalGraphService.supersede_edge()` is the one
addition — closes an old edge and opens a new one in a single explicit call, for a genuine
relationship transition (e.g. a transfer) as opposed to `upsert_edge`'s in-place idempotent
update of an unchanged relationship. Entity Evolution is derived from edge history (opened/
closed events) rather than a new node-versioning table — the graph stays relational, not
event-sourced.

**Graph Performance**: composite indexes on `(from_node_id, edge_type)`/`(to_node_id,
edge_type)` (migration 0016) serve `GraphQueryService`'s combined traversal filter directly.
`CachedKGNodeRepository` is a read-through decorator over `KGNodeRepositoryPort` reusing
`modules.ingestion`'s existing generic `SyncCachePort`/Redis integration (Milestone 5, §5d) — no
new caching concept introduced. `GraphMonitoringService` exposes node/edge counts by type,
population/traversal timing, cache hit ratio, merge/duplicate counts, and an
"Entity Resolution Accuracy" proxy metric (merges ÷ (merges + detected duplicates) — explicitly
documented as a proxy, since there is no ground-truth label this milestone).

**RAG Foundation is retrieval-only** — `GraphRetrievalPort`/`GraphNativeRetrieval` turn a bounded
neighborhood expansion into structured `RetrievalDocument`s (subject/relation/related/confidence/
source). No embeddings, no vector search, no prompt construction, and no LLM call exist in this
port or its implementation — those are RAG itself, explicitly out of scope this milestone.

**API surface** (`apps/api/routers/graph_router.py`, `/api/v1/graph`): Entity Search,
Relationship Search, Graph Traversal (traverse + shortest-path), Timeline Queries (edge history
+ at-time snapshot), Similarity Queries, Context Queries, Neighborhood Queries, Graph
Statistics — read-only, gated at `get_current_user` (any authenticated user; graph data is not
per-organization/per-user sensitive the way billing or PATs are, matching RLS's broad-read
posture, [rls.md](rls.md)).

## 5h. News Intelligence & Community Intelligence Platform (Milestone 8)

Milestone 8 turns `modules/intelligence/` from a bare Gemini text-intelligence port (Milestone
3) into a complete pipeline that transforms unstructured news and community content into
structured, Knowledge-Graph-linked, Feature-Store-consumable intelligence — while never
producing a prediction probability. Organized by layer (domain/application/ports/
infrastructure), same as every other module, rather than by capability
([ADR-036](decisions.md)):

```
modules/intelligence/
  domain/          NewsSource, NewsArticle, NewsEvent, SourceReliabilityScore, SentimentResult,
                     ImpactScore, Summary, CommunityPost, CommunityTopic, IntelligenceSyncRun/
                     Checkpoint (News/Community share one sync-tracking shape)
  ports/             TextIntelligenceProviderPort (extended, additive — see below),
                       NewsProviderPort, CommunityProviderPort, IntelligenceRetrievalPort,
                       repository ports for every domain entity above
  application/         NewsIngestionService, CommunityIngestionService,
                         EntityExtractionService, EventExtractionService,
                         SourceReliabilityService, SentimentService, NewsImpactEngine,
                         SummarizationService, KnowledgeGraphEnrichmentService,
                         FeatureStoreEnrichmentService, IntelligenceRetrievalService,
                         IntelligenceMonitoringService
  infrastructure/        mock/RSS news providers, mock community provider, real+mock Gemini
                         adapters (Milestone 3, extended), SQLAlchemy persistence
```

**`TextIntelligenceProviderPort` grows additively, never toward prediction** ([ADR-037](decisions.md)):
Milestone 3's four methods (`extract_events`, `summarize`, `explain`, `interpret_sentiment`)
are unchanged; Milestone 8 adds `extract_entities` (NER), `extract_relationships`,
`classify_topics`, `detect_language`, `extract_key_phrases` — every one incapable of returning a
probability, the same architectural guardrail the port has carried since Milestone 3.

**News Ingestion and Community Intelligence share one sync-tracking shape, not one pipeline**:
`IntelligenceSyncRun`/`IntelligenceSyncCheckpoint` mirror `modules.ingestion`'s
`SyncRun`/`SyncCheckpoint` (Milestone 5) — incremental sync via checkpoint, one run record per
execution, retry via consecutive-failure tracking — without importing Milestone 5's sports-
specific types, per the "maintain complete separation" instruction. News dedup is a persistent
content-hash index (a republished article, at any time in the future, resolves to the same
row); Community dedup is in-batch content-hash plus platform-external-id, deliberately *not* a
permanent index — a repeated "yes!!" tweet is not a meaningful cross-time duplicate the way a
republished article is ([ADR-038](decisions.md)).

**Entity/Event Extraction resolves against the graph but does not autonomously populate it**:
`EntityExtractionService` calls `EntityResolutionService.find_by_alias` (Milestone 7) to link a
mention to an existing node; an unresolved mention is returned as such, not silently turned into
a new node. `KnowledgeGraphEnrichmentService` (Milestone 8) is the one place that writes —
creating a node for a confirmed-new entity, adding a discovered alias, or transitioning an edge
(`TemporalGraphService.supersede_edge`, Milestone 7) — and only for event types with an
unambiguous target (`TRANSFER` → `PLAYS_FOR`, `MANAGER_CHANGE` → `COACHED_BY`); an `INJURY`
event with no linked match/venue enriches nodes/aliases but creates no edge, since guessing a
relationship the article didn't establish is worse than enriching nothing ([ADR-039](decisions.md)).

**Feature Store enrichment is generic, not sport-specific**: ten features (Injury Impact,
Transfer Stability, Manager Stability, Community Momentum, News Momentum, Squad Availability,
Media Pressure, Travel Fatigue, Weather Impact, Source Reliability) are registered with
`sport_code="generic"` and `category=CONTEXTUAL`, through the same DRAFT → IN_REVIEW → ACTIVE
workflow every other feature uses (Milestone 4) — a "system" reviewer approves them since no
human authored the definitions, but they're consumable exactly like any other ACTIVE feature
([ADR-040](decisions.md)).

**RAG Foundation extends, not replaces, Milestone 7's**: `modules.intelligence.ports.retrieval`
defines a modality-general `IntelligenceRetrievalPort` for News/Community/AI-Reports sources
that aren't graph nodes; `KnowledgeGraphRetrievalAdapter` wraps Milestone 7's
`GraphRetrievalPort` to serve the Knowledge Graph modality through the same facade
(`IntelligenceRetrievalService.retrieve_all`) rather than duplicating it. No embeddings, no
vector search, no LLM prompting layer exist anywhere in this extension, same as Milestone 7's
own RAG Foundation scope ([ADR-041](decisions.md)).

**Source Reliability starts from structural fact, then earns/loses trust**: an official source
(`NewsSource.is_official`) starts at `TrustLevel.OFFICIAL` immediately — official-ness is a
classification, not something earned over time — but a reliability score that craters below
0.2 still demotes it. `reliability_score`/`historical_accuracy` update via an exponentially-
weighted moving average toward each new observed outcome, so a source's score tracks recent
behavior more than any single stale data point ([ADR-042](decisions.md)).

**API surface** (`apps/api/routers/intelligence_router.py`, `/api/v1/intelligence`): News
Search, News Timeline, Entity News, Community Topics, Sentiment, Impact Scores, Summaries,
Source Reliability, News Analytics — read-only, gated at `get_current_user`, the same broad-read
posture as `graph_router.py` (Milestone 7). RLS (added retroactively in Milestone 9's closure
pass, migration 0022 — see [decisions.md](decisions.md) ADR-049): the 7 tables this router
directly serves are free+ (mirroring `get_current_user`'s own posture); `news_sources`/
`community_posts`/`intelligence_sync_runs`/`intelligence_sync_checkpoints` are analyst+.

## 5i. Prediction Intelligence Platform (Milestone 9)

`modules/predictions/` is the enterprise Prediction Intelligence Platform — the only place a
probability is computed from engineered features, never from an LLM. Full pipeline, data model,
and per-component detail live in [prediction_engine.md](prediction_engine.md); summary here:

**Data-driven Market Registry, not a class per market**: `MarketDefinition` rows carry a
`MarketKind` (8-value enum — the reusable computational strategy a market needs: `BINARY`,
`SPREAD`, `TOTAL`, `TEAM_TOTAL`, `PLAYER_PROP`, `CORRECT_SCORE`, `RACE_TO`, `SEGMENT_WINNER`), so
two real `PredictorPort` implementations (`WeightedLogisticPredictor`/`WeightedLinearPredictor`)
serve every named market across all four sports ([ADR-043](decisions.md)). `FeatureMarketMapping`
rows are the "no model may consume features outside its registered mapping" enforcement point
(`FeatureMarketMappingService.resolve_feature_snapshot`).

**Pipeline**: Feature Store → Feature Selection → Market Selection → Market Feature Retrieval
(`PredictionContextBuilder`) → Prediction Model (`PredictorRegistry`) → Probability Calibration
(`PlattScalingCalibrator`) → Confidence Engine (9-factor `ConfidenceBreakdown`) → Explainability
Engine (composes Milestone 7 Knowledge Graph + Milestone 8 retrieval + Gemini's `explain()`) →
`PredictionEngine.generate()` (pure, no persistence) → `PredictionCacheService` (cache/version/
confidence-threshold-gated publish/audit).

**Predictors are real, not mocked, and honestly scoped as v1**: no labeled historical outcome
dataset exists yet to train a model against, so both `PredictorPort` implementations are real,
deterministic weighted linear/logistic scoring — the same mock-first/adapter-swap posture
(ADR-008) every other external-capability port in this codebase already follows
([ADR-044](decisions.md)).

**Champion/Challenger**: `ModelRegistryService` enforces exactly one CHAMPION per market
(`ModelStatus`: CANDIDATE → CHALLENGER → CHAMPION → RETIRED), with `rollback()` reinstating the
most-recently-retired model.

**Windowed feature engineering** (`RollingTeamStatAverageCalculator`) computes each sport's own
declared `TeamStatistics` schema field (football's `shots_on_target`, basketball's `points`,
baseball's `runs`, table tennis's `points_won`) rather than an invented universal scoring field
([ADR-046](decisions.md)) — direct-compute-then-write against the Feature Store, the same shape
Milestone 8's `FeatureStoreEnrichmentService` established.

**Per-sport market seeding** (`modules.predictions.{football,basketball,baseball,table_tennis}`)
registers a representative, not literally exhaustive, market set per sport, each promoted to
PRODUCTION with a real registered feature behind it ([ADR-048](decisions.md)) —
[prediction_markets.md](prediction_markets.md) §5 has the full list.

**API surface**: `/api/v1/predictions` (resource: generate/get/list/approve/reject, plus
confidence/explanation/history/monitoring/statistics/compare sub-resources — split across
`prediction_router.py`/`prediction_analytics_router.py`), `/api/v1/markets` (registry +
feature-to-market mapping lifecycle), `/api/v1/admin/predictions` (`Role.ADMINISTRATOR`-gated
dashboards + Recompute/Rollback Admin Actions, `prediction_admin_router.py`).

**Persistence**: schema `predictions` (migration `0018`) — `prediction_markets`,
`feature_market_mappings`, `models`, `predictions`, `prediction_outcomes`, `model_evaluations`,
`experiments`, `prediction_audits`. Realtime enabled on `predictions`/`prediction_markets`/
`prediction_audits` plus `features.feature_values_offline` (migration `0019`) — the last one closes a
gap left open since Milestone 6 first named "Feature Updates" in the realtime spec without ever
wiring it. RLS (migrations 0020-0021): tiered by what each table is, not blanket analyst+ — app-facing
`predictions`/`prediction_markets` are free+ (any real authenticated user, matching the API's own
`get_current_user` posture), registry/operational tables are analyst+, `prediction_audits` is
administrator+ only (mirrors `identity.audit_log_entries`). Discovered and closed alongside an
identical, pre-existing gap on the Milestone 8 `intelligence` schema (migration 0022) — see
[decisions.md](decisions.md) ADR-049 and [rls.md](rls.md) §6a/§6b.

## 5j. Enterprise Machine Learning Platform (Milestone 9.1)

`modules/predictions/` gains a real ML layer behind the exact same `PredictorPort` — "Prediction
Engine interfaces must NEVER change. Only the predictor implementations may change." Full detail
in [machine_learning.md](machine_learning.md), [training_pipeline.md](training_pipeline.md),
[model_registry.md](model_registry.md), [experiments.md](experiments.md),
[calibration.md](calibration.md); summary here:

**Framework adapters, not a hardcoded model**: `PredictionModelPort` — a lower-level port beneath
`PredictorPort` — is implemented by real LightGBM/XGBoost/CatBoost adapters plus one parametrized
`SklearnAdapter` covering 8 more algorithms (Random Forest, Extra Trees, Logistic Regression,
Ridge, Elastic Net, SVM, Gaussian NB, MLP). `TrainedModelPredictor` is the one `PredictorPort`
implementation wrapping a fitted model; `PredictorRegistry` gained market-key resolution
(`register_for_market`, ADR-050) alongside its existing `MarketKind` resolution, since a specific
trained champion — unlike the weighted predictors — needs its own market identity, not just a
shared kind.

**Dataset & Training Platform**: `DatasetBuilder` sources every training sample exclusively from
`Prediction.feature_snapshot` — "no algorithm may bypass the Feature Store" enforced by
construction, not convention (ADR-052). Approval workflow (DRAFT → VALIDATED → APPROVED →
ARCHIVED), 6 split strategies, drift detection, content-hash reproducibility.
`TrainingPipelineService` wires impute → outlier detection → feature selection → split → fit
(native early stopping) → evaluate. 9 validation strategies, 5 HPO strategies (Grid/Random/
Successive-Halving/Bayesian/Optuna-generic).

**Automatic Model Selection**: "Never hardcode algorithm selection" (ADR-054) — trains a
configurable roster of up to 11 algorithms per market, ranks on real held-out metrics, registers
and promotes the actual winner to CHALLENGER, records the full benchmark (winner, every candidate
considered/skipped) as an `Experiment`.

**Ensemble Learning**: Soft/Hard/Weighted Voting, Stacking/Blending, Dynamic Selection — every
ensemble is itself a `PredictorPort` combining other `PredictorPort` members (ADR-055), so a
trained model and a weighted-heuristic fallback can sit in the same ensemble uniformly.

**Calibration**: Isotonic Regression and Temperature Scaling join Milestone 9's Platt Scaling;
`CalibrationReportBuilder` computes reliability curves/Expected Calibration Error/Brier score.

**SHAP Explainability**: `SHAPExplainerService` duck-types explainer choice on the fitted
estimator (`TreeExplainer` vs. `KernelExplainer`, ADR-056) rather than checking frameworks by
name — global/local importance, interaction values, an honestly-reinterpreted "decision path" for
ensembles, a real bounded counterfactual search, dependence plots.
`ExplainabilityEngine.explain_with_shap()` composes the existing `explain()` unchanged.

**Model Monitoring & Serving**: `ModelMonitoringService` extends `PredictionAdminService` with
latency/volume/concept-drift/confidence-drift/model-health, reusing (not duplicating)
probability-drift and feature-drift where they already exist. `ModelLoaderService`/
`ModelVersionResolver`/`BatchPredictionService`/`AsyncPredictionQueueService` round out Model
Serving — the async queue singleton never holds a database session itself (ADR-057). ONNX export
stays interface-only, matching the spec's own forward-looking framing (same posture as Milestone
7's RAG-foundation retrieval port).

**API surface**: `/api/v1/admin/ml/*` (`ml_platform_router.py`, `Role.ADMINISTRATOR`-gated) —
training, experiments, model registry, champion, feature-importance, calibration, benchmark,
monitoring, retraining, evaluation. `prediction_admin_router.py` (Milestone 9) untouched.

**Persistence**: migration `0023` adds `datasets`, `training_runs`, `calibration_reports`,
`feature_importance_reports`, `latency_samples`, `retraining_jobs`, `model_artifacts`, plus 9
additive `models` columns; RLS (migration `0024`) analyst+ across all 7 new tables, matching the
existing Model Registry tier.

## 5k. Enterprise Frontend Platform (Milestone 10)

`frontend/` — React 19 + TypeScript + Vite, a strict presentation layer over `backend/apps/api`.
Full detail in [frontend_architecture.md](frontend_architecture.md),
[design_system.md](design_system.md), [ui_components.md](ui_components.md),
[user_flows.md](user_flows.md); summary here.

**No backend architecture/API/DTO/business-logic changes beyond what this milestone's own
mandatory backend audit required**: (1) ~41 endpoints defined directly in `apps/api/main.py`
(Provider Management, Feature Registration/Flags/Quality, Sync triggers, Redis/KG monitoring) had
no auth dependency at all — closed with `require_role(Role.ADMINISTRATOR)`, the same mechanism
already used elsewhere, user-approved before implementation (docs/security.md §8); (2) a new
read-only `sports_router.py` (12 endpoints) plus one additive repository method
(`PlayerRepositoryPort.list_by_sport`) — nothing before this milestone exposed competitions/teams/
matches/players to the frontend at all; (3) one new single-article lookup endpoint
(`GET /api/v1/intelligence/news/articles/{id}`) using the existing repository's `get()`. CORS
middleware was added to `apps/api/main.py` (required for any browser origin to call the API at
all — infrastructure, not an API contract change).

**Typed client, not codegen**: the backend defines no Pydantic response models (every route
returns a hand-built dict via a local `_serialize_*` function), so `frontend/src/lib/api/types.ts`
mirrors those shapes by hand, one interface per `_serialize_*`, one API module per backend router.

**Auth**: production auth is Supabase Auth directly from the browser (matching
docs/authentication.md's documented split — FastAPI's own `/auth/register`/`/login` stays the
offline/mock test path). `GET /api/v1/users/me` hydrates the platform role after Supabase
sign-in; RBAC-gated routes/nav use the same ordinal `Role` comparison as the backend.

**Realtime**: subscribes directly to Supabase Realtime on the 12 already-published tables
(migrations 0014 + 0019) — no new backend push mechanism, no WebSocket/SSE endpoints added.

## 5a. Provider Management System & Health Intelligence

Provider registration, encrypted credentials, quota tracking, circuit breaking, and health
monitoring are centralized in the `admin` bounded context (`modules/admin/`) — the backend for
the future Admin Control Center (Milestone 15), built early per the provider configuration
directive so every provider adapter has real infrastructure to plug into from day one:

```
modules/admin/
  domain/          ProviderDefinition, ProviderCredential, ProviderUsageRecord,
                     ProviderHealthCheck, ProviderHealthState, ProviderIncident, FeatureFlag
  ports/             CredentialVaultPort, {Provider,Credential,Usage,Health,HealthState,Incident,FeatureFlag}RepositoryPort
  application/         ProviderManagementService, QuotaIntelligenceEngine, CircuitBreaker,
                         HealthIntelligenceEngine, FeatureFlagService
  infrastructure/        FernetCredentialVault, SQLAlchemy persistence for all of the above
```

`FeatureFlag` lives here rather than in `modules/features/` — it gates platform availability
(sports/markets/subsystems not ready for GA), an admin/operations concern, not part of the ML
Feature Intelligence Platform in §5b below. Same word, deliberately different bounded contexts
— `docs/decisions.md` ADR-015 covers the deterministic (hashed, non-random) rollout evaluation.

**HealthIntelligenceEngine** is the automatic-scoring layer: every recorded health check
(`record_check`) updates a per-provider `ProviderHealthState` (consecutive failures, current
status) in O(1) — no rescanning history — and opens/escalates/resolves a `ProviderIncident`
automatically as status crosses HEALTHY → DEGRADED → DOWN and back. Windowed metrics (success/
failure rate, latency average and p50/p95/p99, availability, daily/monthly uptime, historical
trend) are computed on demand from the append-only `ProviderHealthCheck` history — nothing is
pre-aggregated or can go stale. See [decisions.md](decisions.md) ADR-011 and ADR-012 for the
rolling-state design and the reliability-score formula.

Other modules consume this through the same port pattern as everything else — `SportsProviderRouter`
(§5) calls into `ProviderManagementService`/`QuotaIntelligenceEngine`/`CircuitBreaker` on every
real request; nothing about a provider's health or quota state is decided at the call site.

## 5b. Feature Intelligence Platform

`modules/features/` (Milestone 4) is the bounded context backing [feature_catalog.md](feature_catalog.md)
— the single source of truth every prediction model eventually reads features through:

```
modules/features/
  domain/          FeatureDefinition, FeatureDefinitionVersionSnapshot, FeatureValue,
                     FeatureLineageEdge, FeatureDriftReport (data model only — no computation yet),
                     FeatureValidationReport, FeatureComputationLog, FeatureConsumer, FeatureUsageRecord
  ports/             {Definition,Version,Value,Lineage,DriftReport,ValidationReport,
                        ComputationLog,Consumer,Usage}RepositoryPort, OnlineFeatureStorePort,
                        ProviderReliabilityPort (cross-module, see §5c)
  application/         FeatureRegistrationService, FeatureLineageService, FeatureStoreService,
                         FeatureQualityEngine (§5c)
  infrastructure/        persistence/ (Postgres offline store), online/redis_feature_store.py
```

**Registration is a workflow, not a table insert**: `FeatureRegistrationService` drives
DRAFT → IN_REVIEW → ACTIVE → DEPRECATED → REMOVED. Only `approve()`, naming a human reviewer,
moves a feature to ACTIVE — the same human-gated-promotion shape as Champion/Challenger model
deployment (§"AI Governance" in [titaniq.md](titaniq.md)). `FeatureStoreService.write()` refuses
production writes for a non-ACTIVE feature by default, which is how "no model may consume an
undocumented feature" (docs/feature_catalog.md) is actually enforced today, not just stated.

**Lineage is a leakage guardrail**: `FeatureLineageService` rejects any dependency that isn't
already a registered feature (no forward references) and rejects anything that would create a
cycle, direct or transitive — both are exactly the shape a leakage bug takes, so the graph check
doubles as a leakage check.

**Online/offline is one write, two stores**: `FeatureStoreService.write()` always writes offline
(Postgres, durable/audited) then online (Redis, TTL-bound cache) — there's no "online-only"
write path. Reads prefer online, falling back to offline on a cache miss. See
[decisions.md](decisions.md) ADR-008 for why the Redis adapter is tested against `fakeredis`
rather than a hand-rolled in-memory substitute (same mock-vs-real-adapter reasoning as
providers, applied to a cache instead of an external API).

## 5c. Feature Quality Intelligence

`FeatureQualityEngine` (`modules/features/application/feature_quality_engine.py`) is the
automatic-scoring layer for feature data, mirroring §2a's `HealthIntelligenceEngine` shape
deliberately: windowed metrics computed on demand from append-only `FeatureValue` history
(never pre-aggregated), a persisted report type for point-in-time verdicts
(`FeatureValidationReport`), and every score's formula documented rather than left as a magic
number.

Per-feature it tracks: quality/freshness/reliability/completeness scores; missing/outlier/null/
invalid/duplicate percentages and coverage %; validation history; provider source and
reliability (via `ProviderReliabilityPort`, ADR-016); computation cost, average duration, and
memory footprint (`FeatureComputationLog`); an estimated storage size (ADR-018); consumer
registrations (`FeatureConsumer` — empty until Milestone 6+ models exist to register);
usage frequency (`FeatureUsageRecord`, same daily-bucket pattern as
`ProviderUsageRecord`); and an advisory deprecation warning. `health_report()` assembles all of
it into one composite read, the same pattern as `ProviderDiagnosticsReport`.

Two honestly-documented limitations, not oversights: "Null %" and "Missing Value %" compute
identically today because `FeatureValue.value` has no explicit null representation (ADR-017);
"Storage Size" is a JSON-size estimate, not a live Postgres query, since no live Postgres exists
in this environment yet (ADR-018).

## 6. AI Subsystem Interfaces

Each AI subsystem from [titaniq.md](titaniq.md) §5 is a `ports/` interface plus an
`infrastructure/ai/` implementation, so a subsystem can be swapped (e.g., replace a
heuristic Confidence Engine with a learned one) without touching callers:

| Subsystem | Port | Primary consumer |
|---|---|---|
| Feature Intelligence Platform | `OnlineFeatureStorePort` + `{Definition,Value,Lineage}RepositoryPort` (`modules/features/`, built Milestone 4 — see §5b) | predictions, analytics |
| Prediction Intelligence Platform | `PredictorPort`/`CalibratorPort`, keyed by `MarketKind` not per named market (`modules/predictions/`, built Milestone 9 — see §5i); `PredictionModelPort` — the lower-level framework-independence seam LightGBM/XGBoost/CatBoost/scikit-learn adapters implement (Milestone 9.1, §5j) | api, admin |
| Confidence Engine | `ConfidenceEngine` — plain aggregation over 9 real signals, no separate port yet (§5i) | predictions response assembly |
| Explainability Engine | `ExplainabilityEngine` — composes KG retrieval + news/community retrieval + Gemini's `explain()` (§5i); `explain_with_shap()` additionally composes real SHAP values via `SHAPExplainerService` when the predictor is ML-backed (Milestone 9.1, §5j) | predictions response assembly |
| Outcome Learning Engine | `OutcomeEvaluatorPort` | scheduled worker, triggered on MatchCompleted |
| Knowledge Graph | `KGNodeRepositoryPort`/`KGEdgeRepositoryPort` (population, Milestone 5, §5d) + `GraphQueryPort`/`SimilarityPort`/`GraphRetrievalPort` (full Sports Semantic Intelligence Platform, Milestone 7, §5g) | ingestion (write); recommendations/explainability/AI Assistant/future RAG (read) |
| Recommendation Engine | `RecommenderPort` | personalization, api |
| News Intelligence | `TextIntelligenceProviderPort` (`modules/intelligence/`, Gemini-backed — Milestone 3 port, full News Intelligence Platform Milestone 8, §5h) | Knowledge Graph, Feature Store, explainability, future Recommendation Engine |
| Community Intelligence | Same `modules/intelligence/` bounded context — `CommunityIngestionService` (Milestone 8, §5h) | features (supporting only, never primary) |

`TextIntelligenceProviderPort` is deliberately narrow: `extract_events`, `summarize`, `explain`,
`interpret_sentiment` (Milestone 3) plus `extract_entities`, `extract_relationships`,
`classify_topics`, `detect_language`, `extract_key_phrases` (Milestone 8, additive) — no method
on this port could be used to source a prediction probability from an LLM instead of a trained
model, per the provider configuration directive.

## 7. Data Flow (high level)

```
[Providers] --adapters--> [Ingestion] --normalize--> [Domain entities]
   --> [Feature Store] --> [Prediction Intelligence Platform] --> [Confidence + Explainability]
   --> [API response / cached read-model]

[MatchCompleted event] --> [Outcome Learning Engine] --> updates feature reliability,
   model performance metrics, drift detectors --> [AutoML Engine] evaluates retrain trigger
   --> Champion/Challenger workflow --> (human-gated) promotion
```

Provider ingestion and inference are decoupled via the event bus so that a slow/degraded
provider cannot block API latency — cached/last-known-good features are served with a staleness
flag rather than blocking.

## 8. Technology Stack

| Layer | Choice |
|---|---|
| Database | Supabase (PostgreSQL, Auth, Storage, Realtime, Row-Level Security) |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, AsyncIO, Redis, Celery, Flower |
| Frontend | React 19, TypeScript, Tailwind CSS v4, Vite 8, TanStack Query + Virtual, Zustand, Radix UI, react-hook-form + zod, cmdk, Recharts (installed, not yet wired — no live endpoint returns time-series data), React Router 7, Supabase JS (Auth + Realtime), vite-plugin-pwa |
| ML | XGBoost, LightGBM, CatBoost, PyTorch, scikit-learn, SHAP, ONNX (export where it simplifies serving) |
| Infra | Docker, Docker Compose (local), Railway (services), Vercel (frontend), GitHub Actions (CI/CD), Nginx, Redis |

Rationale for each is in [decisions.md](decisions.md) (ADR-001 through ADR-005).

## 9. Non-Functional Targets (funded-team scale)

These are targets to design against from Milestone 1, not just aspirations for later:

- **Availability**: 99.9% for the API tier (≈43 min/month budget), degraded-but-serving during
  provider outages via cache fallback.
- **Latency**: p95 < 300ms for cached prediction reads, p95 < 2s for cold/uncached inference.
- **Scalability**: horizontally scale API and worker tiers independently; no in-process state
  that prevents running N replicas.
- **Observability**: every request traced end-to-end (structured logs + OpenTelemetry traces +
  metrics) from Milestone 2 onward — not bolted on later.
- **Data isolation**: Row-Level Security enforced at the database layer for every
  user-scoped table, never relied on solely at the application layer.

## 10. Cross-Cutting Concerns

- **Config**: environment-driven (12-factor), validated at startup via Pydantic settings models
  per module — fail fast on missing/invalid config.
- **Secrets**: never in code or plain env files committed to the repo; provider API keys are
  encrypted at rest (see [security.md](security.md)).
- **Migrations**: Alembic, one linear history, reviewed like code — no manual schema edits in
  any environment.
- **Feature flags**: config-driven, checked in `admin_center` module, used to gate new
  prediction markets / sports / AI subsystems before general availability.

## 11. What This Document Does Not Cover

Detailed schema → [database_schema.md](database_schema.md). Endpoint-level API contracts →
[api_specification.md](api_specification.md). Feature/model lifecycle detail →
[feature_catalog.md](feature_catalog.md) and the AI sections of the constitution. Milestone
sequencing → [roadmap.md](roadmap.md).
