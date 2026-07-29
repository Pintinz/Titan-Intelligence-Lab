# TitanIQ — Roadmap: 20 Milestones

Status: This is Milestone 1's deliverable. **Do not begin Milestone 2 until this roadmap and
the rest of the foundation docs are explicitly approved.**

## Definition of Done (applies to every milestone)

A milestone is not complete unless, at the end of it:

1. Code is production-quality — no placeholder implementations, no TODOs standing in for
   required behavior.
2. Unit tests and integration tests exist and pass in CI.
3. The relevant living document(s) in `docs/` are updated in the same PR as the code.
4. A new [decisions.md](decisions.md) entry exists for any non-trivial architectural choice
   made during the milestone.
5. The system remains deployable — no previously completed milestone is broken.
6. A short milestone summary (architecture recap, what was built, what was decided, what's
   open) is presented, and explicit approval is given before the next milestone starts.

## Milestones

**1. Engineering Foundation & Documentation** *(this milestone)*
Architecture, documentation structure, engineering standards, 20-milestone roadmap. No
production code. Deliverables: everything in `docs/`. Gate: user approval.

**2. Data Layer & Core Domain Models** — ✅ complete (2026-07-25)
Postgres schema per [database_schema.md](database_schema.md), Alembic migration pipeline, domain
entities + sport plugin contracts ([architecture.md](architecture.md) §4) for
Football/Basketball/Baseball/Table Tennis with no provider wiring yet. Repository pattern
implementations (SQLAlchemy 2.x async). 45 unit tests passing.
Delivered under `backend/modules/sports/` — see `backend/alembic/versions/0001_initial_sports_schema.py`
for the schema migration. **Deferred to Milestone 3**: RLS policies (require a live Supabase
project to apply against) and the `identity`/`billing`/`content` schema tables (out of this
milestone's scope — `sports` schema only, per the roadmap's original title).

**3. Identity, API Gateway & Provider Foundation** — 🟡 provider foundation complete (2026-07-25), identity deferred
Scope changed mid-milestone by the provider configuration directive: rather than wiring real
provider keys, the full **Provider Management System** (docs/admin_center.md §2) was built as a
permanent enterprise subsystem now, backend-only (UI in Milestone 15) — see
`backend/modules/admin/` and `backend/modules/sports/infrastructure/providers/`. Delivered:
- Provider registry, encrypted multi-credential storage (Fernet, [ADR-010](decisions.md)) with
  rotation, priority, and status (active/inactive/maintenance).
- Quota Intelligence Engine: daily/monthly usage tracking, exhaustion prediction, alert
  threshold, priority-aware throttling (live traffic never throttled before background sync),
  credential selection for load-balanced key rotation.
- Circuit breaker (closed/open/half-open) per provider, in-memory.
- `SportsProviderRouter`: automatic mock-vs-real selection per provider ([ADR-008](decisions.md)),
  in-memory TTL response caching (Redis-backed caching arrives with Milestone 4's Feature Store).
- Real adapters (httpx-based) for API-Football, API-Basketball, API-Baseball, and Gemini
  (REST), each paired with a deterministic mock implementing the same port
  ([ADR-009](decisions.md) on the adapter return-type refinement). `ITableTennisProvider`
  interface defined with a working mock, no real implementation (no provider selected —
  docs/titaniq.md §6).
- `TextIntelligenceProviderPort` (Gemini) scoped to non-prediction uses only — no method could
  be used to source a prediction probability from an LLM.
- Minimal FastAPI app (`apps/api/main.py`) proving the composition end-to-end: DB-free health
  check + provider list/activate endpoints.

**Provider Health Intelligence** (2026-07-25 addendum, requested before Milestone 4 could start):
`HealthIntelligenceEngine` (`backend/modules/admin/application/health_intelligence_engine.py`)
extends the Provider Management System with automatic health scoring built entirely on top of
the existing `ProviderHealthCheck` history plus a new materialized `ProviderHealthState`
per provider ([ADR-011](decisions.md)):
- Success/failure rate, average latency, p50/p95/p99 latency, availability %, daily/monthly
  uptime, request throughput — all windowed metrics computed on demand, nothing pre-aggregated.
- Consecutive-failure tracking and automatic HEALTHY → DEGRADED → DOWN classification
  (2 / 5 consecutive failures by default, tunable), running inline on every recorded check.
- `ProviderIncident` history: opens on first degradation, escalates severity in place (never
  downgrades mid-incident), resolves automatically on recovery.
- Provider reliability score and independent per-credential reliability score
  ([ADR-012](decisions.md) for the formula).
- 7/30-day historical health trend, a composite diagnostics report with a plain-language
  recommendation, and `attempt_recovery()` for probe-based recovery (actual periodic scheduling
  of recovery probes needs Celery beat, not wired until a later milestone — this is what that
  job will call).
- Six new dashboard-facing FastAPI endpoints under `/api/v1/admin/providers/{id}/health/*` and
  `/diagnostics`, plus per-credential health.
- New Alembic migration `0002_admin_provider_management_schema.py` — this also retroactively
  covers the Milestone 3 provider tables, which had SQLAlchemy models but no migration until now.

139 backend tests passing (96 from the original Milestone 3 pass + 43 new).

**Deferred to a later pass of Milestone 3** (needs a real Supabase project, which doesn't exist
yet): Supabase Auth integration, RBAC, RLS enforcement tied to real auth claims, full
OpenAPI-first CI pipeline + generated TS client, the remaining route groups in
docs/api_specification.md §2, and rate limiting tied to real user tiers. These block on
infrastructure access, not on design — the architecture in docs/architecture.md §3 and
docs/security.md already accounts for them.

**4. Feature Store Infrastructure & Feature Flags** — ✅ complete (2026-07-25)
`features` schema live, online (Redis) + offline (Postgres) feature serving, feature
registration workflow with leakage-review gate, feature flag system for gating incomplete
sports/markets. Delivered under `backend/modules/features/` and `backend/modules/admin/`:
- **Offline store** (Postgres, `features` schema): `feature_definitions`,
  `feature_definition_versions`, `feature_values_offline`, `feature_lineage`,
  `feature_drift_reports` — the last is a data model only, no drift *computation* yet (that's
  Milestone 11, wired to Outcome Learning, per the original roadmap sequencing).
- **Online store**: `RedisFeatureStore` implementing `OnlineFeatureStorePort` — real
  `redis.asyncio` adapter, tested against `fakeredis` so the real code runs in CI without a
  live Redis instance ([ADR-008](decisions.md) pattern, applied to a cache).
- **Feature registration workflow**: `FeatureRegistrationService` — DRAFT → IN_REVIEW → ACTIVE
  → DEPRECATED → REMOVED lifecycle. `approve()` requires an explicit human reviewer, mirroring
  the Champion/Challenger human-gated promotion pattern already used for models — nothing
  reaches ACTIVE (consumable by a model) automatically. Any formula/dependency change bumps
  the version and resets to DRAFT, with the prior version snapshotted for history.
- **Feature lineage**: `FeatureLineageService` validates every dependency already exists (no
  forward references) and rejects anything that would create a cycle, direct or transitive —
  both are leakage guardrails, not just graph hygiene.
- **`FeatureStoreService`**: unified read/write facade — writes go to offline (durable) then
  online (cache) with data-quality validation (type/range) attaching `QualityFlag`s; reads
  prefer online, falling back to offline on a cache miss.
- **Feature Flags**: `FeatureFlagService` in `modules/admin/` — deterministic hash-based
  percentage rollout (no randomness — same context always gets the same answer), unknown/
  disabled flags default closed.
- Ten new FastAPI endpoints for the registration lifecycle and flag management. Feature *value*
  read/write is not yet HTTP-exposed — `FeatureStoreService` is fully built and tested, but its
  primary consumer is the Milestone 5 ingestion pipeline, not a human-facing endpoint, so that
  wiring waits until there's a real caller.
- Two new Alembic migrations: `0003_admin_feature_flags.py`, `0004_features_schema.py` — the
  former also retroactively fixed a Milestone 3 gap (the `feature_flags` table needed the same
  admin-schema migration treatment as the provider tables from [ADR log](decisions.md)).

216 backend tests passing (139 from Milestone 3 + 77 new). One real bug was caught and fixed
during test-writing: version snapshots were storing a live reference to the mutable
`FeatureDefinition`, so a later in-place edit silently rewrote "historical" snapshots after the
fact — fixed by snapshotting a copy ([ADR-013](decisions.md)).

**Feature Quality Intelligence** (2026-07-25 addendum, requested before Milestone 5 could
start): `FeatureQualityEngine` (`backend/modules/features/application/feature_quality_engine.py`)
extends the Feature Platform with automatic quality scoring, mirroring the Provider Health
Intelligence shape ([docs/feature_catalog.md](feature_catalog.md) §8 has the full breakdown):
quality/freshness/reliability/completeness scores; missing/outlier/null/invalid/duplicate/
coverage percentages; persisted `FeatureValidationReport`s with history; provider source +
reliability via a new cross-module `ProviderReliabilityPort` ([ADR-016](decisions.md));
computation cost, average duration, and memory footprint; an estimated storage size
([ADR-018](decisions.md)); consumer registration and usage-frequency tracking; and an advisory
deprecation warning. Ten new dashboard endpoints across five route groups (Quality, Validation,
Usage, Statistics, Health). New migration `0005_feature_quality_intelligence.py`. 269 backend
tests passing (216 + 53 new).

**5. Sport-Specific Ingestion & Feature Pipelines** — ✅ complete (2026-07-25), scope expanded mid-milestone
Delivered as an **Enterprise Sports Data Intelligence Platform** (scope expanded beyond the
original "live + historical ingestion" title by an explicit directive) under
`backend/modules/ingestion/` and `backend/modules/knowledge_graph/` (new bounded contexts),
plus extensions to `backend/modules/sports/`:

- **Canonical Domain Normalization / Entity Reconciliation**: `EntityReconciliationService`
  turns validated provider DTOs into persisted, versioned domain entities via a
  `provider_ref_index` O(1) lookup ([ADR-021](decisions.md)) — 11 representative entities fully
  wired end-to-end (Sport, Competition, Country, Season, Venue, Team, Player, Fixture, Match
  Statistics, Lineup, Standing). **Entity Expansion Matrix** in
  [database_schema.md](database_schema.md) §11 tracks these plus the remaining
  constitution-named entities still at "domain model only" (Rounds, Coaches, Officials, Player
  Statistics, Injuries, Suspensions, Transfers, Rankings, Match Events, Historical Results) —
  scoped down from "all ~20 entities now" after an explicit conversation about depth vs.
  breadth; the pattern for adding any of them is mechanical (new DTO + reconciler method), not
  architectural.
- **Data Versioning**: `version` + `provider_ref` columns added to every fully-wired entity
  (migration `0006_sports_versioning_and_new_entities.py`), bumped by the reconciler on every
  detected change — plus two brand-new domain entities, `Country` and `Lineup`.
- **Provider Synchronization Engine / Incremental / Live Sync**: `SyncOrchestrator` — one
  generic `_run_sync` giving every sync method distributed locking (Redis, `RedisDistributedLock`,
  [ADR-022](decisions.md)), incremental skip (`SyncCheckpoint`, never reload within the
  configured interval), retry/failure tracking, and quality-report generation. `SyncTrigger.LIVE`
  bypasses the interval check entirely — live fixtures poll every 30s.
- **Data Validation Engine**: `DataValidationEngine` — stateless, pre-persistence validation of
  every provider DTO (required fields, relationships, duplicates via batch-level ref checking,
  date/competition/season consistency, provider integrity). Invalid records are rejected, not
  persisted; a partially-invalid sync succeeds as `PARTIAL`, not `FAILED`.
- **Data Quality Engine**: `IngestionQualityEngine` — completeness/consistency/freshness/
  accuracy/validity/reliability/coverage/provider-quality/composite scores, persisted
  `DataQualityReport` history. Deliberately distinct from `FeatureQualityEngine` (Milestone 4.5)
  — raw ingested data quality vs. derived feature quality are different questions.
- **Feature Pipeline Foundation**: `FeaturePipeline` — Raw → Normalized → Validated → Clean →
  `FeatureCalculatorPort` → Feature Store, architecture only, zero registered calculators (per
  the explicit "do NOT implement sport-specific engineered features yet" instruction).
- **Knowledge Graph Population Foundation**: `KnowledgeGraphPopulationService` — write-only,
  called directly by the reconciler after each entity persists. Two new edge types beyond the
  original nine ([ADR-019](decisions.md)): `BELONGS_TO`, `LOCATED_IN`. No query/reasoning layer
  (still Milestone 9) — moved earlier than planned since the ingestion pipeline needed
  somewhere to write relationships as it went.
- **Event Timeline Engine**: `TimelineEvent` — immutable, append-only; doubles as the
  ingestion audit log rather than building a second mechanism for the same shape
  ([ADR-020](decisions.md)).
- **Redis Integration**: `RedisSyncCache` (generic get/set/delete + TTL) and
  `RedisDistributedLock`, both tested against `fakeredis` ([ADR-008](decisions.md) pattern).
- **Celery Background Processing & Scheduler**: a real `Celery` app (Redis broker + backend),
  `live`/`default` queues, a dead letter queue (a Redis list for human review, not a second
  worker queue), and a Beat schedule with a pure, tested `compute_adaptive_interval()`
  quota-aware policy function (full dynamic runtime rescheduling against live quota state is a
  documented follow-up, not built this milestone).
- **Synchronization Monitoring**: `MonitoringService` — sync status/duration/records/
  validation-failure history, Redis health (ping + latency), Celery queue length, worker health
  (via `celery_app.control.inspect()`). Provider health itself stays `HealthIntelligenceEngine`
  (Milestone 3) — exposed alongside, never reimplemented.
- Three new Alembic migrations (`0006` sports versioning/Country/Lineup, `0007` ingestion
  schema, `0008` knowledge_graph schema) and eleven new dashboard/sync-trigger FastAPI endpoints
  under `/api/v1/admin/sync/*`, `/ingestion/quality/*`, `/monitoring/*`, `/graph/nodes/*`
  ([api_specification.md](api_specification.md) §2a).
- `SportsDataProviderPort` grew from 2 to 7 methods (`fetch_countries`, `fetch_players`,
  `fetch_standings`, `fetch_team_statistics`, `fetch_lineups` added), each with a real
  httpx-based adapter implementation and a mock — two of the five new real-adapter methods are
  honestly weaker than the rest (basketball/baseball `fetch_lineups` returns `[]`, no documented
  endpoint exists to call; their `fetch_team_statistics` endpoint is a best-effort guess), see
  [architecture.md](architecture.md) §5.

**451 backend tests passing** (269 from Milestone 4 + 182 new), **95% backend test coverage**
(up from 91% before this milestone's provider-adapter test gap was closed — the real HTTP
adapters had 0% coverage despite existing since Milestone 3). Three real bugs were caught and
fixed while writing tests, each worth naming because none would have been caught by a shallower
test pass: (1) KG population calls were passing a raw `UUID` object where a `str` was expected
for `entity_ref`, crashing on SQLite (would also have been silently wrong on Postgres); (2) a
version-snapshot mutation-aliasing bug reused a live object reference instead of a copy
(same class of bug as [ADR-013](decisions.md), different module); (3) `IngestionQualityEngine`
and `SyncOrchestrator` both crashed comparing naive vs. timezone-aware datetimes when a
SQLite-backed repository stripped tzinfo on read-back — fixed with a shared `_ensure_aware()`
helper rather than routed around in tests, since a naive-datetime input is a real (if
SQLite-specific) input the engine needs to not crash on. See [ADR-023](decisions.md) for the
Standings-as-snapshots and Venue-synthetic-ref decisions.

**Deferred, honestly**: real provider credentials still aren't configured (mock-first
continues, [ADR-008](decisions.md)); Table Tennis provider still unresolved
([titaniq.md](titaniq.md) §6); Celery workers/Beat aren't running as a persistent background
service in this environment — verified via `task_always_eager` (task logic) and `fakeredis`
(Redis-backed components), the same "test the real code, fake the transport" pattern used
throughout, not a literal running worker process.

**6. Enterprise Supabase Platform & Identity** — ✅ complete (2026-07-25)
Redefined by explicit user directive from the original title ("Prediction Intelligence
Platform v1", now deferred — see note below). Replaced the "no live Supabase project"
assumption used throughout Milestones 2-5 with a real provisioned project (`titaniq`, ref
`irhnoilyaqgewfidhunx`) and built the full enterprise identity/multi-tenancy/billing/webhook
platform on top of it. Delivered under `backend/modules/identity/`, `modules/tenancy/`,
`modules/billing/`, `modules/webhooks/` — see [supabase.md](supabase.md),
[authentication.md](authentication.md), [rls.md](rls.md) for full detail:

- **Identity**: `User`/`Profile`, 8-level RBAC ladder (Guest → Super Administrator), federated
  identity linking (Google/GitHub auto-linked on OAuth login, Apple/Microsoft interface-ready),
  Personal Access Tokens, Session Intelligence (device/IP/risk tracking), Security Intelligence
  (brute-force detection below the lockout threshold so it's a distinct earlier signal, account
  lockout, append-only audit trail). Dual authentication path: Supabase JWT for production,
  bcrypt/PAT for the fast offline test suite ([ADR-025](decisions.md)).
- **Multi-tenancy**: Organizations, Teams, Memberships (owner/admin/member), Invitations
  (token-based, email-addressed).
- **Billing**: Plans, Entitlements (per-plan feature limits), Subscriptions, metered Usage
  Counters — no payment provider wired yet, state management only.
- **Webhooks**: endpoint registration (HMAC-signed via the same `CredentialVaultPort` as
  provider credentials), delivery/retry ledger — for future payment/integration providers.
- **Row Level Security**: all 62 tables across all 9 schemas RLS-enabled; real least-privilege,
  role-ladder-aware policies for identity/tenancy/billing/webhooks
  ([ADR-026](decisions.md)); analyst+ read-only for M2-M5 catalog data; zero self-access for
  security-internal tables. Full reference: [rls.md](rls.md).
- **Storage**: 7 buckets (avatars, team-logos, competition-logos, ai-reports,
  generated-charts, uploads, temporary-files) with ownership-path-convention policies.
- **Realtime**: 8 of 62 tables enabled, each tied to a named use case (Live Match Updates,
  Provider Status, Background Job Monitoring, Session Intelligence, security dashboard, webhook
  delivery status) — deliberately not every table ([ADR-028](decisions.md)).
- **Two-tier testing**: fast SQLite/fakeredis suite (540 tests) unchanged and still the default;
  a separate `tests/integration/` tier against the live project (38 tests: Database, RLS, Auth,
  Authorization, Storage, Realtime dimensions), skipped (not failed) without live credentials.
- **API**: `/api/v1/auth/*`, `/api/v1/users/*`, `/api/v1/organizations/*`,
  `/api/v1/billing/*`, `/api/v1/webhooks/*` — see [api_specification.md](api_specification.md).

**Deferred/manual** (no MCP tool exists for this): OAuth provider dashboard configuration for
Google/GitHub (code-side complete, needs the user to paste client id/secret into the Supabase
Dashboard — see [deployment.md](deployment.md) §4) and Apple/Microsoft (same, plus the
provider's own developer-account setup). Backup/DR, formal security review: Milestone 20 gate,
unchanged.

**Note on "Prediction Intelligence Platform v1"**: the original Milestone 6 content described
below is deferred to a future milestone slot — the exact number is not yet renumbered pending
explicit direction, since Milestones 7-20 as originally sequenced are otherwise unaffected.
First prediction markets designed and documented per sport
([prediction_markets.md](prediction_markets.md)), grounded in Milestone 5's real feature
availability. **Gate**: no market may depend on an entity still marked "domain model only" or
"not started" in the Entity Expansion Matrix ([database_schema.md](database_schema.md) §11)
without first promoting it to "fully wired" — that promotion is a Milestone 5-pattern extension
(new provider DTO + reconciler method), schedulable as its own short unit of work whenever a
market design actually needs one of those entities. Per-market training pipeline, candidate
algorithm evaluation, probability calibration, Champion/Challenger scaffold,
`/api/v1/predictions` and `/api/v1/markets` endpoints live for the first markets.

**7. Sports Semantic Intelligence Platform** — ✅ complete (2026-07-26)
Delivered under this exact number and title by explicit user directive ("MILESTONE 7 — SPORTS
SEMANTIC INTELLIGENCE PLATFORM: Knowledge Graph, Ontology, Context Intelligence & Graph Query
Engine"), extending Milestone 5's Knowledge Graph population into the complete semantic
intelligence layer described in [knowledge_graph.md](knowledge_graph.md) and
[ontology.md](ontology.md):

- **Sports Ontology** — every canonical `NodeType`/`EdgeType` the constitution names now exists
  (additive-only; population-only for the M5/M6 subset, ontology-only-reserved for the rest).
- **Graph Query Engine** (`GraphQueryPort`) — shortest path, neighborhood/subgraph extraction,
  relationship traversal, connected components, historical snapshot/timeline queries, influence
  queries — pure-Python BFS, bounded ([ADR-029](decisions.md)).
- **Entity Resolution** — provider mapping, alias resolution, duplicate detection, non-destructive
  canonical merge, historical identity (merge-chain resolution).
- **Similarity Engine** — framework only (Jaccard graph-structural heuristic), no ML embeddings
  yet; same adapter-swap seam as every other pluggable capability ([ADR-008](decisions.md)).
- **Semantic Search** — named retrieval APIs matching the constitution's example queries.
- **Context Engine** — one generic context builder, named wrappers per entity kind (fixture,
  match, player, team, competition, prediction, news, feature, model, explainability,
  historical comparison).
- **Temporal Graph** — relationship versioning, time-valid edges, historical snapshots/traversal,
  entity evolution (derived from edge history, not a new versioning table).
- **Graph Population extensions** — batch writes, relationship discovery (teammate inference),
  relationship deletion (hard delete, distinct from temporal close), historical replay
  (chronological reordering regardless of input order).
- **Graph Performance** — composite traversal indexes (migration 0016), a caching decorator
  reusing Milestone 5's existing generic Redis cache (no new caching concept).
- **Graph Monitoring** — node/edge counts, population/traversal timing, cache hit ratio,
  merge/duplicate counts, an explicitly-documented Entity Resolution Accuracy proxy, graph
  growth.
- **RAG Foundation** — retrieval interfaces only (`GraphRetrievalPort`); no embeddings, no
  prompt construction, no LLM call — RAG generation itself remains future scope.
- **API** — `/api/v1/graph/*`, eight route categories matching the constitution's API section
  exactly (see [api_specification.md](api_specification.md) §2b).
- **Tests** — 645 fast unit tests total (up from 569 at the start of this milestone), ≥95%
  line coverage on `modules.knowledge_graph`.

**Numbering note, not yet resolved by the user**: this milestone occupies the number "7" by
explicit directive, which now sits alongside two pre-existing roadmap entries that also expected
that neighborhood — the still-unrenumbered "Prediction Intelligence Platform v1" content
displaced from Milestone 6 (note above) and item **9, "Knowledge Graph v1"** below, whose entire
remaining scope (`GraphQueryPort`, similarity, reasoning consumers) this milestone now delivers.
Item 9 is left as-is with a forward pointer rather than silently renumbered or deleted — same
posture as the Milestone 6 note.

**7. Confidence & Explainability Engines** — ✅ delivered as part of "9. Enterprise Prediction
Intelligence Platform" below (number collision, not yet resolved, see the numbering note above)
`ConfidenceEngine` (9-factor `ConfidenceBreakdown`, plain aggregation — not a separate
`ConfidenceScorerPort`) and `ExplainabilityEngine` (composes Knowledge Graph + news/community
retrieval + Gemini's `explain()` — not SHAP) are wired into every prediction response per the
contract in [api_specification.md](api_specification.md) §3. No prediction ships without
confidence + explanation, as originally specified here.

**8. Enterprise News Intelligence & Community Intelligence Platform** — ✅ complete (2026-07-26)
Delivered under this exact number and title by explicit user directive ("MILESTONE 8 —
ENTERPRISE NEWS INTELLIGENCE & COMMUNITY INTELLIGENCE PLATFORM"), same numbering-collision
pattern as Milestone 7 above — this occupies "8" alongside the pre-existing "Frontend
Foundation" plan item below and supersedes item 13's entire scope (see that entry's note). Full
detail in [news_intelligence.md](news_intelligence.md) and
[community_intelligence.md](community_intelligence.md):

- **News Ingestion** — provider-abstracted (mock + real RSS adapter), incremental sync,
  persistent content-hash dedup, versioning, retry via consecutive-failure tracking, covering
  every source category the constitution names (official club/league/competition sites, sports
  news APIs, RSS feeds, approved publishers, press releases, federation announcements).
- **Community Intelligence** — Reddit/X/YouTube/official-fan-community ingestion with spam
  filtering, bot detection (username heuristic), in-batch + external-id duplicate filtering,
  noise reduction, and a bounded [0.3, 1.0] source-credibility score.
- **Gemini integration** — `TextIntelligenceProviderPort` extended additively (NER, relationship
  extraction, topic classification, language detection, key phrase extraction) alongside the
  Milestone 3 methods; no method on the port can produce a prediction probability.
- **Entity Extraction** — NER resolved against the Knowledge Graph via Milestone 7's
  `EntityResolutionService.find_by_alias`; unresolved mentions are surfaced, not auto-created.
- **Event Extraction** — all fourteen named event categories (transfers, injuries, recoveries,
  suspensions, manager/formation/tactical changes, training updates, weather reports, travel
  delays, stadium changes, postponements, player availability, lineup expectations), every
  event carrying confidence/source/timestamp/affected-entities/Knowledge-Graph-links.
- **Source Reliability Engine** — reliability score, historical accuracy, bias rating,
  verification status, trust level; official sources start at `OFFICIAL` trust immediately,
  demoted only by a genuinely poor track record; EWMA updates from observed outcomes.
- **Sentiment Engine** — positive/negative/neutral/mixed (mixed derived from per-sentence
  disagreement), momentum (signed change vs. the prior reading), confidence, target entity.
- **News Impact Engine** — eight named factors (injury severity, transfer importance, manager
  influence, player importance, competition importance, timing, historical impact, community
  momentum), each a real deterministic heuristic; composite impact score, confidence, affected
  teams/players/competitions.
- **Summarization** — all seven named kinds (short, executive, AI match briefing, timeline,
  player, team, competition); timeline assembled deterministically rather than through the LLM.
- **Knowledge Graph enrichment** — nodes/edges/relationships/temporal events/aliases created
  using Milestone 5/7's existing Graph APIs only; edges created only for unambiguous event types
  (transfer → `PLAYS_FOR` via `TemporalGraphService.supersede_edge`, manager change →
  `COACHED_BY`).
- **Feature Store enrichment** — ten generic (`sport_code="generic"`, `CONTEXTUAL` category)
  features registered through the real Milestone 4 approval workflow; no sport-specific
  engineered features computed, per the constitution's explicit scope line.
- **RAG Foundation extension** — retrieval interfaces for News/Community/AI-Reports added
  alongside Milestone 7's Knowledge Graph retrieval, fanned out by one facade; no embeddings, no
  LLM prompting layer.
- **Monitoring** — ingestion rate, article count, duplicate rate, extraction accuracy (proxy),
  processing time, Gemini usage, provider health (derived from sync-run history), source
  reliability, community activity.
- **API** — `/api/v1/intelligence/*`, nine route categories matching the constitution's API
  section exactly (see [api_specification.md](api_specification.md) §2c).
- **Tests** — 853 fast unit tests total (up from 811 at the start of this milestone), 98% line
  coverage on `modules.intelligence`.

**8. Frontend Foundation & Design System** (number collision with the completed milestone
above — not yet resolved, same numbering note as "7. Confidence & Explainability Engines")
Design tokens, component library, global navigation/command palette, prediction cards, match
intelligence pages, dashboards shell, dark/light mode, accessibility baseline (WCAG 2.1 AA),
PWA setup. First end-to-end user-facing flow: browse fixtures → view a real, explainable
prediction.

**9. Knowledge Graph v1** (this number is now triple-occupied — see "9. Enterprise Prediction
Intelligence Platform" below, not yet resolved)
~~`kg_nodes`/`kg_edges` write path from ingestion~~ — ✅ done, Milestone 5 (moved earlier than
planned, see that entry). ~~`GraphQueryPort` read/traversal API, similarity computation~~ — ✅
done, delivered as part of "7. Sports Semantic Intelligence Platform" above (number collision,
not yet resolved). ~~Explainability Engine actually consuming this platform~~ — ✅ done,
Milestone 9's `ExplainabilityEngine` composes Knowledge Graph retrieval directly (see below).
Remaining scope, now genuinely future: Recommendation Engine consuming this platform once that
subsystem exists.

**9. Enterprise Prediction Intelligence Platform** — ✅ complete (2026-07-26)
Delivered under this exact number and title by explicit user directive, occupying "9" alongside
the pre-existing "Knowledge Graph v1" plan item above (number collision, not yet resolved — same
posture as Milestones 7/8's collisions). Full detail in
[prediction_engine.md](prediction_engine.md) and [prediction_markets.md](prediction_markets.md):

- **Data-driven Market Registry** — `MarketDefinition` rows keyed by an 8-value `MarketKind`
  taxonomy, not one class per named market ([ADR-043](decisions.md)); full lifecycle
  (Draft → Review → Approved → Production → Deprecated → Archived → Removed) via
  `MarketRegistryService`, refusing promotion to Production with zero required features mapped.
- **Feature-to-Market Registry** — `FeatureMarketMapping` rows enforce "no model may consume
  features outside its registered mapping" (`FeatureMarketMappingService.resolve_feature_snapshot`).
- **Model Registry** — Champion/Challenger lifecycle (`ModelRegistryService`), exactly one
  CHAMPION per market, `rollback()` reinstating the most-recently-retired model.
- **Prediction Engine** — full pipeline (Feature Store → Feature/Market Selection → Market
  Feature Retrieval → Prediction Model → Probability Calibration → Confidence → Explainability),
  `PredictionEngine.generate()` pure with respect to persistence.
- **Generic Predictors** — two real, deterministic weighted linear/logistic `PredictorPort`
  implementations, honestly scoped as v1 (no ML framework, no fabricated black-box —
  [ADR-044](decisions.md)), keyed by `MarketKind` not by named market.
- **Probability Calibration** — `PlattScalingCalibrator`, pure-Python gradient-descent logistic
  regression fitted from `PredictionOutcome` history; identity mapping before any history exists.
- **Confidence Engine** — the full 9-factor `ConfidenceBreakdown` the constitution names, with
  asymmetric "no data yet" defaults matching what each factor's absence actually means
  ([ADR-045](decisions.md)).
- **Explainability Engine** — Top Positive/Negative Features, Feature Importance (real ranking
  work), Knowledge Graph Evidence + News/Community Contribution (one call to Milestone 8's
  retrieval facade), AI Explanation (Gemini's `explain()`, never the source of the probability).
- **Prediction Cache/Versioning/Audit** — TTL-cached reuse, supersede-on-republish versioning,
  confidence-threshold-gated auto-publish vs. DRAFT ([ADR-047](decisions.md)), a
  `PredictionAudit` row for every generation/approval/rejection.
- **Feature engineering** — single-record calculators via Milestone 5's `FeaturePipeline`
  (`ImpliedProbabilityCalculator`, `OddsOverroundCalculator`, `HoursUntilKickoffCalculator`,
  `AttendanceRatioCalculator`) plus one windowed team-form feature per sport
  (`RollingTeamStatAverageCalculator`, reading each sport's own declared stat schema —
  [ADR-046](decisions.md)).
- **Per-sport market seeding** — Football, Basketball, Baseball, Table Tennis each get a
  representative (not literally exhaustive) market set covering every relevant `MarketKind`,
  each promoted to Production with real features behind it ([ADR-048](decisions.md)).
- **API** — `/api/v1/predictions/*`, `/api/v1/markets/*`, `/api/v1/admin/predictions/*` — see
  [api_specification.md](api_specification.md) §2d.
- **Admin Control Center extension** — Market Health/Confidence/Accuracy/Prediction-Drift
  dashboards, Alerts (missing champion, below-threshold confidence), Export, and the
  Recompute/Rollback Admin Actions ([admin_center.md](admin_center.md)).
- **Realtime** — `predictions`, `prediction_markets`, `prediction_audits` added to the Supabase
  realtime publication, plus `features.feature_values_offline` (a "Feature Updates" gap left open since
  Milestone 6, closed here).
- **Tests** — 1,079 fast unit tests total, 98% line coverage on `modules.predictions` +
  `modules.ingestion.infrastructure.feature_calculators`.

**9.1. RLS closure for `predictions` and `intelligence`** — ✅ complete (2026-07-26)
The Supabase security advisor correctly flagged all 8 new `predictions.*` tables as RLS-disabled
right after migration 0018 went live; checking `intelligence.*` while investigating found the
identical gap had existed, undetected, since Milestone 8. Root cause both times: migration 0012
(ADR-027) granted schema/table access to `anon`/`authenticated` for the schemas that existed when
it ran — neither `intelligence` nor `predictions` existed yet. Closed with three migrations
(0020 grants, 0021 predictions RLS, 0022 intelligence RLS), tiered by what each table actually is
rather than a blanket analyst+-only stance: `predictions`/`prediction_markets` and the 7
intelligence tables `intelligence_router.py` genuinely serves to any logged-in user are free+;
registry/operational tables are analyst+; `prediction_audits` is administrator+ only (mirrors
`identity.audit_log_entries`). Verified live: zero RLS-disabled advisor findings for either
schema, 12/12 hand-verified role-impersonation checks passed, `tests/integration/test_rls.py`
extended with 18 new automated checks (41 total). Full detail in [rls.md](rls.md) §6a/§6b and
[decisions.md](decisions.md) ADR-049.

**9.1. Enterprise Machine Learning Platform** — ✅ complete (2026-07-26)
Delivered under this exact number and title by explicit user directive, occupying "9.1" alongside
the pre-existing "9.1. RLS closure" entry immediately above (number collision — the user's own
spec used "9.1" for both; same posture as every other collision in this roadmap, not resolved by
renumbering). Real, framework-native ML models now sit behind the exact same `PredictorPort` the
weighted predictors already implement — "Prediction Engine interfaces must NEVER change. Only
the predictor implementations may change," honored throughout. Full detail in
[machine_learning.md](machine_learning.md), [training_pipeline.md](training_pipeline.md),
[model_registry.md](model_registry.md), [experiments.md](experiments.md),
[calibration.md](calibration.md):

- **Framework adapters** — real LightGBM/XGBoost/CatBoost adapters plus one parametrized
  `SklearnAdapter` covering 8 more algorithms (Random Forest, Extra Trees, Logistic Regression,
  Ridge, Elastic Net, SVM, Gaussian NB, MLP) — 11 concrete algorithms total, all implementing the
  new `PredictionModelPort`, a lower-level seam beneath `PredictorPort` ([ADR-051](decisions.md)).
  `PredictorRegistry` gained market-key resolution alongside its existing `MarketKind` resolution
  ([ADR-050](decisions.md)), since a specific trained champion needs its own market identity.
- **Ensemble Learning** — Soft/Hard/Weighted Voting, Stacking/Blending, Dynamic Selection, every
  ensemble itself a `PredictorPort` composing other `PredictorPort` members
  ([ADR-055](decisions.md)) — a trained model and a weighted-heuristic fallback can sit in the
  same ensemble uniformly.
- **Dataset & Training Platform** — `DatasetBuilder` sources every sample exclusively from
  `Prediction.feature_snapshot`, enforcing "no algorithm may bypass the Feature Store" by
  construction ([ADR-052](decisions.md)); approval workflow, 6 split strategies, drift detection,
  content-hash reproducibility; preprocessing (impute/outlier/feature-selection); GPU-ready via
  constructor-param passthrough; 9 validation strategies; 5 HPO strategies
  (Grid/Random/Successive-Halving/Bayesian/Optuna-generic).
- **Automatic Model Selection** — "never hardcode algorithm selection"
  ([ADR-054](decisions.md)): trains a configurable roster per market, ranks on real held-out
  metrics, registers and promotes the actual winner, records the full benchmark as an
  `Experiment` — auditable after the fact, not just true at the moment it ran.
- **Model Registry extension** — `ModelDefinition` gains 9 additive fields
  ([ADR-053](decisions.md)): `framework`, `dataset_version`, `feature_versions`,
  `training_run_ref`, `calibration_report_ref`, `feature_importance_ref`, `artifact_ref`,
  `deployment_mode`, `trained_at`. Rollback/Audit History reuse the existing `PredictionAudit`,
  not duplicated.
- **Probability Calibration** — Isotonic Regression and Temperature Scaling join Platt Scaling;
  `CalibrationReportBuilder` computes reliability curves/Expected Calibration Error/Brier score.
- **SHAP Explainability** — `SHAPExplainerService` duck-types explainer choice on the fitted
  estimator rather than checking frameworks by name ([ADR-056](decisions.md)): global/local
  importance, SHAP values, interaction values (tree models), an honestly-reinterpreted decision
  path for ensembles, a real bounded counterfactual search, dependence plots.
  `ExplainabilityEngine.explain_with_shap()` composes the existing `explain()` unchanged.
- **Model Monitoring & Serving** — `ModelMonitoringService` extends `PredictionAdminService`
  with latency/volume/concept-drift/confidence-drift/model-health, reusing probability-drift and
  feature-drift where they already exist. Model Loader/Cache, Version Resolver, Batch/Async
  Prediction Queue (the queue singleton never holds a database session itself,
  [ADR-057](decisions.md)). ONNX export stays interface-only, matching the spec's own
  forward-looking framing.
- **API** — `/api/v1/admin/ml/*` — training/experiment/registry/champion/feature-importance/
  calibration/benchmark/monitoring/retraining/evaluation ([api_specification.md](api_specification.md) §2e).
  `prediction_admin_router.py` (Milestone 9) untouched.
- **Admin Control Center extension** — 9 named dashboards (Training/Model/Champion/Experiment/
  Calibration/Feature-Importance/Drift/Model-Monitoring/Retraining), all backed by real endpoints
  ([admin_center.md](admin_center.md) §3b).
- **Database** — migration `0023` adds 7 tables (`datasets`, `training_runs`,
  `calibration_reports`, `feature_importance_reports`, `latency_samples`, `retraining_jobs`,
  `model_artifacts`) + 9 additive `models` columns; RLS migration `0024` (analyst+, matching the
  Model Registry tier) — ✅ applied to the live Supabase project 2026-07-26 (post-STOP-GATE
  activation task), security advisor clean, role-impersonation hand-verified, one real gap found
  and fixed (`training_runs.dataset_id` missing a covering index) ([rls.md](rls.md) §6c).
- **Tests** — 1,334 fast unit tests total (up from 1,079 at the start of this milestone), 97%
  line coverage across every new ML module.

**10. Enterprise Frontend Platform** — ✅ complete (2026-07-27)
Delivered under this exact number and title by explicit user directive — a number collision with
the pre-existing "10. Analytics Engine & Dashboards" entry immediately below (same posture as
every other collision in this roadmap: noted, not resolved by renumbering). React 19 + TypeScript
+ Vite frontend ([frontend_architecture.md](frontend_architecture.md),
[design_system.md](design_system.md), [ui_components.md](ui_components.md),
[user_flows.md](user_flows.md)) — a strict presentation layer over the Milestone 1-9.1 backend,
plus the two backend additions the mandatory backend audit showed were genuinely missing:

- **Backend audit + two additive fixes** — cataloged every router/DTO/realtime table/RBAC gate
  before writing any frontend code. Closed a real security gap (~41 endpoints in
  `apps/api/main.py` had no auth dependency at all — now `require_role(Role.ADMINISTRATOR)`,
  user-approved) and two missing-endpoint gaps (`sports_router.py`, 12 endpoints — nothing
  before this exposed competitions/teams/players/fixtures for reading; one news-article-by-id
  lookup). CORS middleware added (required for any browser origin, not an API contract change).
  ([api_specification.md](api_specification.md) §2f, [security.md](security.md) §8.)
- **Design system + component library** — tokens as CSS variables mapped into Tailwind v4's
  `@theme` (repaint-on-theme-change, no re-render); ~25 Radix-based foundational primitives +
  12 domain composites (PredictionCard with full confidence/SHAP/explanation breakdown,
  MatchCard/TeamCard/PlayerCard/CompetitionCard, ModelCard/ExperimentCard, a deterministic-layout
  Knowledge Graph viewer, a virtualized table, Timeline/Stepper).
- **Auth + Realtime** — Supabase Auth directly from the browser (email/password, magic link,
  Google/GitHub OAuth, password reset) matching the documented production auth path; RBAC-aware
  nav/routes; Realtime subscriptions on all 12 published tables driving TanStack Query cache
  invalidation.
- **Every named Center built**: Dashboard, Prediction Center (+ detail), Match/Competition/Team/
  Player Centers (+ details), News/Community Centers, Knowledge Graph Explorer (browse-by-type —
  no free-text KG search exists anywhere in the backend to wire to), Analytics Center,
  Model/Experiment/Feature Centers (administrator+, read + limited actions), Admin Center
  (administrator+, read + Feature Flag toggling — full mutating admin workflows are a follow-up),
  Organization/User Settings, Billing, Notifications (a live Realtime-driven activity feed, since
  no backend notifications entity exists), Help Center.
- **PWA + performance** — installable manifest, service worker (precached app shell, deliberately
  no offline caching of API responses — RBAC-sensitive, per-user, and continuously changing data
  should never risk serving stale/leaked state from a shared device's cache), per-route code
  splitting via `React.lazy`.
- **Tests** — 68 frontend tests (component/store/route/automated-axe-a11y) + 6 Playwright e2e
  tests, all passing; ~16% whole-codebase line coverage — far short of the 95% target for a
  ~90-file frontend built from scratch in one milestone, reported honestly rather than inflated.
  Backend: 1,357 fast unit tests (up from 1,334), zero regressions.
- **Known limitations** (see [frontend_architecture.md](frontend_architecture.md) §7 for full
  detail): no free-text/fuzzy search anywhere in the Knowledge Graph module; no "list my
  organizations" endpoint (Organization Settings remembers the active org client-side instead);
  no certified Lighthouse scores (no Lighthouse runner available in this session's tooling — real
  in-browser verification was done instead: console-error-free rendering, RBAC-filtered nav,
  mobile drawer nav, dark/light theme, live signup/login against the real Supabase project);
  mutating ML/Admin workflows (dataset build, champion promotion, model rollback) have a typed
  API client but no UI action forms yet.

**10. Analytics Engine & Dashboards**
Team/player/competition/season/venue analytics, power rankings, comparative analysis,
CQRS-style read-models for dashboard queries, executive-style analytics UI. (Milestone 9's
Prediction Statistics/Comparison endpoints and Admin confidence/accuracy/drift dashboards are a
prediction-scoped slice of this; Milestone 10's Analytics Center frontend surfaces exactly these
existing aggregate endpoints — full cross-entity analytics with new backend read-models remains
future scope.)

**11. Outcome Learning Engine & Drift Detection**
~~Prediction-vs-outcome comparison, historical-accuracy tracking~~ — ✅ partially done, Milestone 9:
`PredictionOutcome` persistence, `historical_accuracy` computation (Confidence Engine + Admin
Accuracy Dashboard), and `prediction_drift()` (recent-vs-prior probability-mean comparison) all
exist and are real. Remaining, genuinely future: the `MatchCompleted` event trigger itself (no
event bus wired to auto-record outcomes yet — `PredictionOutcome` rows are written manually/by a
future job), feature-level (not just prediction-level) drift detection, and human-gated
retraining recommendations.

**12. AutoML Platform & Model Registry Maturity**
~~Model Registry, Champion/Challenger, rollback tooling~~ — ✅ done, Milestone 9:
`ModelRegistryService` (CANDIDATE → CHALLENGER → CHAMPION → RETIRED, single-champion-per-market
invariant, `rollback()`), plus the `Experiment` entity/repository Champion-vs-Candidate
benchmarks are meant to be recorded in. Remaining, genuinely future: automated feature selection,
hyperparameter optimization, and an automated evaluation-report pipeline that actually writes
those `Experiment` rows (the repository exists; nothing populates it yet).

**13. News Intelligence & Community Intelligence**
~~Gemini-backed news extraction (injuries, transfers, suspensions, etc.), source reliability
scoring, News Impact Engine (supporting signal only). Community signal ingestion with spam/bot
filtering and sentiment analysis (supporting only, never primary evidence).~~ — ✅ this entire
scope is done, delivered as "8. Enterprise News Intelligence & Community Intelligence Platform"
above (number collision, not yet resolved). Nothing remains under this item.

**14. Recommendation Engine & Personalization**
User preference model, favorites, watchlists, personalized dashboards/news, recommendation
generation combining historical data, Knowledge Graph, and AI intelligence.

**15. Admin Control Center (full)**
All modules in [admin_center.md](admin_center.md) §1, full audit trail, feature flag UI,
configuration management, maintenance mode.

**16. Monetization: Billing, Subscriptions, Rewarded Ads**
Free/Premium/Enterprise tiers, usage counters and enforcement, Google Rewarded Ads integration,
payment processing, Google Ads policy compliance review.

**17. Natural Language Intelligence & AI Assistant**
Conversational query interface over the platform's intelligence (predictions, analytics,
explanations), grounded in the Knowledge Graph and Feature Store — no unsupported/fabricated
answers.

**18. Observability, Performance & Scalability Hardening**
Full OpenTelemetry tracing/metrics/logging coverage, load testing against the NFR targets in
[architecture.md](architecture.md) §9, caching strategy audit, horizontal scaling validation for
API/worker tiers.

**19. Security Review, Compliance & Legal Documentation**
Formal security review against [security.md](security.md) §6 threat model, Privacy Policy,
Terms of Service, Cookie Policy, Responsible AI Policy, AI Transparency Policy, Community
Guidelines, Advertising Policy, Subscription Policy, Disclaimer, Data Retention Policy. Backup
and disaster recovery drill.

**20. Production Launch Readiness & Go-Live**
Final cross-milestone regression pass, launch runbook, rollback plan, go-live.

## Open Items Carried Forward

- Table Tennis data provider still unresolved ([titaniq.md](titaniq.md) §6) — mock-only through
  Milestone 5; resolve or explicitly descope before it needs to appear in a real prediction
  market.
- Confirm which of the listed provider keys (API-Football, API-Basketball, API-Baseball,
  API-Tennis, Gemini) are actually active and their plan tiers/quotas — still open; every
  provider adapter through Milestone 5 has run mock-first ([ADR-008](decisions.md)).
- Remaining Entity Expansion Matrix entries (Rounds, Coaches, Officials, Player Statistics,
  Injuries, Suspensions, Transfers, Rankings, Match Events, Historical Results) — promote to
  "fully wired" ([database_schema.md](database_schema.md) §11) as Milestone 6+ prediction
  markets actually need them, not as a blanket prerequisite.
- Basketball/baseball real-adapter gaps: `fetch_lineups` returns `[]` (no documented provider
  endpoint), `fetch_team_statistics`'s endpoint path is a best-effort guess — both need
  verification against a live API key before production use ([architecture.md](architecture.md) §5).
- Celery workers/Beat: verified via `task_always_eager` + `fakeredis`, not as a persistently
  running background service in this environment — real deployment needs an actual
  `celery -A ... worker` + `celery -A ... beat` process pair.
- Full dynamic quota-aware Beat rescheduling (a custom `celery.beat.Scheduler` polling live
  quota state) — the policy function (`compute_adaptive_interval`) exists and is tested; wiring
  it into a live-rescheduling scheduler is a documented follow-up.
