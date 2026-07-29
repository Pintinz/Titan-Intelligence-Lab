# TitanIQ — Architecture Decision Records

Append-only log. Each ADR: context, decision, alternatives considered, consequences. Superseding
an ADR means adding a new one that references it — never editing history in place.

---

## ADR-001: Supabase as the primary data platform

**Context**: Need Postgres + Auth + Storage + Realtime + RLS with low operational overhead for
a funded but still-lean early engineering team.
**Decision**: Adopt Supabase for database, auth, storage, and realtime channels.
**Alternatives considered**: Self-hosted Postgres + Auth0/Clerk + S3 + a bespoke realtime layer
(more control, materially more ops burden for equivalent capability at current stage).
**Consequences**: Fast start, built-in RLS. Some vendor coupling for Auth/Realtime — mitigated
by keeping the `identity` and `content`/realtime access behind ports
([architecture.md](architecture.md) §3) so a future migration is a swapped adapter, not a
rewrite.

## ADR-002: Modular Monolith over Microservices at launch

**Context**: Enterprise scale is the target, but the *domain* (multi-sport, multi-market AI
platform) is already very complex; the team is still discovering module boundaries.
**Decision**: Ship as a modular monolith with hard internal boundaries designed for later
extraction (see [architecture.md](architecture.md) §1–§3).
**Alternatives considered**: Microservices from day one (rejected — network-boundary cost
compounds with still-changing domain boundaries); pure monolith with no internal boundaries
(rejected — makes eventual extraction and independent scaling impossible without a rewrite).
**Consequences**: Single deployable simplifies CI/CD and local dev now. Revisit per-module
extraction once a module has a clearly independent scaling or team-ownership need — tracked as
future ADRs, not decided in advance.

## ADR-003: Independent model per prediction market — no universal model

**Context**: Constitution mandates every prediction objective be an independent ML problem.
**Decision**: Each `prediction_markets` entry gets its own dataset, feature set, model,
calibration, and monitoring pipeline (`PredictorPort` implementation per market,
[architecture.md](architecture.md) §6).
**Alternatives considered**: A shared multi-task model per sport (rejected — couples unrelated
targets' retraining/rollback lifecycles and undermines per-market explainability and
calibration correctness).
**Consequences**: More models to register/monitor/retrain, offset by the Feature Store and
AutoML Engine sharing infrastructure across markets even though the models themselves are
independent.

## ADR-004: Redis Streams as the initial internal event bus

**Context**: Need cross-module eventing (e.g., `MatchCompleted` → Outcome Learning) without
adding a new infra dependency this early.
**Decision**: Use Redis Streams (already required for caching/Celery) as the v1 event bus,
behind an `EventPublisher`/`EventConsumer` port.
**Alternatives considered**: Kafka (more capable, materially more ops overhead than justified at
current message volume); direct synchronous cross-module calls (rejected — violates the module
boundary and couples deployment/failure domains, see [architecture.md](architecture.md) §2).
**Consequences**: Revisit if throughput/retention needs outgrow Streams — the port abstraction
makes that a swap, not a rewrite.

## ADR-005: Relational Knowledge Graph, not a dedicated graph database, for v1

**Context**: Need graph-shaped queries (relationships, similarity) without committing to a new
persistence technology before traversal patterns are known.
**Decision**: Model the graph as `kg_nodes`/`kg_edges` tables in Postgres
([database_schema.md](database_schema.md) §5), queried via recursive CTEs and application-layer
similarity computation.
**Alternatives considered**: Neo4j / dedicated graph DB (rejected for v1 — adds an operational
dependency before traversal-depth/perf requirements justify it).
**Consequences**: Tracked as an open item in [knowledge_graph.md](knowledge_graph.md) §4 to
revisit if CTE-based traversal becomes a measured bottleneck.

## ADR-006: Cursor-based pagination only, no offset pagination

**Context**: API must hold up at the scale targeted in [architecture.md](architecture.md) §9.
**Decision**: All list endpoints use cursor pagination from the first implementation.
**Alternatives considered**: Offset pagination (rejected — degrades at scale and is a breaking
change to fix later, cheaper to do correctly from Milestone 3).
**Consequences**: Slightly more client-side complexity (opaque cursors vs. page numbers),
accepted for the scalability guarantee.

## ADR-007: Dialect-generic SQLAlchemy types for repository unit tests

**Context**: Milestone 2 needed repository tests that run in CI without a live Postgres
instance, while models still target real Postgres (JSONB, native UUID) in every deployed
environment.
**Decision**: Model columns use SQLAlchemy's dialect-generic `Uuid`/`JSON` types rather than
`postgresql.UUID`/`postgresql.JSONB`. Unit tests run against an in-memory SQLite engine with
`execution_options={"schema_translate_map": {"sports": None}}` so the same `sports`-schema-
qualified models used in production compile against SQLite's single default schema.
**Alternatives considered**: Postgres-specific dialect types with tests requiring a real
Postgres/testcontainers instance (rejected for unit tests — reserved for a future integration
test tier against real Postgres, tracked as an open item for Milestone 18 hardening);
mocking the repository layer entirely (rejected — would not catch real mapping/FK errors).
**Consequences**: SQLAlchemy compiles `Uuid`→native UUID and `JSON`→JSONB on a Postgres engine
automatically, so there is no production/test schema divergence — this is a testing technique,
not a compromise on the Postgres-native column types. Revisit with a Postgres-backed
integration test tier once CI has real Postgres available (Milestone 18).

## ADR-008: Mock-first provider development, selected automatically per provider

**Context**: Milestone 3's provider configuration directive requires that no milestone be
blocked by missing production API keys, while the provider architecture itself must still be
production-ready.
**Decision**: Every provider port (`SportsDataProviderPort`, `ITableTennisProvider`,
`TextIntelligenceProviderPort`) has both a real adapter and a deterministic mock adapter.
`SportsProviderRouter` selects real vs. mock automatically and per-call: real only if the
provider is `ACTIVE` *and* has at least one usable credential; mock otherwise. Callers never
branch on this themselves.
**Alternatives considered**: A single global `DEVELOPMENT_MODE` flag switching every provider
at once (rejected — doesn't support the realistic case of some providers having keys and others
not); requiring a real key before any adapter code could be written (rejected — exactly what
the directive says not to do).
**Consequences**: Adding a real credential through the Provider Management System is enough to
flip a provider from mock to real in production with no code or deploy change. Mock data must
stay structurally identical to real adapter output (enforced by both implementing the same
`Protocol`), or callers built against the mock would break against the real adapter.

## ADR-009: Provider adapters return normalized DTOs, not domain entities

**Context**: `docs/architecture.md` §5 originally said provider adapters "return normalized
domain entities." In practice, a freshly fetched `ProviderTeamRecord` has no database identity
yet — it doesn't know its `TeamId`, and a `Fixture` needs a `SeasonId` that only exists after a
season has been reconciled in the database.
**Decision**: Adapters return sport-agnostic-in-shape but not-yet-persisted DTOs
(`ProviderTeamRecord`, `ProviderFixtureRecord`, defined in
`modules/sports/ports/provider_gateway.py`). Matching a DTO against an existing domain entity
by `ProviderRef` (or creating a new one) is the ingestion pipeline's job, landing in Milestone 5.
**Alternatives considered**: Forcing adapters to look up/create domain entities directly
(rejected — couples the provider adapter, whose only job is "talk to the external API," to
repository/reconciliation logic that belongs in an application-layer ingestion service, and
makes adapters untestable without a database).
**Consequences**: `docs/architecture.md` §5 should be read as "adapters return normalized data,
persisted into domain entities by ingestion" rather than literally returning entities. No other
part of that section changes.

## ADR-010: Fernet symmetric encryption for provider credentials

**Context**: Provider API keys must be encrypted at rest (docs/security.md §2) with a workable
local-dev and production story, without pulling in a full secrets-manager integration this
early.
**Decision**: `cryptography.fernet.Fernet` (AES-128-CBC + HMAC, authenticated encryption) keyed
by `TITANIQ_ENCRYPTION_KEY`, an env var validated at startup (fail-fast, same pattern as
`TITANIQ_DB_URL`). Decrypting with the wrong key raises rather than silently returning garbage.
**Alternatives considered**: A cloud KMS/secrets manager (deferred — real candidate once a cloud
environment exists to integrate with, likely Milestone 19 hardening; not justified for local/
early-stage development); unencrypted storage with app-layer-only access control (rejected —
directly violates docs/security.md §2).
**Consequences**: Key rotation currently means rotating `TITANIQ_ENCRYPTION_KEY` and
re-encrypting all stored credentials — acceptable at current scale, revisit if/when a KMS is
integrated.

## ADR-011: Materialized rolling health state, not full-history rescans

**Context**: The Provider Health Intelligence subsystem needs `consecutive_failures` and current
status on essentially every request-routing decision (`SportsProviderRouter`, throttling,
recovery scheduling) — recomputing that from the full `ProviderHealthCheck` history on every
read would mean an unbounded, ever-growing scan.
**Decision**: `ProviderHealthState` is one row per provider, updated incrementally inside
`record_check` (consecutive failures/successes, current status, last check/success/failure
timestamps, open incident pointer). `ProviderHealthCheck` stays append-only and is only scanned
for windowed metrics (success rate, latency percentiles, trends) where a bounded time window
keeps the query cheap.
**Alternatives considered**: Deriving status from the last N rows of `ProviderHealthCheck` on
every read (rejected — O(N) per read on a hot path, and "N" is an arbitrary tuning knob instead
of a precise incremental counter); a separate scheduled job that periodically recomputes state
(rejected — adds latency between a failure and the system noticing it, and there's no scheduler
wired in yet, see Milestone roadmap).
**Consequences**: State and history can theoretically drift if a check is written but the state
update fails/races — mitigated by doing both within the same repository call inside a service
method (`record_check`), not as two independently-triggered writes. Revisit if usage patterns
ever need per-check state instead of "latest wins."

Incident severity is a **high-water mark**: once an incident escalates from WARNING to CRITICAL
it stays CRITICAL until resolved, even if the provider partially recovers (DOWN → DEGRADED)
without fully returning to HEALTHY. This mirrors standard incident-management practice (the
incident record reflects the worst the episode got) and avoids incident severity flapping on
every single check during a noisy partial recovery.

## ADR-012: Reliability score formula — 60% success rate, 40% latency, no data means no score

**Context**: The directive asks for a single "provider reliability score" and "credential
reliability score" the future Admin UI can sort/alert on, distinct from the raw metrics
underneath it.
**Decision**: `reliability_score` = `round((0.6 * success_rate_24h + 0.4 * latency_component) *
100, 1)`, where `latency_component = clamp(1 - avg_latency_ms / 2000, 0, 1)` (2 seconds average
latency scores 0, 0ms scores 1). Returns `None` — not a fabricated default like 100 or 0 — when
there's no health-check data in the last 24h. `credential_reliability_score` is computed
independently per credential from that credential's own daily usage record's error rate, so a
bad key among several good ones on the same provider is visible rather than averaged away.
**Alternatives considered**: Weighting uptime as a third independent term (rejected — over a
fixed 24h window, "uptime" and "success rate" are the same computation; `daily_uptime`/
`monthly_uptime` are exposed as their own named dashboard metrics instead of folded into the
score, avoiding double-counting the same signal under two names); an unbounded/no-ceiling
latency penalty (rejected — a single 30-second outlier would swing the score far more than its
real-world impact warrants; clamping at a 2s ceiling keeps one bad request from dominating).
**Consequences**: The 60/40 weighting and 2000ms ceiling are tunable constructor parameters on
`HealthIntelligenceEngine`, not hardcoded — revisit the specific numbers once real provider
latency data exists to calibrate against (tracked as an open item, not a commitment to keep
these exact values).

## ADR-013: Version snapshots copy state at write time, never hold a live reference

**Context**: Caught by a failing test while building Milestone 4's feature registration
workflow, not by inspection. `FeatureRegistrationService._snapshot()` stored the
`FeatureDefinition` object handed to it directly inside `FeatureDefinitionVersionSnapshot`.
`update_formula()` snapshots the definition, *then* mutates that same object (formula, version,
status, ...) before persisting it. Because Python dataclasses are mutable and passed by
reference, the "historical" snapshot silently changed too — asserting the pre-update formula
in a test failed because the snapshot showed the *new* formula.
**Decision**: `_snapshot()` now calls `dataclasses.replace(definition)` to copy every field into
a new instance before wrapping it in a snapshot. A shallow copy is sufficient here — every field
mutated afterward (`formula`, `dependencies`, `version`, `status`, `leakage_reviewed`,
`reviewed_by`, `reviewed_at`, `rejection_reason`) is reassigned wholesale on the live object, not
mutated in place inside a nested container.
**Alternatives considered**: `copy.deepcopy` (unnecessary cost — no nested mutable state exists
to protect against); make `FeatureDefinition` frozen (rejected — the entity needs in-place
lifecycle mutation for update-in-place semantics against the repository's `upsert`, matching
every other entity in the codebase).
**Consequences**: Any future application service that snapshots a mutable domain entity for
history/audit purposes must copy it the same way — this is now the pattern to follow, not a
one-off fix. Worth a grep for other `record(...snapshot=<live object>...)` call shapes if this
pattern gets reused.

## ADR-014: Feature version history records only superseded versions

**Context**: While fixing ADR-013's bug, reconsidered whether `register()` should also write a
version-1 snapshot at creation time (it originally did).
**Decision**: `register()` does not write a version snapshot. The live `FeatureDefinition` row
*is* the current version's record; `feature_definition_versions` exists only to preserve a
version after `update_formula()` replaces it with the next one. A feature still on v1 has empty
version history — that's correct, not a gap.
**Alternatives considered**: Snapshotting at registration too, for an immutable "creation
record" (rejected — every feature would carry a redundant, always-identical v1 snapshot
alongside the live v1 row, and the two would only diverge once history actually mattered).
**Consequences**: "Version History" (docs/feature_catalog.md §1) means *prior* versions, not
every version ever. Consistent with how ADR-011 treats `ProviderHealthState` vs.
`ProviderHealthCheck` — a live/current record separate from an append-only history of what
came before it.

## ADR-015: Feature flag rollout is deterministic (hashed), never randomized

**Context**: Percentage-based rollout needs to decide, for a given context (user/request), yes
or no — and needs to keep deciding the same way for that context as long as the percentage
doesn't change.
**Decision**: `_bucket(flag_key, context_id)` hashes `f"{key}:{context_id}"` (SHA-256) and takes
`% 100`; enabled iff the bucket is below the rollout percentage. No `random()` call anywhere in
the evaluation path. A percentage-rollout flag evaluated with no `context_id` returns `False`
rather than falling back to a coin flip.
**Alternatives considered**: `random.random() < percentage/100` per call (rejected — the same
user would flip between enabled/disabled on every request, which is unusable for gating a
feature someone is actively using); a stored per-context assignment table (rejected — adds a
write path and a table for something a pure hash function gives for free, with no loss of
determinism).
**Consequences**: Rollout percentage changes immediately affect the *boundary*, not everyone
independently — moving from 50% to 60% only flips contexts whose bucket falls in [50,60), it
doesn't re-roll the original 50%. This is the expected/desirable property for gradual rollout
(previously-enabled contexts almost never flip back off as the percentage increases).

## ADR-016: Provider Reliability reaches `modules/features` through a port, not an import

**Context**: Feature Quality Intelligence needs to report "Provider Reliability" for a feature's
`source_provider_key` — a number that only `modules/admin`'s `HealthIntelligenceEngine` can
compute. `modules/features` importing `modules/admin` directly would create a bounded-context
dependency the architecture otherwise avoids (docs/architecture.md §3: modules depend on other
modules' *ports*, not their internals).
**Decision**: `modules/features/ports/provider_reliability.py` defines
`ProviderReliabilityPort` (one method: `reliability_score(provider_key, now)`).
`FeatureQualityEngine` takes it as an optional constructor dependency. The composition root
(`apps/api/composition.py`) wires the real implementation, `AdminProviderReliabilityAdapter`,
which looks up the provider by key and delegates to `HealthIntelligenceEngine.reliability_score`.
**Alternatives considered**: Direct import of `modules.admin` types into `modules.features`
(rejected — the exact cross-module coupling the port pattern in §5/§5a/§5b exists to prevent);
duplicating a lightweight reliability calculation inside `modules/features` (rejected — two
independently-drifting implementations of "how reliable is this provider" is worse than one
real one behind a port).
**Consequences**: `modules/features`' test suite never needs `modules/admin` — a
`FakeProviderReliabilityPort` is enough, and unit tests confirm the engine behaves correctly
both with and without the port wired (feature has no `source_provider_key`, port absent
entirely, or port present and returning a score).

## ADR-017: "Null %" and "Missing Value %" are the same computation today, by design constraint

**Context**: The Feature Quality Intelligence directive lists "Null %" and "Missing Value %" as
distinct metrics. `FeatureValue.value` is typed `float | int | str | bool` — there is no
explicit null/None representation in the domain model, only `QualityFlag.MISSING_IMPUTED`
attached at write time when a value had to be imputed.
**Decision**: Compute both `null_pct` and `missing_pct` from the same `MISSING_IMPUTED` flag
ratio, and say so directly in code (module docstring, inline comment) and here, rather than
inventing a fake distinction or quietly shipping a metric that doesn't mean what its name
implies.
**Alternatives considered**: Adding `None` to `FeatureValue.value`'s type and a genuine
null-write path now (rejected — no real ingestion pipeline exists yet to produce an explicit
null distinct from an imputed one; speculative modeling ahead of the actual need, against the
"no placeholder implementations" / YAGNI discipline this project follows); silently making the
two numbers different via an arbitrary heuristic (rejected — worse than admitting the
equivalence, since it would look meaningful without being so).
**Consequences**: Revisit when Milestone 5's ingestion pipeline defines what "null" actually
means for a feature value (provider returned nothing vs. provider returned an explicit null vs.
computation failed) — that's when a real distinction becomes possible.

## ADR-018: Storage Size is a JSON-size estimate, not a live Postgres measurement

**Context**: "Storage Size" needs a number now, but there is no live Postgres instance this
platform runs against yet (development is entirely SQLite-in-tests, per ADR-007), so a real
`pg_total_relation_size()` query isn't available to call.
**Decision**: `storage_size_bytes()` sums `len(json.dumps({"value": v.value})) +
ROW_OVERHEAD_BYTES` (128, a rough per-row index/timestamp/id estimate) across the requested
window's `FeatureValue` rows. Documented as an estimate everywhere it's mentioned (module
docstring, this ADR), not presented as authoritative.
**Alternatives considered**: Querying `pg_total_relation_size` for real (deferred — not
callable without a live Postgres instance; becomes the right implementation once one exists,
tracked as a follow-up, not a design rejection); omitting the metric entirely until then
(rejected — the directive asked for it, and a documented estimate is more useful than nothing,
as long as it's honest about being an estimate).
**Consequences**: Once a real Postgres environment exists, swap the estimate for a live query
inside the same method signature — callers (API, health report) don't change.

---

## ADR-019: Two new Knowledge Graph edge types added during population work

**Context**: Milestone 5's `EntityReconciliationService` needed to express two relationships
the original [knowledge_graph.md](knowledge_graph.md) §3 edge set didn't cover: a generic
"this entity belongs to that sport/competition" containment relationship, and "this team/venue
is located in this country" — the latter meaningful even though the relational schema still
stores `country` as a plain string (see ADR-023 below).
**Decision**: Add `BELONGS_TO` (Competition→Sport, Team→Sport, Player→Sport, Season→Competition)
and `LOCATED_IN` (Team/Venue→Country) to `EdgeType`, documented alongside the original nine.
**Alternatives considered**: Overloading `COMPETES_IN` or `INVOLVED_IN` for containment
(rejected — both already have a specific, different meaning; overloading would make edge-type
filtering ambiguous for the Milestone 9 query layer); waiting until Milestone 9 to add any new
edge types (rejected — population had to write *something* for these relationships now, and
guessing at the read-side API before it exists is worse than naming the edge type honestly).
**Consequences**: `EdgeType` is no longer a closed set fixed at the constitution's original
scope — future modules may add more, following the same "name what you're actually writing"
principle rather than forcing everything into nine pre-declared types.

## ADR-020: Event Timeline Engine doubles as the ingestion audit log

**Context**: The constitution asks for both an immutable "Event Timeline Engine" (fixture
created/updated, goal, card, ...) and "Audit Logging" for ingestion. Building two separate
append-only log tables with near-identical shape (timestamped, immutable, entity-scoped) would
duplicate the same mechanism for two names.
**Decision**: One `TimelineEvent` table serves both. `TimelineEventType` includes both the
match-lifecycle vocabulary (`GOAL`, `CARD`, `KICKOFF`, ...) and ingestion-lifecycle events
(`SYNC_STARTED`, `SYNC_COMPLETED`, `SYNC_FAILED`, `ENTITY_RECONCILED`) — the latter is what
"audit logging" for the reconciliation pipeline actually is: a timestamped, immutable record of
what changed and when.
**Alternatives considered**: A separate `admin.audit_log` table now (rejected — `admin_center.md`
already scopes a dedicated, richer audit trail — actor identity, permission checks — to
Milestone 15, once real user identity exists; building a second one now for ingestion alone
would be replaced or duplicated by that later); no audit trail at all until Milestone 15
(rejected — the constitution asks for it now, and the mechanism already existed for the
Timeline Engine).
**Consequences**: `TimelineEvent.actor` defaults to `"ingestion"` — Milestone 15's richer audit
log can either extend this table with real actor identity or supersede it; this ADR is not a
claim that `TimelineEvent` is the final audit log design, only that it's the honest one for
what exists today.

## ADR-021: Provider ref index for O(1) reconciliation lookup, not a JSON column scan

**Context**: `EntityReconciliationService` needs to answer "have I already persisted the entity
with external id X from provider Y" for every incoming record. Each entity's `provider_ref` is
a JSONB column (`{"api_football": "42"}`, per `docs/database_schema.md` §1's original design) —
finding a match by scanning and JSON-matching every row of a growing `teams`/`fixtures`/... table
doesn't stay fast, and isn't portable to the SQLite testing path this codebase relies on
(ADR-007).
**Decision**: A dedicated `provider_ref_index` table (`provider`, `external_id`, `entity_kind`,
`entity_id`), unique on the first three columns, gives an indexed point lookup. Every
`reconcile_*` method resolves through it before deciding create-vs-update, and records into it
after persisting.
**Alternatives considered**: A Postgres JSONB containment query (`provider_ref @> '{"api_football":
"42"}'`) with a GIN index (rejected — real but Postgres-specific, breaking the SQLite-testable
path every other repository in this codebase uses; would need a second, divergent
implementation for tests); denormalizing `external_id` into its own indexed column per provider
per entity (rejected — doesn't generalize across providers, reintroduces the "add a column per
provider" problem `provider_ref` JSONB was designed to avoid).
**Consequences**: One extra write per reconciliation (the index upsert) in exchange for O(1)
reads at any table size, and a lookup mechanism that works identically against SQLite (tests)
and Postgres (production) — no dialect-specific query.

## ADR-022: Hand-rolled Redis distributed lock, not redis-py's built-in `Lock`

**Context**: `SyncOrchestrator` needs a distributed lock so two workers never sync the same
(sport, entity_kind, scope) concurrently. `redis.asyncio`'s built-in `Redis.lock()` is the
obvious first choice — well-tested, ships with the library already in use.
**Decision**: Implement `RedisDistributedLock` directly with `SET NX EX` (acquire) and a
token-based `GET` then conditional `DELETE` (release), rather than wrapping `Redis.lock()`.
**Alternatives considered**: `Redis.lock()` (rejected after testing — its `release()` calls
`EVALSHA` against a Lua script, and `fakeredis` (this codebase's test double for every other
Redis-backed component, ADR-008) raises `unknown command 'evalsha'`; adopting it would mean
either a second, real-Redis-only test tier just for locking, or an untested lock implementation
in a codebase that otherwise tests everything). A pure in-memory lock (rejected — doesn't
coordinate across worker processes, defeating the purpose).
**Consequences**: Release is a GET-then-DELETE, not a single atomic operation — there's a
narrow race window where a lock expires (TTL), gets re-acquired by someone else, and then gets
wrongly deleted by the original holder's stale `release()` call. Documented and accepted for
this use case (mutual exclusion over second-scale sync operations against a multi-minute TTL);
would need revisiting if this lock were guarding something correctness-critical rather than
"don't do redundant work."

## ADR-023: Standings are point-in-time snapshots; Venue/Country reconciliation limitations

**Context**: Two smaller but worth-recording decisions from Milestone 5 entity reconciliation.
**Decision (Standings)**: `reconcile_standing()` always inserts a new `Standing` row per sync
call rather than updating one row in place — the sync time IS the snapshot time ("this is what
the table looked like as of this sync"), and history is preserved for free. **Decision
(Venue)**: no provider DTO in this codebase carries a distinct venue id (`ProviderTeamRecord`/
`ProviderFixtureRecord` only give a `venue_name` string), so `reconcile_venue()` keys off a
synthetic `f"venue:{name}"` ref through the same provider-ref-index mechanism as everything
else (ADR-021), rather than adding special-cased venue matching logic.
**Alternatives considered (Standings)**: One row per (season, team) updated in place (rejected
— loses history a "did this team's rank change over the season" question would need).
**Alternatives considered (Venue)**: Fuzzy name matching / geocoding to deduplicate venues with
slightly different name strings (rejected — real complexity for a problem that doesn't exist
yet; two different venues sharing an exact name string within one provider is the only failure
mode, and hasn't been observed).
**Consequences**: Standings queries need `ORDER BY snapshot_at DESC` to get "current" — no
"latest" flag exists (a reasonable Milestone 6+ addition if that query pattern turns out to be
common). Venue reconciliation would need real per-venue provider ids the moment a provider adds
them — a mechanical, non-breaking change to `reconcile_venue()`'s ref-index key.

## ADR-024: Applying Alembic migrations to live Supabase via offline SQL + MCP `execute_sql`, not a direct Alembic connection

**Context**: Milestone 6 moved from the "no live Supabase project" assumption (M2-M5) to a real
provisioned project (`titaniq`, ref `irhnoilyaqgewfidhunx`). The assistant does not have and
must never fabricate the database password (docs constitution: secrets are user-supplied via
env var, never invented) — `TITANIQ_DB_URL` with real credentials was never set in this
session. Yet migrations 0001-0014 needed to be verified against, and applied to, the real
Postgres instance.
**Decision**: Generate each migration's SQL offline (`alembic upgrade --sql` against a
dummy dialect-only URL, which only needs a valid *dialect*, not real credentials), strip the
non-SQL `INFO [alembic.runtime.migration]` log lines Alembic interleaves into that output, and
apply the resulting SQL via the Supabase MCP server's `execute_sql` tool — which authenticates
independently of the assistant knowing any database password.
**Alternatives considered**: Ask the user for the DB password up front (rejected — unnecessary
if the MCP tool can apply schema changes on its own authenticated channel; keeps the password
out of the conversation and environment entirely for this class of change). Using the MCP's
`apply_migration` tool instead of `execute_sql` (rejected — `apply_migration` records changes
in Supabase's own `supabase_migrations` schema, a second migration ledger running in parallel
with our own `sports.alembic_version`; `execute_sql` is a plain SQL executor with no side
ledger, keeping Alembic the single source of migration truth per the established convention).
**Consequences**: Supabase's own migration-history view (dashboard/`list_migrations`) shows
nothing for any of these changes — by design, since `sports.alembic_version` is authoritative.
Anyone applying a future migration this way must remember to strip the interleaved log lines
first; a raw `alembic upgrade --sql` redirect is not directly executable SQL as-is.

## ADR-025: Dual-path authentication — offline bcrypt for tests/dev, Supabase JWT for production

**Context**: `modules.identity.application.identity_service.IdentityService` has both a
password-based `register`/`authenticate` path (bcrypt-hashed, fully local) and an
`ensure_provisioned` path driven by a validated Supabase Auth JWT. Building the password path
first (before a live Supabase project existed) risked looking like FastAPI was re-implementing
credential storage that "Supabase remains infrastructure only" says belongs to Supabase Auth.
**Decision**: Keep both, explicitly scoped: `register`/`authenticate` are the offline/mock
path — same mock-first rationale as `fakeredis`/`FakeSportsProvider` elsewhere (ADR-008) — used
by the fast SQLite test suite, local dev without live Supabase, and any future non-Supabase
deployment target. `ensure_provisioned` is the real production path: Supabase Auth (GoTrue)
owns password verification/email verification/magic links/OAuth and issues the JWT; FastAPI
only validates that JWT (`SupabaseJWKSValidator`) and get-or-creates the local `identity.users`
shadow row keyed by the JWT's `sub` claim, so `identity.users.id` always equals Supabase's
`auth.users.id` — required for `auth.uid()` to line up directly with it in RLS policies
(migrations 0010-0011).
**Alternatives considered**: Delete the password path once Supabase was provisioned (rejected —
the fast test suite has no live Supabase project to talk to, and never should need one to stay
fast; removing it would force every identity test onto the slow, credentialed integration
tier). Route `/api/v1/auth/login` through Supabase Auth's REST API from FastAPI (rejected for
now — adds an outbound HTTP call and a second failure mode to a local dev/test flow that has no
real need to touch the network; revisit if a genuine non-Supabase deployment target emerges).
**Consequences**: `/api/v1/auth/login`'s response includes an `access_token` that is a Personal
Access Token, not a Supabase JWT — documented in the endpoint's own docstring so it's never
confused for the real thing by a future reader. OAuth logins (Google/GitHub) flow through
`ensure_provisioned` + `ensure_federated_identity_linked` identically to email/password logins;
there is no separate OAuth-specific FastAPI endpoint because none is needed — Supabase issues
the JWT either way, and `get_current_user` treats every JWT the same regardless of how its
subject authenticated.

## ADR-026: Role-aware RLS — one ordinal-comparison function, read broadly / write narrowly

**Context**: Migration 0010 first shipped that "RLS enabled, no policies" for tables with no
per-user ownership concept (M2-M5 backend/catalog schemas) satisfied the letter of "enable RLS
on every table" but not the spirit of "design least-privilege policies supporting the full RBAC
ladder" — Moderator/Analyst/Administrator/Super Administrator had no meaningfully different
database-level access from each other or from Free/Premium.
**Decision**: Mirror the Python `Role.level` ordinal ladder (Guest=0 ... Super Administrator=7)
in SQL as three functions — `identity.role_level(text)`, `identity.current_role_level()`
(`SECURITY DEFINER`, looks up `auth.uid()`'s row), `identity.has_role_at_least(text)` — so every
elevated-read policy picks ONE threshold role and the ordinal comparison automatically covers
every role above it. A single `identity.has_role_at_least('moderator')` policy is satisfied by
Moderator, Analyst, Administrator, and Super Administrator alike; there is no need for a
separate policy per role, and no risk of the ladder getting out of sync across dozens of
hand-written per-role policies. Every such elevation is READ-ONLY — no role, including Super
Administrator, gets a write path via RLS. All writes continue through FastAPI's service-role
connection (which bypasses RLS entirely) exclusively.
**Alternatives considered**: A `role` claim check directly in each policy (`auth.jwt() ->>
'role' = 'moderator'`) (rejected — reads the JWT's role claim, not `identity.users.role`; the
two can drift, since role changes happen via `IdentityService.change_role` against our own
table, not by re-issuing a Supabase JWT). Granting Administrator+ write access via RLS for
"emergency break-glass" edits (rejected — service_role already IS the break-glass path;
duplicating it as a second, less-audited route through RLS was assessed as pure downside for
no capability gain).
**Consequences**: Free/Rewarded/Premium get identical RLS-level access to their own data —
these are billing/entitlement tiers enforced by `modules.billing.application.billing_service`
at the application layer, not database permissions, and RLS deliberately does not try to
re-implement that distinction. Analyst+ can read the full M2-M5 catalog schema directly (e.g. a
BI tool connected with an analyst's JWT) — a deliberate, documented broadening from 0010's
original no-policy stance, made specifically to give the Analyst role something real to mean.

## ADR-027: Schema/table GRANTs are a prerequisite RLS silently depends on

**Context**: Discovered while hand-verifying migration 0011's policies against the live
project: every check failed with `permission denied for schema identity`, even though the
policies themselves were correct. Supabase auto-grants `USAGE` on `public` (and a few of its
own schemas) to `anon`/`authenticated` when a project is created, but schemas introduced by our
own Alembic migrations (identity, tenancy, billing, webhooks, sports, admin, features,
ingestion, knowledge_graph) never received that grant — Postgres checks GRANTs before RLS ever
runs, so the policies were unreachable code from those roles' perspective the entire time.
**Decision**: Migration 0012 grants broadly at the table level (`GRANT ALL ... TO anon,
authenticated`, plus matching `ALTER DEFAULT PRIVILEGES` for tables created by future
migrations) across every one of these schemas — deliberately matching Supabase's own
convention for tables created through its dashboard/API, where GRANT is coarse and RLS is the
real enforcement layer.
**Alternatives considered**: Grant only the exact privilege each existing policy needs per
table (SELECT-only here, INSERT/UPDATE/DELETE there) (rejected as unnecessarily fragile — every
new write policy added later would also need a matching GRANT remembered in lockstep, two
places to keep in sync for one security boundary that RLS already owns cleanly on its own).
**Consequences**: A table with RLS enabled but zero policies (e.g. `identity.audit_log_entries`,
every M2-M5 table before migration 0011 widened analyst+ access) remains fully inaccessible to
anon/authenticated regardless of this GRANT — the safety property this migration exists to
preserve. Any schema added by a future migration must remember to run the same GRANT/ALTER
DEFAULT PRIVILEGES pattern, or its tables will silently be as unreachable as identity/tenancy
were before 0012, even with correct RLS policies in place.

## ADR-028: Storage bucket ownership via path convention; Realtime enabled per-table by explicit use case

**Context**: Milestone 6 required both Storage buckets with "secure upload policies" and
Realtime — with an explicit instruction not to enable Realtime on every table.
**Decision (Storage)**: Every private/owner-scoped bucket (ai-reports, generated-charts,
uploads, temporary-files) and the self-service part of `avatars` uses the standard Supabase
path convention `{bucket}/{owner_id}/filename`, checked via `(storage.foldername(name))[1] =
auth.uid()::text` — the same ownership-check shape already used for database RLS, just applied
to `storage.objects`. Catalog-asset buckets with no individual owner (team-logos,
competition-logos) are public-read with administrator+-only writes, mirroring the "read
broadly, write narrowly through a role gate" shape from ADR-026.
**Decision (Realtime)**: Only 8 of 62 tables were added to the `supabase_realtime` publication,
each mapped to a concrete use case named in the Milestone 6 spec: Live Match Updates
(`sports.matches`, `sports.match_events`), Provider Status (`admin.provider_health_state`,
`admin.provider_incidents`), Background Job Monitoring (`ingestion.sync_runs`), Session
Intelligence (`identity.sessions`), a security/admin dashboard feed (`identity.security_events`),
and webhook delivery status (`webhooks.webhook_deliveries`). "Notifications" was named in the
spec but has no backing table yet, so it was deliberately left out rather than enabling
Realtime on a placeholder.
**Alternatives considered**: Enabling Realtime on every table "for future-proofing" (explicitly
rejected by the task instructions and by our own judgment — broadcast volume and client
subscription surface area should track actual product use cases, not be maximized speculatively).
**Consequences**: Realtime broadcasts still respect each subscriber's own RLS (Supabase
Realtime evaluates policies per-subscriber JWT), so enabling these 8 tables adds no new data
exposure beyond one-shot SELECT — just live push for rows a client could already read. Adding a
`notifications` table in a future milestone means also adding it to the publication in that
milestone's own migration, not retrofitting this one.

## ADR-029: Graph Query Engine is pure-Python BFS over the relational store, not recursive SQL CTEs

**Context**: Milestone 7 required a Graph Query Engine supporting shortest path, neighborhood/
subgraph extraction, relationship traversal, connected components, and historical snapshot/
timeline queries — all classic graph-database operations, but ADR-005 already committed the
Knowledge Graph to relational storage (`kg_nodes`/`kg_edges`) rather than a dedicated graph DB.
**Decision**: Implement every traversal as pure-Python BFS over
`KGEdgeRepositoryPort.list_from`/`list_to`, bounded by explicit `max_nodes`/`max_hops`/
`max_depth` parameters, rather than recursive Postgres CTEs. `GraphQueryService` composes a
small set of shared primitives (`touching_edges` — undirected combine of both directions,
`other_end`, a shared `_expand()` BFS core for neighborhood/subgraph extraction) rather than one
bespoke SQL query per operation.
**Alternatives considered**: Recursive `WITH RECURSIVE` CTEs per traversal type (rejected —
Postgres-only, meaning every operation would need a second SQLite-compatible implementation for
the fast test suite, doubling the surface area for a query pattern this milestone's traffic
scale doesn't demand); a dedicated graph database / Postgres graph extension like Apache AGE
(rejected — reopens the exact question ADR-005 already closed, with no new evidence traversal
latency is actually a problem at this scale).
**Consequences**: Every traversal runs identically against SQLite (fast tests) and Postgres
(production) with zero dialect-specific code. Traversal cost is O(edges touched), bounded by the
caller's own limits — a caller requesting an unbounded neighborhood on a densely-connected hub
node gets a `truncated=True` result, not a runaway query. Composite indexes
(`from_node_id, edge_type` / `to_node_id, edge_type`, migration 0016) keep the dominant query
pattern (`touching_edges`) fast without needing the planner to intersect single-column indexes.
Revisit only if measured traversal latency at real query volume becomes a problem — not a
speculative optimization now.

## ADR-030: Entity Resolution merge is non-destructive; canonical resolution follows a pointer chain with a cycle guard

**Context**: Milestone 7's Entity Resolution needed Conflict Resolution and Canonical Merge —
two graph nodes discovered to represent the same real-world entity (shared alias or provider
reference) need to become one, without losing either node's edges or provenance.
**Decision**: `EntityResolutionService.merge(canonical, duplicate, now)` never deletes the
duplicate node. It marks the duplicate `status="merged"` with a `merged_into` pointer (a
stringified `KGNodeId`), redirects the duplicate's edges onto the canonical node via the
existing idempotent `upsert_edge` (composed in, not reimplemented), and folds the duplicate's
aliases/provider_refs into the canonical. `resolve_canonical()` follows `merged_into` chains
(A merged into B, B later merged into C resolves to C) with an explicit `seen` set guarding
against a cycle or a dangling pointer to a missing node.
**Alternatives considered**: Hard-deleting the duplicate row (rejected — destroys the historical
record of what the duplicate used to represent, and breaks any external reference — audit logs,
provider re-sync, a future "why did these two records merge" query — still pointing at its id);
redirecting edges by mutating them in place rather than creating new canonical-side edges
(rejected — the duplicate's original edges are useful historical record exactly as they were
observed; the population service's `upsert_edge` already has well-tested idempotent-update
semantics that would need a second, subtly different mutation path just for this case).
**Consequences**: A merged node's original edges remain queryable (e.g. via `edge_history`) even
after merge — nothing about the graph's history is lost. Every consumer that holds a reference to
a since-merged node's id must call `resolve_canonical()` to get current, authoritative data;
consumers that skip this see the stale (but still valid, non-corrupted) duplicate record. A
provider-ref-index-style dedicated lookup table (mirroring `modules.ingestion`'s
`ProviderRefIndexRepository`) would make `find_by_provider_ref`/`find_by_alias` O(1) instead of
the current O(n) filter-in-Python-over-`list_by_type`; deferred until it measurably doesn't
scale, same posture as ADR-021's original scope call.

## ADR-031: Similarity Engine ships as a framework with one graph-structural heuristic adapter, no ML embeddings this milestone

**Context**: The constitution's explicit Milestone 7 scope for the Similarity Engine: "Implement
framework only. No ML embeddings yet... Support future embedding providers." Player/Team/Coach/
Venue/Competition/Historical Match/Feature/Model Similarity were all named as required kinds.
**Decision**: `SimilarityPort` (`similarity(a, b) -> float`, `most_similar(node, type, limit,
min_score) -> list[(node, score)]`) has exactly one implementation this milestone,
`GraphStructuralSimilarity` — Jaccard overlap of two nodes' immediate graph neighbors (shared
teammates, opponents, competitions). It is deterministic, explainable, and needs no training
data or external embedding service, and the same one implementation serves every `NodeType`
named in the ontology, since the metric only cares which other nodes an entity is connected to,
not what kind of entity it is.
**Alternatives considered**: A stub/no-op similarity adapter that always returns 0 (rejected —
would satisfy "framework only" too literally while providing no real value; the graph-structural
metric is real, computed, and useful today); building embedding infrastructure now "to be ready"
(explicitly rejected by the constitution's own scope line — premature given no embedding
provider is chosen yet and no consumer exists to call it).
**Consequences**: Similarity quality is bounded by graph structure alone — two players who are
statistically similar but share no graph neighbors (e.g. two strikers on different, unconnected
teams in different leagues) score 0 today. `SimilarityService.compute_and_store()` persists
scores clearing `similarity_threshold` as `SIMILAR_TO` edges, so once written they're queryable
via the ordinary Graph Query Engine without recomputing. A future embedding-backed adapter
(Gemini embeddings or similar) implements the identical `SimilarityPort` and slots in without
any consumer (`SimilarityService`, Semantic Search, Context Engine, the `/graph/similar` API
route) needing to change — the same mock-first/adapter-swap shape as every other pluggable
capability in this codebase (ADR-008).

## ADR-032: Context Engine is one generic builder with named per-entity wrappers, not a distinct implementation per entity kind

**Context**: The constitution named eleven distinct "context providers" (Fixture, Match, Player,
Team, Competition, Prediction, News, Feature, Model, Explainability, Historical Comparison) —
read literally, this could mean eleven separate context-generation implementations.
**Decision**: `ContextEngine.build_context(node_id, now, depth, max_nodes)` is the one real
implementation: a bounded neighborhood expansion (delegating to `GraphQueryService.neighborhood`)
grouped by `NodeType` into a `ContextBundle`. Every named `context_for_*` method is a thin
wrapper that only chooses a `depth`/`max_nodes` pair appropriate to that entity's typical
fan-out (e.g. `context_for_player` goes two hops deep to reach a player's team's sport;
`context_for_explainability` goes two hops for the same reason a prediction's context needs the
feature/model chain that produced it) — mirroring the Similarity Engine's "one metric, many
entity kinds" shape (ADR-031).
**Alternatives considered**: A distinct hand-written query per named context kind (rejected —
eleven near-identical implementations differing only in which edges to prioritize, with no
evidence any entity kind actually needs materially different traversal logic yet); no per-kind
methods at all, just `build_context()` called directly everywhere (rejected — the constitution
explicitly names each kind, and named methods are real, cheap, documentation-as-code for future
consumers who shouldn't need to guess the right depth/max_nodes for "a player" vs "a
competition").
**Consequences**: Adding real per-kind context logic later (e.g. Historical Comparison actually
comparing specific statistical fields, not just returning two side-by-side generic bundles) is
an additive change to one named method, not a rearchitecture. No narrative/LLM text generation
happens in this engine — turning a `ContextBundle` into prose for an AI Assistant response is
RAG Foundation/future-RAG's job (ADR-035), explicitly not this milestone's.

## ADR-033: `supersede_edge` is a distinct explicit operation from `upsert_edge`'s idempotent update; Entity Evolution is derived from edge history, not a new versioning table

**Context**: The constitution asked for Temporal Graph support: Relationship Versioning,
Time-valid Edges, Historical Snapshots, Historical Traversal, Entity Evolution. Time-valid edges
(`valid_from`/`valid_to`) and historical snapshots (`GraphQueryService.at_time`) already existed
from the ontology-metadata migration and the Graph Query Engine (ADR-029). `upsert_edge`'s own
docstring (written during that work) flagged the remaining gap: it is idempotent-in-place for an
*unchanged* relationship (a repeat sync updating weight/attributes), which is the wrong behavior
for a *genuine* relationship change (a transfer ending one team's `PLAYS_FOR` and starting
another's).
**Decision**: `TemporalGraphService.supersede_edge(old_edge, from_node, to_node, edge_type, now,
...)` explicitly closes `old_edge` (`valid_to = now`) and then calls the ordinary `upsert_edge`
for the new relationship — a single, named, intentional operation distinct from `upsert_edge`'s
implicit idempotent-update path. `entity_evolution(node_id)` derives a node's relationship
timeline (opened/closed events, chronologically sorted) from `GraphQueryService.edge_history`
rather than introducing a new per-node snapshot/versioning table.
**Alternatives considered**: Overloading `upsert_edge` itself to detect "is this actually a new
relationship" and auto-close the old one (rejected — from `upsert_edge`'s signature alone there
is no way to know whether a caller intends an update or a replacement; making the caller say so
explicitly, as `supersede_edge`, is safer and matches how the transfer/relationship-change
scenario is actually triggered by upstream code, e.g. ingestion detecting a `PLAYER_TRANSFERRED`
event); a dedicated `kg_node_versions` table snapshotting every attribute change per node
(rejected — the relational-not-event-sourced posture ADR-005/ADR-029 already committed to; edge
history already answers "how did this entity's relationships change over time" for the
node-evolution use cases named in scope, without a second storage mechanism).
**Consequences**: Callers that intend a genuine relationship transition must call
`supersede_edge` explicitly — calling plain `upsert_edge` on a changed relationship instead
silently overwrites the existing edge's `weight`/`attributes` in place rather than preserving
the old relationship as closed history, which would be a caller bug, not a service bug.
Node-level attribute-change history (as opposed to relationship-change history) genuinely isn't
tracked — if a future consumer needs "show me every value this node's `attributes.name` has
ever had," that is new scope requiring new storage, not something `entity_evolution` answers
today.

## ADR-034: Graph node caching reuses the existing generic `SyncCachePort`/Redis integration rather than a new caching abstraction

**Context**: Milestone 7's Graph Performance section asked for Caching. Milestone 5's ingestion
module had already built a generic distributed cache port (`SyncCachePort` — `get`/`set`/
`delete`, TTL-bound) with a real `RedisSyncCache` adapter tested against `fakeredis`
(docs/roadmap.md Milestone 5 "Redis Integration").
**Decision**: `CachedKGNodeRepository` decorates any `KGNodeRepositoryPort` with a read-through
cache built on the *same* `SyncCachePort` — no new cache port, no new Redis client, no new
serialization framework. `get`/`get_by_entity_ref` check the cache first and populate it on a
miss; `upsert` invalidates both key shapes for the affected node; `list_by_type` is deliberately
left uncached, since it's a bulk fan-out query rather than a single-entity lookup and caching an
unbounded, growing per-type list would need its own invalidation strategy this milestone doesn't
need yet. `hits`/`misses`/`hit_ratio` on the decorator feed Graph Monitoring's Cache Hit Ratio
metric directly.
**Alternatives considered**: A bespoke in-process LRU cache local to the Knowledge Graph module
(rejected — duplicates infrastructure that already exists, tested, and works, for no benefit;
an in-process cache also wouldn't be shared across API worker processes the way Redis is); a
new typed `KGNodeCachePort` distinct from `SyncCachePort` (rejected — `SyncCachePort` is
deliberately generic/untyped specifically so heterogeneous callers like this one can reuse it
without a new interface per caller, matching its original design intent).
**Consequences**: The Knowledge Graph module now depends on `modules.ingestion.ports.cache`
(a cross-module dependency in the same direction the composition root already wires — see
`AdminProviderReliabilityAdapter` for the established precedent of application-layer
cross-module composition). Any future consumer needing a Redis-backed cache for a different
entity type gets the same reuse option instead of another bespoke cache class.

## ADR-035: RAG Foundation ships retrieval interfaces only — no embeddings, no prompt construction, no LLM call

**Context**: The constitution was explicit: "Prepare the graph for future LLM retrieval.
Implement retrieval interfaces only. Do NOT implement RAG. Expose retrieval services for
Gemini, Future LLMs, Explainability, AI Assistant, Recommendations."
**Decision**: `GraphRetrievalPort` (`retrieve(RetrievalQuery) -> RetrievalResult`) and its one
implementation, `GraphNativeRetrieval`, turn a bounded neighborhood expansion into structured
`RetrievalDocument`s (subject/relation/related-entity/confidence/source) — data, not prose.
Nothing in the port or the adapter performs embedding generation, vector similarity search,
prompt template rendering, or any call to an LLM (including the already-integrated Gemini
adapter from Milestone 3's `modules.intelligence`).
**Alternatives considered**: Wiring retrieval results directly into a Gemini prompt as a
"preview" of the future RAG pipeline (rejected — explicitly out of scope per the constitution's
own wording, and would require product decisions about prompt format/token budget that belong
to whichever future milestone actually implements RAG); returning raw `KGNode`/`KGEdge` domain
objects instead of a dedicated `RetrievalDocument` shape (rejected — the retrieval contract
should be stable and LLM-agnostic even as internal domain entities evolve, so a future RAG
implementation depends on a purpose-built, documented shape rather than the graph's internal
representation).
**Consequences**: `GraphNativeRetrieval` is real and useful today for any consumer that wants
"structured facts about X" without generation (e.g. a debugging tool, or Explainability directly
listing contextual factors) — it is not a placeholder. A future embedding-backed retriever
(semantic/vector search over node content, rather than graph-structural neighborhood expansion)
implements the identical `GraphRetrievalPort` and slots in without any consumer changing, the
same adapter-swap seam as Similarity (ADR-031) and every other pluggable capability in this
codebase (ADR-008). Actual RAG — retrieval **plus** generation, prompt construction, and an LLM
call — remains explicitly unbuilt and is a future milestone's scope.

## ADR-036: `modules/intelligence/` is organized by layer, not by the constitution's literal capability-folder list

**Context**: Milestone 8's architecture section listed submodules as
`news/, community/, nlp/, entity_extraction/, event_extraction/, source_reliability/,
sentiment/, summarization/, impact_engine/, rag/, application/, domain/, infrastructure/,
presentation/` — reading that literally would mean ten capability-named subfolders each with
their own domain/application/ports/infrastructure split, on top of the four layer folders also
listed. Every other bounded context in this codebase (`modules.knowledge_graph`,
`modules.features`, `modules.ingestion`, `modules.identity`, ...) is organized strictly by
layer, with each named capability becoming a file/class inside those layers, not a nested
sub-package.
**Decision**: `modules/intelligence/` keeps the single `domain/`, `application/`, `ports/`,
`infrastructure/` layout every other module uses. Each of the ten named capabilities
(News/Community ingestion, Entity/Event Extraction, Source Reliability, Sentiment,
Summarization, Impact Engine, RAG) is one file/class inside those layers —
`application/news_ingestion_service.py`, `application/entity_extraction_service.py`, etc. — the
exact same pattern `modules.knowledge_graph` already used for Milestone 7's ten-ish named
capabilities (Graph Query Engine, Entity Resolution, Similarity, ...). "Presentation" is
satisfied by `apps/api/routers/intelligence_router.py`, matching every other module's routers-
live-in-apps-not-in-the-module convention — no module in this codebase has its own
`presentation/` folder.
**Alternatives considered**: Ten capability subfolders each with their own domain/application/
infrastructure split (rejected — fragments one bounded context into ten mini-modules, directly
contradicting "modules/intelligence/" being *one* Clean Architecture module and Milestone 8's
own "maintain existing module boundaries" instruction); a hybrid with capability folders one
level under `application/` only (rejected — inconsistent with every sibling module for no
functional benefit, and the file-per-capability naming already gives the same navigability).
**Consequences**: Someone looking for "the community filtering logic" finds
`application/community_ingestion_service.py`, exactly where they'd look for the equivalent in
any other module in this codebase — consistency with fourteen other files across seven modules
was weighted over matching the spec's literal folder list word-for-word. If a capability
genuinely outgrows one file (e.g. Source Reliability needs three collaborating classes), it
still lives under `application/` as multiple files, not a new nested package — same
"file-per-concern, not folder-per-concern" rule.

## ADR-037: `TextIntelligenceProviderPort` grows additively toward NLP tasks, never toward prediction

**Context**: Milestone 8 asked Gemini to additionally perform Named Entity Recognition,
Relationship Extraction, Topic Classification, Language Detection, and Key Phrase Extraction —
none of which existed on `TextIntelligenceProviderPort` since Milestone 3
(`extract_events`/`summarize`/`explain`/`interpret_sentiment`). The port's own docstring already
carries an explicit guardrail: no method may be capable of sourcing a prediction probability
from an LLM instead of a trained model.
**Decision**: Five new methods (`extract_entities`, `extract_relationships`, `classify_topics`,
`detect_language`, `extract_key_phrases`) were added to the Protocol, each returning a new
frozen-dataclass value object (`ExtractedEntity`, `ExtractedRelationship`, `KeyPhrase`) —
additive only; all four Milestone 3 methods and their signatures are unchanged. Both existing
implementations (`GeminiAdapter`, `MockGeminiAdapter`) were extended with real logic for every
new method — the real adapter via new Gemini REST prompts constrained to structured JSON output,
the mock via deterministic keyword/regex heuristics (Title-Case span detection for NER, a fixed
relation-phrase table for relationship extraction, keyword tables for topics/language) — neither
implementation gained anything resembling a numeric outcome probability.
**Alternatives considered**: A second, separate port for the new NLP capabilities (rejected —
these are the same provider, Gemini, and splitting one provider's capabilities across two ports
for no isolation benefit would only add indirection); returning raw provider JSON instead of
typed value objects (rejected — every other port in this codebase returns typed domain/value
objects, not raw provider payloads, per the Provider Adapter Pattern's normalization rule).
**Consequences**: Any future capability this port might need (e.g. "text embedding") gets the
same additive treatment and the same scrutiny — does this method, even indirectly, let a caller
extract a probability-shaped number from the LLM instead of a trained model? If yes, it doesn't
belong on this port, full stop, regardless of how useful it would otherwise be.

## ADR-038: News dedup is a persistent content-hash index; Community dedup is in-batch plus external-id, not persistent

**Context**: Milestone 8 asked for Deduplication in both News Ingestion and Community
Intelligence, but the two have different volume and value profiles — an article is a
substantial, infrequently-republished unit of content; a community post/tweet is short, high-
volume, and "the same short phrase posted many times" (e.g. "yes!!") is not a meaningful
cross-time duplicate the way a wire story republished by a second outlet is.
**Decision**: `NewsIngestionService.content_hash()` (SHA-256 of normalized title+body) is
checked against `NewsArticleRepositoryPort.get_by_content_hash` — a permanent, cross-time index;
any article, ever ingested, with matching normalized content is flagged a duplicate regardless
of when. `CommunityIngestionService.post_content_hash()` is checked only against an in-memory
set scoped to the current sync batch, plus the platform's own external post id checked against
persisted history (`CommunityPostRepositoryPort.get_by_external_id`) — there is no permanent
community content-hash table.
**Alternatives considered**: The same persistent content-hash index for both (rejected —
would require either a new indexed column on every `CommunityPost` row for a check that rarely
matters, or accepting O(n) full-table scans as the community table grows far faster than news;
the actual problem — "don't create two rows for the literal same post appearing twice in one
provider response, or re-ingest a post already seen by external id" — is already solved without
it); no duplicate filtering for community at all (rejected — the constitution explicitly names
"Duplicate filtering" for Community Intelligence).
**Consequences**: A community post reposted verbatim by a different account weeks later is not
caught as a duplicate by this pipeline — that is an accepted scope boundary, not an oversight;
revisit with a persistent index only if a real product need for cross-time community dedup
emerges (e.g. detecting coordinated repost campaigns), which is a different, larger problem than
what this milestone's spec asked for.

## ADR-039: Entity/Event Extraction resolves against the Knowledge Graph; only `KnowledgeGraphEnrichmentService` writes, and only for unambiguous event types

**Context**: Milestone 8 asked Entity Extraction to "link every extracted entity to the
Knowledge Graph" and Event Extraction to produce "Knowledge Graph links," while Knowledge Graph
Enrichment separately asked to "automatically create nodes, edges, relationships... using
existing Graph APIs only." Read together, there's a real design question: does extraction
itself write to the graph, or only prepare data for something else to write?
**Decision**: `EntityExtractionService.extract_and_link()` only *resolves* — it calls
`EntityResolutionService.find_by_alias` (Milestone 7) and returns a `ResolvedEntityMention`
with a `kg_node_id` if a match exists, `None` otherwise; it never creates a node itself.
`KnowledgeGraphEnrichmentService` (composing Milestone 5/7's `KnowledgeGraphPopulationService`/
`TemporalGraphService` — no new Knowledge Graph code) is the one place that writes:
`enrich_from_mentions()` creates a new node for an unresolved mention with a known ontology type
(and adds a discovered alias to an already-resolved node), and `enrich_from_event()` creates or
supersedes an edge **only** for `TRANSFER` (→ `PLAYS_FOR`, via `TemporalGraphService.supersede_edge`
if a prior edge exists) and `MANAGER_CHANGE` (→ `COACHED_BY`) — the two event types where the
target relationship is unambiguous from the event type alone. Every other event type (`INJURY`,
`SUSPENSION`, `WEATHER_REPORT`, ...) enriches nodes/aliases only, no edge.
**Alternatives considered**: Extraction services writing directly to the graph as they extract
(rejected — conflates "what did the text say" with "what should the graph now believe," and
makes it impossible to review/gate extraction output before it becomes graph state); inferring
an edge for every event type from its `affected_entity_refs` order (rejected — e.g. an `INJURY`
event's affected entities are the player and possibly a match/venue, but there is no single
correct edge type to infer without knowing which ref is which *and* having a target — guessing
wrong pollutes the graph with a false relationship, which is a worse outcome than no edge).
**Consequences**: A confirmed transfer or manager change is reflected in the graph automatically
end-to-end (extract → resolve → enrich); every other event type contributes evidence (the
`NewsEvent` row itself, plus any newly-discovered node/alias) without ever asserting a
relationship the source text didn't unambiguously establish. Extending edge inference to more
event types (e.g. `INJURED_IN` once a match is reliably resolved) is a small, additive change to
`enrich_from_event`'s dispatch, not a redesign.

## ADR-040: Feature Store enrichment features are generic/cross-sport, registered through the real approval workflow with a system reviewer

**Context**: Milestone 8 named ten Feature Store outputs (Injury Impact, Transfer Stability,
Manager Stability, Community Momentum, News Momentum, Squad Availability, Media Pressure,
Travel Fatigue, Weather Impact, Source Reliability) and explicitly said "Do NOT compute sport-
specific engineered features yet." Every existing `FeatureDefinition` (Milestone 4) requires a
`sport_code` and goes through a human-reviewed DRAFT → IN_REVIEW → ACTIVE lifecycle before any
model may consume it.
**Decision**: All ten features register with `sport_code="generic"` (a new convention, not
validated against `SportPluginRegistry` — `sport_code` was always a free-form string) and
`category=FeatureCategory.CONTEXTUAL`. `FeatureStoreEnrichmentService.ensure_registered()` calls
the real `FeatureRegistrationService.register()` → `submit_for_review()` → `approve()` sequence
with `owner="intelligence-platform"` acting as both submitter and a "system" reviewer, rather
than writing with `require_active=False` to bypass the ACTIVE-status gate `FeatureStoreService.write()`
already enforces.
**Alternatives considered**: Bypassing registration/review entirely via `require_active=False`
(rejected — every other feature in this codebase, without exception, goes through registration
and review before being written in production; special-casing intelligence-derived features
would be the one silent exception to a governance rule the constitution itself established in
Milestone 4); a distinct `sport_code` per sport for these generic signals (rejected — Injury
Impact for a football player and Injury Impact for a basketball player are the same *kind* of
signal computed the same way; forcing four near-identical registrations per sport for a feature
that doesn't vary by sport would be duplication with no benefit).
**Consequences**: These ten features are queryable and consumable through the exact same
`FeatureStoreService.read()` path every other feature uses — a future Prediction Intelligence
Platform model can depend on `intelligence.source_reliability` exactly as it would on any
football-specific feature, no special-casing required. `ensure_registered()` is idempotent
(checks `definitions.get()` before registering), so it's safe to call on every enrichment run
without re-registering or erroring on the second call.

## ADR-041: RAG Foundation generalizes retrieval beyond graph nodes via a new port, adapting (not replacing) Milestone 7's

**Context**: Milestone 7 shipped `GraphRetrievalPort`/`GraphNativeRetrieval` — retrieval-only,
typed to `KGNodeId`/`NodeType`, since every Milestone 7 retrieval subject was a graph node.
Milestone 8 asked to "extend the existing retrieval framework" with News, Community, and AI
Reports modalities — none of which are graph nodes (a `NewsArticle`, `CommunityPost`, or
`Summary` has no `KGNodeId`).
**Decision**: A new, more general `IntelligenceRetrievalPort` (`retrieve(query) -> result`,
keyed by a plain `subject_ref: str` rather than a typed `KGNodeId`) was added to
`modules.intelligence.ports.retrieval`, with three new implementations (`NewsRetrieval`,
`CommunityRetrieval`, `AIReportRetrieval`) and one adapter, `KnowledgeGraphRetrievalAdapter`,
that wraps Milestone 7's `GraphRetrievalPort` unchanged to serve the Knowledge Graph modality
through the same shape. `IntelligenceRetrievalService.retrieve_all()` fans out across all four
and returns the combined result — one facade, not four separate calls a future RAG consumer
would need to know about individually.
**Alternatives considered**: Widening `GraphRetrievalPort` itself to accept a `subject_ref: str`
and drop the `KGNodeId` typing (rejected — would weaken Milestone 7's port for every existing
Knowledge Graph consumer to accommodate modalities that were never in scope when that port was
designed; an adapter is a smaller, safer change than modifying a shipped, tested port);
reimplementing Knowledge Graph retrieval logic natively against the new port instead of adapting
(rejected — duplicates working, tested Milestone 7 code for no benefit, and risks the two
retrieval paths drifting apart over time).
**Consequences**: A future embedding-backed retriever for any of the four modalities implements
its respective port and slots in without touching `IntelligenceRetrievalService` or any other
modality's adapter — the same mock-first/adapter-swap seam used throughout this codebase
(ADR-008). Still true after this milestone: no vector embeddings, no LLM prompting layer, exist
anywhere in this retrieval stack — RAG generation itself remains explicitly future scope.

## ADR-042: Source Reliability trust level starts from structural fact (official/unofficial), then earns or loses trust via EWMA-updated track record

**Context**: The Source Reliability Engine needed both a static classification
(Official/Unofficial, already a plain boolean on `NewsSource`) and a dynamic `TrustLevel` that
should reflect actual behavior over time — but a brand-new official source has no track record
yet, and it felt wrong to initialize it at the same neutral trust level as an unknown blog.
**Decision**: `_classify_trust(is_official, reliability_score)` treats official-ness as
dominant unless the reliability score has cratered: `is_official and reliability_score >= 0.2`
→ `OFFICIAL`, otherwise falls through ordinary reliability-score bands (`>= 0.7` → `VERIFIED`,
`>= 0.3` → `UNVERIFIED`, else `UNRELIABLE`). `record_outcome()` updates `reliability_score`/
`historical_accuracy` via an exponentially-weighted moving average (`α = 0.2`) toward each new
observed outcome (1.0 if accurate, 0.0 if not) rather than a simple running average — recent
behavior should move the score faster than an old one, without one single stale data point
carrying more weight than the pattern of recent ones.
**Alternatives considered**: Official sources permanently pinned to `OFFICIAL` trust regardless
of track record (rejected — an official source that turns out to be repeatedly, badly wrong
should eventually lose that status; permanent pinning would make Trust Level meaningless as a
behavioral signal for that source); a simple cumulative average instead of EWMA (rejected — a
source with 100 accurate reports and then 20 consecutive bad ones should visibly degrade faster
than a cumulative average would show, since the constitution's own framing — "Historical
Accuracy" *and* a separately-evolving "Reliability Score" — implies recency should matter).
**Consequences**: `reliability_score`/`historical_accuracy` converge toward whatever the recent
outcome pattern has been, with `α = 0.2` meaning roughly the last ~5 outcomes dominate the
current score — a tunable constant, not a structural commitment; revisit the exact α if real
usage shows it reacts too fast or too slow. `TrustLevel` classification logic
(`_classify_trust`) is a pure function with no persisted state of its own, so changing the
thresholds later is a one-line, fully-reversible change with no migration required.

---

## ADR-043: Data-driven Market Registry — `MarketKind` is a small taxonomy of computational strategies, not one class per named market

**Context**: Milestone 9's spec names dozens of literal markets per sport (basketball alone
lists 26: Moneyline, Spread, Alternative Spread, Team Totals, Quarter Winners, Player Props,
Double Double, Race To Points, ...). Building one bespoke predictor/serializer/validation path
per named market would mean 80+ near-identical classes across four sports, almost all of them
differing only in which feature backs them and what the line/threshold is.
**Decision**: `MarketDefinition` is a registry row (market_key, sport_code, name, category,
`MarketKind`, target_type, thresholds, lifecycle status) — pure data. `MarketKind` is a
frozen 8-value enum (`BINARY`, `SPREAD`, `TOTAL`, `TEAM_TOTAL`, `PLAYER_PROP`, `CORRECT_SCORE`,
`RACE_TO`, `SEGMENT_WINNER`) naming the *shape* of computation a market needs. `PredictorPort`
implementations are written against a `MarketKind`, never a named market — `WeightedLogisticPredictor`
serves every classification-shaped kind, `WeightedLinearPredictor` every regression/threshold-shaped
one, so two real classes back every market this milestone registers across all four sports.
**Alternatives considered**: One `Market` subclass per named market (rejected — 80+ classes
for what is structurally 8 computation shapes, and adding market #81 would mean writing a new
class instead of inserting a registry row); a single flat `market_type` string with
if/elif branching in the predictor (rejected — loses the type-safety and IDE discoverability an
enum gives, and invites the branching logic to sprawl across services instead of staying at the
one seam `PredictorRegistry` already provides).
**Consequences**: Adding a new named market to an existing sport (or a new sport entirely) is a
registry insertion + a feature-to-market mapping, not new code, as long as its behavior fits one
of the 8 existing kinds. A genuinely new computation shape (e.g. a market needing a joint
distribution over two correlated outcomes) would need a 9th `MarketKind` and one new predictor
class — an intentional, rare extension point, not a routine one.

---

## ADR-044: Predictions never originate from an LLM — enforced by real, honestly-scoped v1 statistical predictors, not a trained black-box

**Context**: The constitution's Prediction Principles are explicit: "Predictions must never
originate from an LLM... Predictions originate only from engineered features, historical data,
feature store, knowledge graph, validated statistics, approved feature calculators." Milestone 9
also bans "mock production code." No real historical labeled-outcome dataset exists yet to train
an ML model against, which could be read as blocking real code from existing at all this
milestone.
**Decision**: "No mock production code" is read as "the code must be real, deterministic, and
complete," not "the model must be a trained neural net." `WeightedLogisticPredictor`/
`WeightedLinearPredictor` are real, production-grade, mathematically-grounded weighted
linear/logistic scoring implementations of `PredictorPort` — genuinely used to produce every
prediction this platform generates, with signed per-feature contributions that are the actual
basis for Explainability, not decoration. `PlattScalingCalibrator` is a real pure-Python gradient-
descent logistic regression, fitted from `PredictionOutcome` history once it exists. Both follow
the exact mock-first/adapter-swap posture already established (ADR-008): identity/neutral
behavior when no history exists yet is itself the honest v1 behavior, and a future trained model
swaps in behind `PredictorPort` without any consumer changing.
**Alternatives considered**: Deferring the entire Prediction Engine until real labeled outcome
data exists to train a model (rejected — blocks the whole milestone indefinitely on a data
dependency nothing in this codebase controls, and the constitution's own "no mock production
code" already anticipated code being real without requiring ML); a rules-engine that returns a
fixed/random probability as a placeholder (rejected — this is exactly the "mock production code"
the constitution forbids, unlike a real, if simple, statistical model).
**Consequences**: Prediction quality this milestone is bounded by the linear/logistic model's
expressive power and by whatever features are actually registered — an honest v1 ceiling,
documented rather than hidden. `PredictorPort`/`CalibratorPort` are the only two seams a future
trained model needs to implement to replace this; no other module (Confidence Engine,
Explainability Engine, API layer) changes.

---

## ADR-045: Confidence factor "no data yet" defaults are asymmetric by what kind of unknown they represent

**Context**: Three of the nine Confidence factors this milestone computes
(`historical_accuracy`, `model_reliability`, `prediction_stability`) have no meaningful value the
first time a market or model is used — there is no outcome history, no evaluation, no repeated
prediction to compare against. A single blanket default (all-zero, or all-neutral) would either
punish every brand-new market as maximally unreliable, or overstate confidence in ways that
don't reflect what's actually known.
**Decision**: Three different defaults, each matching what "no data" actually means for that
factor: `historical_accuracy`/`model_reliability` default to a neutral **0.5** (an unproven
market/model — genuinely unknown, not bad); `prediction_stability` defaults to **1.0** (a single
prior prediction, or none, cannot have *disagreed* with anything yet, so instability has no
evidence behind it — absence of repetition isn't evidence of instability). Separately,
`ConfidenceEngine.compute()`'s own no-features-resolved case defaults `feature_quality`/
`feature_freshness`/`data_completeness` to **0.0** — that case is a hard failure of the current
prediction (nothing backing it at all), not an unproven-but-plausible state, and is scored as
the worst case on purpose.
**Alternatives considered**: One uniform "no data" constant across every factor (rejected —
conflates three structurally different kinds of missing information, and would either make every
new market look artificially confident or artificially unreliable); omitting the affected
factors from the composite average entirely when unknown (rejected — `ConfidenceBreakdown` is a
fixed 9-field dataclass by explicit constitution requirement, and a variable-length average would
make the composite incomparable across predictions with different amounts of missing history).
**Consequences**: A market's displayed confidence composite is honestly lower right after launch
(no accuracy/reliability track record yet) without being artificially zeroed out by instability
that hasn't been observed. Each default is documented at its call site specifically so a future
reader doesn't assume they're interchangeable.

---

## ADR-046: Windowed feature engineering computes against each sport's own declared `TeamStatistics` schema, not an invented universal scoring field

**Context**: A natural first windowed feature is "team form" — but the four sport plugins
(`modules.sports.<sport>.plugin`) each declare their own `team_statistic_schema`, and none of
them share a common "points_for/points_against" pair: football tracks `possession_pct`/
`shots_on_target`/`corners`/`fouls` (no goals field at all), basketball tracks `points`,
baseball tracks `runs`, table tennis tracks `points_won`. Assuming a universal scoring-margin
field would mean inventing data the domain model doesn't actually declare.
**Decision**: `RollingTeamStatAverageCalculator` is one generic engine parametrized by
`stat_key` — the rolling average of *whichever* declared numeric field a sport actually tracks,
computed self-contained (no opponent join) from `TeamStatisticsRepositoryPort.list_recent_by_team()`.
Each sport's market seeder picks the real field its own plugin declares: football uses
`shots_on_target` (an attacking-form proxy, since no goals field exists), basketball/baseball/
table tennis use their own literal `points`/`runs`/`points_won`.
**Alternatives considered**: A "scoring margin vs. opponent" feature via a cross-team join
within each match (rejected for this milestone — real and buildable, but a second, larger
mechanism; deferred as a documented future enhancement against the same generic engine, not
built dishonestly with fabricated opponent data); inventing a universal `points_for`/
`points_against` convention and asking every plugin to backfill it (rejected — a scope change to
Milestone 2's already-shipped, provider-verified plugin schemas that this milestone doesn't own).
**Consequences**: Football's windowed feature is honestly "recent attacking output," not "recent
scoring form" — a real, weaker signal than the other three sports get, disclosed rather than
disguised. Adding a real scoring-margin feature later is an additive calculator against the same
framework, not a redesign.

---

## ADR-047: Prediction publication is confidence-threshold-gated, not automatic — a DRAFT prediction requires a human Approve/Reject Admin Action

**Context**: Milestone 9's System Objectives name both "Human approval" and continuous,
automatic prediction generation as goals — which sound contradictory if every single generated
prediction needed a human sign-off before anything could consume it. `MarketDefinition.confidence_threshold`
already exists as a per-market configured field with nothing reading it.
**Decision**: `PredictionCacheService._persist_new_version()` auto-publishes a freshly generated
prediction only if its `ConfidenceBreakdown.composite` meets the market's own configured
`confidence_threshold`; otherwise it persists as DRAFT — visible to the Admin Control Center,
requiring an explicit `approve`/`reject` Admin Action before publication. "Human approval" is
satisfied at the market/model lifecycle level (`MarketRegistryService`/`ModelRegistryService`'s
review gates, both already human-gated) *and*, per-prediction, for exactly the cases confident
enough to matter — a prediction confident enough to auto-publish doesn't need the same scrutiny
as one that wasn't.
**Alternatives considered**: Every prediction requires human approval before publishing
(rejected — unworkable at the volume continuous prediction generation implies, and not what any
other milestone's "human approval" gates have meant so far — they gate configuration/lifecycle
changes, not every generated data point); no gate at all, every prediction auto-publishes
(rejected — makes `confidence_threshold` a dead configuration field with no behavior, and removes
the one place a human could catch a systematically low-confidence market before it reaches
consumers).
**Consequences**: A market with a strict `confidence_threshold` will accumulate DRAFT predictions
an operator must actively review — a real operational signal (the Admin Alerts dashboard already
surfaces markets whose recent average confidence sits below their own threshold), not silent
data loss.

---

## ADR-048: Market and feature-to-market seeding per sport is representative, not the literal exhaustive market list

**Context**: The spec's per-sport market lists are large — basketball alone names 26 markets,
baseball 14, table tennis 9 — and each would need a genuinely relevant registered feature behind
it to avoid becoming exactly the "mock production code"/fabricated-market problem this milestone
explicitly forbids.
**Decision**: Each sport's `market_seeding.py` registers one market per distinct `MarketKind`
that sport's named list implies (5-7 markets per sport, not 9-26), each backed by real features:
the sport's windowed team-form calculator (ADR-046) plus real single-record odds-derived
features (`ImpliedProbabilityCalculator`/`OddsOverroundCalculator`, registered here since task
#136 built the calculators but not their Feature Registry entries). Every `MarketKind` category
relevant to that sport is covered by at least one real market; the remaining named markets in
the spec's list are additional rows the same seeding pattern can register later, not a gap in
the mechanism.
**Alternatives considered**: Registering all 80+ literally-named markets across four sports this
milestone (rejected — most would either share a required-feature set with an already-registered
market of the same `MarketKind`, adding registry rows without adding real coverage, or would need
features — player-level props, cross-team joins — this milestone doesn't build, forcing a choice
between skipping them honestly or backing them with fabricated data); registering markets with no
feature mapping at all "to be filled in later" (rejected — `MarketRegistryService.promote_to_production`
already refuses a market with zero required features, by design, so an unbacked market could
never legitimately reach PRODUCTION anyway).
**Consequences**: The Market Registry demonstrably proves the full mechanism — registration,
feature mapping, lifecycle promotion, real prediction generation — for a real, deployable subset
per sport, with the exact same seeding pattern available to register the rest as real features
for them are built.

---

## ADR-049: `predictions`/`intelligence` RLS — tiered by what a table actually is, not a blanket analyst+; ADR-027's GRANT gap recurred and is now closed for both

**Context**: Migration 0018 (predictions schema) went live and the Supabase security advisor
immediately flagged all 8 tables as RLS-disabled — a real gap, not a false positive. Checking
`intelligence` (Milestone 8) while investigating turned up the identical gap on all 11 of its
tables, pre-dating this milestone. Root cause for both: migration 0012 (ADR-027) granted
schema/table USAGE to `anon`/`authenticated` for the nine schemas that existed *at the time it
ran* — `intelligence` and `predictions` were both introduced by later migrations and never
folded back in, so even after enabling RLS, GRANTs would still block access (Postgres checks
GRANTs before RLS).
**Decision**: Migration 0020 extends 0012's exact GRANT pattern to both schemas — same
mechanism, no new one. Migrations 0021/0022 then apply RLS **tiered by what each table actually
is**, reusing only `identity.has_role_at_least` (no new SQL function): `predictions`/
`prediction_markets` and the 7 intelligence tables `intelligence_router.py` actually serves
(`news_articles`, `news_events`, `community_topics`, `sentiment_results`, `impact_scores`,
`summaries`, `source_reliability_scores`) get `free+` (any real authenticated user) — because
that's the true access level the API layer already grants them via `get_current_user`, and RLS
should mirror the API's own posture rather than invent a stricter one. Everything else
registry/operational (`models`, `feature_market_mappings`, `prediction_outcomes`,
`model_evaluations`, `experiments`, `news_sources`, `community_posts`,
`intelligence_sync_runs`/`checkpoints`) gets `analyst+`, matching the existing M2-M5
backend-catalog shape (docs/rls.md §6). `prediction_audits` gets `administrator+` specifically
— not analyst+ — because it is structurally identical to `identity.audit_log_entries` (who did
what, to what, when), which is already administrator-only for the same reason: an audit trail is
not analytics data.
**Alternatives considered**: Blanket analyst+-only for every predictions/intelligence table,
matching §6's M2-M5 shape exactly (rejected — unlike sports/features/ingestion catalog data,
predictions and most intelligence tables genuinely are product data an ordinary logged-in user
reads today via the REST API; RLS-denying that access for anyone below analyst would be *more*
restrictive than the application layer already is, which is a mismatch worth avoiding rather
than a safety margin worth keeping). A new `TO authenticated USING (true)` policy shape instead
of reusing `has_role_at_least('free')` (rejected — would introduce a second, parallel
authorization mechanism alongside the ordinal ladder every other elevated-read policy in this
codebase already uses; `free` is already the lowest real tier a genuinely authenticated user
has, so the ladder function covers "any authenticated user" without a new concept).
**Consequences**: Both schemas now have zero RLS-disabled advisor findings. Any *future*
schema-owning migration must remember the same GRANT step (ADR-027's original consequence,
restated) — this is the second time it's been missed; a lint/checklist item in the migration
authoring process (not automated here) is the honest mitigation, not a false promise that it
can't happen a third time.

---

## ADR-050: `PredictorRegistry` gains market-key resolution alongside `MarketKind` resolution — additive, not a `PredictorPort` change

**Context**: Milestone 9.1 mandates "Prediction Engine interfaces must NEVER change. Only the
predictor implementations may change." `PredictorRegistry` (Milestone 9) resolves a predictor by
`MarketKind` alone — sufficient for the weighted predictors, which carry no market-specific
fitted state (`FeatureMarketMapping.weight` supplies all per-market specificity they need). A
real trained ML model has no such escape hatch: a LightGBM champion fitted for
`football.match_result` has different tree splits than one fitted for `basketball.match_winner`,
even though both markets share `MarketKind.BINARY` — `MarketKind`-only resolution cannot serve
two distinct trained champions of the same kind.
**Decision**: Add `register_for_market(market_key, predictor)` and an optional `market_key`
parameter to `get()`, checked first before falling back to the `MarketKind` default. Exactly one
call site changes: `PredictionEngine.generate()`'s `self.predictors.get(context.market.market_kind)`
becomes `self.predictors.get(context.market.market_kind, context.market.market_key)` — every other
line of `PredictionEngine`, and `PredictorPort` itself, is untouched.
**Alternatives considered**: Adding `market_id`/`model_id` to `PredictorPort.predict()`'s
signature directly (rejected — this is the literal interface the spec says must never change, and
every existing implementation, test, and call site would need updating). Keying the registry
by `(MarketKind, model_id)` pairs supplied at registration time only, with no fallback (rejected —
would force every market to pre-register an ML predictor even when the weighted fallback is what's
actually serving, breaking the "champion resolution can silently stay on the weighted fallback
until enough data exists" posture ADR-044/052 depend on).
**Consequences**: Every existing `get(market_kind)` call and test keeps working unchanged (verified:
zero test breakage). New per-market registrations are additive and optional — a market with no
specific registration transparently falls back to its `MarketKind`'s default predictor.

## ADR-051: `PredictionModelPort` is a lower-level seam beneath `PredictorPort`, not a replacement for it

**Context**: Milestone 9.1 needs a framework-independent contract every LightGBM/XGBoost/CatBoost/
scikit-learn adapter can implement identically, but `PredictorPort` (Milestone 9) is already the
frozen "Prediction Engine interface." The two operate at different levels: `PredictorPort` knows
about `MarketKind`/`FeatureMarketMapping` weights; a trained model only knows about feature
vectors and a scalar label.
**Decision**: `PredictionModelPort` (fit/predict_one/feature_importance/serialize/deserialize/
underlying_estimator) is a new, independent port with no knowledge of markets. `TrainedModelPredictor`
is the one class that bridges the two — a `PredictorPort` implementation wrapping exactly one
fitted `PredictionModelPort` instance, converting its single-row `ModelPrediction` into the
`PredictorOutput` shape every consumer already expects. Its `feature_contributions` is an honestly
documented approximation (`feature_value * global_feature_importance`, the same "value * weight"
shape the weighted predictors already use) — not a SHAP value; real per-instance SHAP values are
layered on top by the Explainability Engine (ADR-056) without this class changing.
**Alternatives considered**: Making every framework adapter itself implement `PredictorPort`
directly (rejected — would duplicate the `MarketKind`-dispatch and mapping-weight-filtering logic
across four adapter classes instead of once in `TrainedModelPredictor`, and would couple
framework-specific code to market/mapping concepts it has no reason to know about).
**Consequences**: A fifth framework (TensorFlow/PyTorch, explicitly named as future work) only
needs a new `PredictionModelPort` implementation — `TrainedModelPredictor`, `PredictorRegistry`,
and `PredictionEngine` all stay exactly as they are.

## ADR-052: Dataset Builder sources training samples exclusively from `Prediction.feature_snapshot`; classification labels follow the existing generic "positive"/"negative" convention

**Context**: "No algorithm may bypass the Feature Store" (Milestone 9.1 spec) needs a concrete
enforcement mechanism, not just a stated rule. Separately, building a real supervised dataset
needs a ground-truth label independent of what any past model predicted (not "was the prediction
right," which is circular).
**Decision**: `DatasetBuilder` reads only `Prediction.feature_snapshot` (Milestone 9's
Feature-to-Market-Registry-filtered Feature Store resolution) paired with the matching
`PredictionOutcome`, joined via `PredictionOutcomeRepositoryPort`/`PredictionRepositoryPort` — the
only two repositories it depends on. There is no code path in `DatasetBuilder` that reads a
`FeatureValue` directly, so bypassing the Feature Store isn't just discouraged, it's structurally
impossible. For `TargetType.CLASSIFICATION` markets, `PredictionOutcome.actual_value` is expected
to literally be `"positive"`/`"negative"` — the same generic two-sided convention
`WeightedLogisticPredictor`/`TrainedModelPredictor` already produce as `PredictorOutput.value`
(ADR-044's docstring explicitly defers real-per-market-label translation to a layer that doesn't
exist yet); outcome recording follows the same convention by symmetry rather than inventing a
third one. `TargetType.REGRESSION` labels are `float(actual_value)` directly — unambiguous, no
convention needed.
**Alternatives considered**: Deriving the label from `actual_value == Prediction.value` (rejected
— that's correctness of a *specific past prediction*, not the ground-truth outcome; it would
train a new model to imitate old mistakes rather than predict reality). Inventing real per-market
label names now (e.g. `"home_win"`/`"away_win"`) (rejected — no per-sport label-translation layer
exists yet in this codebase to produce or consume them; ADR-044 already scoped that as future
work, and duplicating that scope here would contradict it).
**Consequences**: Every dataset this milestone can build is honestly limited to whatever real
`PredictionOutcome` history has accumulated — for a fresh deployment, that's zero, and
`DatasetBuilder.build()` correctly returns a `DRAFT` dataset flagged `TOO_FEW_SAMPLES`, not a
fabricated one. This is the same "honestly empty until real data exists" posture as every other
v1 capability in this codebase.

## ADR-053: Model Registry extended additively for ML provenance; Rollback/Audit History reuse `PredictionAudit`, not duplicated

**Context**: The Milestone 9.1 Model Registry spec names fields M9's `ModelDefinition` doesn't
have: Framework, Dataset Version, Feature Version, Training Run, Calibration Report, Feature
Importance, Deployment Status, Rollback History, Audit History.
**Decision**: Nine new fields added to `ModelDefinition`, all defaulting to `None`/empty
(`framework`, `dataset_version`, `feature_versions`, `training_run_ref`, `calibration_report_ref`,
`feature_importance_ref`, `artifact_ref`, `deployment_mode`, `trained_at`) — every existing
`ModelRegistryService.register()` call site keeps working with zero changes. "Rollback History"
and "Audit History" are deliberately **not** new fields: `PredictionAudit` (keyed by `model_id`,
Milestone 9) already records every registry mutation including rollbacks
(`AuditAction.ROLLED_BACK`) — adding a second history list here would just create two sources of
truth for the same facts. "Deployment Status" is `deployment_mode` (`"shadow"`/`"canary"`/
`"live"`/`None`), a new `ModelRegistryService.set_deployment_mode()` method, deliberately distinct
from the existing `ModelStatus` lifecycle (`CANDIDATE`/`CHALLENGER`/`CHAMPION`/`RETIRED`) — a
CHALLENGER can be in shadow deployment or canary rollout, which is a *how it's being exercised*
question, not a *what stage of its lifecycle* question the existing enum already answers.
**Alternatives considered**: A separate `ModelDeploymentRecord` table/entity to hold framework/
dataset-version/deployment-mode (rejected — over-engineered for nine scalar/opaque-ref fields
with no independent lifecycle of their own; they only ever exist alongside a `ModelDefinition`
row, so they belong on it, matching how `training_dataset_ref`/`calibration_ref` already work).
**Consequences**: `models` table gains 9 nullable columns (migration 0023) with zero data
migration needed for existing rows. `dataset_version`/`feature_versions` are lightweight int/dict
fields rather than foreign keys into a versioned dataset-schema table — sufficient for this
milestone's honest scope; a stricter foreign-key relationship is straightforward future work once
dataset versioning has real production traffic to validate against.

## ADR-054: Automatic Model Selection ranks a configurable candidate roster on real held-out metrics — the roster is data, not a hardcoded choice

**Context**: "Never hardcode algorithm selection" (Milestone 9.1 spec) needs to mean something
concrete and falsifiable, not just a design aspiration repeated in a docstring.
**Decision**: `AutomaticModelSelectionService.select()` takes a `candidates: tuple[CandidateSpec, ...]`
parameter (defaulting to `DEFAULT_CLASSIFICATION_CANDIDATES`/`DEFAULT_REGRESSION_CANDIDATES`, 11
and 9 entries respectively — every algorithm named in the spec except the two combinations with
no sensible form, ADR already covered by `SklearnAdapter`'s own `UnsupportedAlgorithmForTargetTypeError`).
Every candidate is trained via the identical `TrainingPipelineService.train()` path and ranked by
its own held-out test metric (`accuracy` for classification, `mae` for regression — lower/higher
comparison encoded once in `_is_better()`, not per-algorithm special-casing). The winner is
whichever candidate actually scored best on this specific market's data, not a fixed favorite.
Every run — winner, every candidate considered, every candidate skipped and why — is recorded via
`ExperimentTrackingService.record_model_selection()`, so "never hardcode" is auditable after the
fact, not just true at the moment it ran.
**Alternatives considered**: A single "best default" algorithm (e.g. always LightGBM) with other
algorithms as opt-in overrides (rejected — this is exactly the hardcoding the spec forbids, just
with extra steps). Ranking by a fixed composite score across multiple metrics (rejected — over-
engineered for this milestone's honest scope; a single, named, market-appropriate metric per
target type is simpler and just as real).
**Consequences**: Adding a 12th algorithm to either default roster is a one-line tuple edit, not a
new code path. A market's champion algorithm can differ from another market's of the same
`MarketKind`, by design (ADR-050 is what makes that servable at inference time).

## ADR-055: Ensemble Learning composes at the `PredictorPort` level, not the `PredictionModelPort` level

**Context**: Milestone 9.1 names 6 ensemble methods (soft/hard/weighted voting, stacking,
blending, dynamic). They need a common seam to combine members through.
**Decision**: Every ensemble class (`VotingEnsemblePredictor`, `StackedEnsemblePredictor`,
`DynamicEnsemblePredictor`) is itself a `PredictorPort` implementation whose members are other
`PredictorPort` instances — not `PredictionModelPort` instances. This means an ensemble member can
be a `TrainedModelPredictor` wrapping any of the four frameworks, a weighted heuristic predictor,
or even another ensemble, uniformly. "Sport-specific"/"market-specific" ensembles aren't distinct
classes — which members compose an ensemble, and for which market, is decided entirely by
composition wiring (`PredictorRegistry.register_for_market`, ADR-050); an ensemble registered for
`football.match_result` is football-specific purely because of what it was built from.
**Alternatives considered**: Building ensembles at the `PredictionModelPort` level (rejected — it
would exclude the weighted predictors from ever participating in an ensemble, and would need its
own market-kind/mapping-weight-filtering logic duplicated from `TrainedModelPredictor`).
**Consequences**: Stacking/blending's meta-model is a plain `PredictionModelPort` (any of the four
frameworks) trained on member probabilities as its own feature columns — reuses the exact same
`fit()`/`predict_one()` contract, no new training path. Mixing a real trained model with a
weighted-heuristic fallback inside one ensemble is possible without special-casing, a useful
property during the transition period ADR-052 describes (real data still accumulating).

## ADR-056: SHAP explainer selection is duck-typed on the fitted estimator, never framework-isinstance-checked; "Decision Path" is honestly reinterpreted for ensembles

**Context**: SHAP's `TreeExplainer` (fast, exact, supports interaction values) only applies to
bare tree ensembles; everything else needs the slower, model-agnostic `KernelExplainer`. Coupling
that choice to "which of the 4 frameworks produced this model" would require `SHAPExplainerService`
to import and special-case every framework's adapter class.
**Decision**: Explainer choice is duck-typed on the fitted estimator itself —
`hasattr(estimator, "feature_importances_") and not wrapped in a Pipeline` selects `TreeExplainer`;
everything else (scale-sensitive sklearn algorithms `SklearnAdapter` wraps in a `Pipeline`, plus
bare `GaussianNB`) gets `KernelExplainer` over the estimator's own `predict_proba`/`predict` —
correct for a `Pipeline` because `KernelExplainer` only ever calls it as a black-box function, so
the wrapped `StandardScaler` is transparently handled. Milestone 9.1's "Decision Paths" requirement
has no literal answer for an ensemble (there is no single tree to traverse) — `decision_path` is
honestly redefined as the top-3 SHAP-ranked features rendered as plain-language sentences, not a
fabricated single-tree traversal that doesn't exist for a forest/boosting ensemble.
Counterfactual explanation is a real, bounded greedy search (perturb the top-ranked SHAP feature(s)
toward the opposite end of the background data's own observed range, re-check the model's
prediction, repeat up to a budget) — not a static canned answer, and it honestly reports
`found=False` when the budget is exhausted without a flip, rather than fabricating one.
**Alternatives considered**: `isinstance()` checks against `lightgbm.LGBMClassifier`/
`xgboost.XGBClassifier`/`catboost.CatBoostClassifier`/etc. directly (rejected — couples
`SHAPExplainerService` to every framework's import surface, breaking exactly the framework-
independence `PredictionModelPort` (ADR-051) exists to provide). A literal single-tree decision
path computed from one arbitrarily-chosen tree in the ensemble (rejected — would misrepresent the
ensemble's actual decision process, which is a real correctness concern, not a cosmetic one).
**Consequences**: Adding a 5th framework needs no `SHAPExplainerService` changes at all, provided
its fitted estimator exposes the sklearn-conventional `predict_proba`/`feature_importances_`
surface (true for every sklearn-API-compatible framework, including the three already integrated).

## ADR-057: Model Serving's async queue singleton never holds a database session; ONNX export and distributed serving stay interface-only, matching the spec's own framing

**Context**: `AsyncPredictionQueueService`'s pending/results state must survive across separate
HTTP requests (enqueue now, poll later — possibly a different worker-process invocation in
production), so it must be a process-wide singleton. But actually running a queued prediction
needs a `PredictionCacheService`, which is built per-request from a short-lived `AsyncSession` —
holding one of those open inside a long-lived singleton is a real connection-lifecycle bug, not a
style preference. Separately, the spec explicitly frames ONNX export and distributed serving as
forward-looking ("architecture", "future") rather than a working requirement this milestone
delivers.
**Decision**: `AsyncPredictionQueueService` holds no `cache_service` field; `process_next()` takes
a freshly-built `PredictionCacheService` as a parameter every time it's called, so the queue's own
state outlives requests while the database session backing any given `process_next()` call does
not. `ModelExportPort` (`export_to_onnx`) is defined as a Protocol with no concrete adapter — the
same "interface now, concrete adapter when a real need arrives" posture as Milestone 7's RAG
foundation retrieval port.
**Alternatives considered**: Giving `AsyncPredictionQueueService` its own dedicated long-lived
`AsyncSession` at construction time (rejected — async sessions aren't designed to be held open
indefinitely across many requests; this is a resource leak and staleness risk, not a simplification).
Building a concrete ONNX exporter now via `skl2onnx`/`onnxmltools` (rejected — no production need
for cross-runtime export exists yet in this codebase, and the spec itself names this "architecture,"
not a delivered capability; installing and wiring an unused dependency would be scope creep beyond
what was asked).
**Consequences**: `process_next()`'s signature carries `cache_service` explicitly, visible at every
call site — the session-lifecycle discipline is enforced by the type signature, not just a
comment. A future Celery-task-based production queue implements the same `enqueue`/`process_next`/
`poll` shape without `PredictionEngine`/`PredictionCacheService` changing.

---

## ADR-058: Closing the `apps/api/main.py` auth gap with `require_role(ADMINISTRATOR)` uniformly, not per-endpoint judgment

**Context**: The Milestone 10 backend audit found ~41 endpoints defined directly in
`apps/api/main.py` (Provider Management, Feature Registration/Flags/Quality, Sports Ingestion
Sync, Redis/KG monitoring) with no auth dependency at all — not even `get_current_user`. These
predate the identity/RBAC system (Milestone 6) and were never retrofitted. Once a public frontend
exists, these URLs are directly reachable by anyone who finds them, bypassing RBAC entirely; the
frontend's own route guards would be cosmetic, not a real security boundary.
**Decision**: Gate every one of these routes with `require_role(Role.ADMINISTRATOR)` — the exact
mechanism already used by `prediction_admin_router.py` and `ml_platform_router.py` — rather than
picking a different threshold per endpoint category. `GET /api/v1/health` is the sole exception
(public liveness probe, no data returned). User-approved before implementation (this is backend
behavior change, and the milestone's own instructions were explicit about not touching backend
logic without a specific call-out).
**Alternatives considered**: Leaving the backend untouched and gating only in the frontend router
(rejected — the user asked, when presented with this exact tradeoff, for the real fix; a
frontend-only gate doesn't stop a direct HTTP request). Picking a lower threshold (e.g.
`Role.MODERATOR`) for read-only monitoring endpoints (rejected — every one of these already has
an `administrator`-gated equivalent posture elsewhere in the same file, e.g. sync-trigger
mutations sit right next to sync-status reads; splitting the threshold within one file by
endpoint would be an inconsistent, hard-to-audit policy for no clear benefit at current scale).
**Consequences**: 41 new `require_role(Role.ADMINISTRATOR)` dependencies (one string-replace
across identical `session: AsyncSession = Depends(get_session)` parameter signatures, since every
affected function shared that exact pattern). Four existing test files
(`test_api_health_dashboard.py`, `test_api_features_and_flags.py`, `test_api_feature_quality.py`,
`test_api_ingestion.py`) needed an admin-authenticated `TestClient` fixture instead of an
anonymous one — full backend suite stayed green (1,357/1,357) after the change.

## ADR-059: `sports_router.py` is free+ (no role floor beyond authentication), matching `predictions`/`prediction_markets`, not the analyst+ posture of the raw M2-M5 schema

**Context**: `docs/rls.md` §6 gives the sports/admin/features/ingestion/knowledge_graph schemas a
blanket analyst+ RLS policy, since M2-M5 never exposed them to ordinary users — "the API surfaces
this data through prediction/analytics endpoints, out of scope until later milestones." Milestone
10 is that later milestone: Match/Competition/Team/Player Centers need to show fixtures, standings,
rosters to any logged-in user, not just analysts.
**Decision**: `sports_router.py`'s new endpoints are `get_current_user`-gated with no role floor —
the same posture already established for `predictions`/`prediction_markets` (§6a of rls.md), since
this is now genuinely app-facing product data an ordinary user reads directly, not analyst-only
catalog/backend data. This is an API-layer decision only; the underlying `sports`/`features`/etc.
schemas' RLS policies (analyst+, migration 0010-0011) are unchanged — FastAPI's service-role
connection bypasses RLS regardless, so this doesn't create a new direct-Postgres-access exposure,
only a new authenticated-REST-read path.
**Alternatives considered**: Matching the raw schema's analyst+ RLS tier at the API layer too
(rejected — would make Match/Team/Player/Competition Centers unusable for any non-analyst user,
defeating the point of building them). Leaving these entities backend-only until a future
milestone formally revisits access tiers (rejected — the frontend milestone's whole mandate is to
expose exactly this data to app users now).
**Consequences**: `sports_router.py` follows the exact tiering precedent `predictions`/
`prediction_markets` already set, rather than inventing a third posture. Documented explicitly in
docs/api_specification.md §2f so the next person auditing RLS-vs-API-tier consistency has the
rationale, not just the code.

## ADR-060: Design tokens as CSS custom properties mapped into Tailwind v4's `@theme`, not JS-driven theme objects

**Context**: Milestone 8 fixed token *names* (`color.background.primary`, etc.) without values.
Milestone 10 needed real dark/light values and a way to flip between them without a full React
re-render on every component that reads a color (theme toggling is a common, latency-sensitive
interaction).
**Decision**: Every token lives as a CSS custom property (`frontend/src/styles/tokens.css`), with
a dark block on `:root`/`[data-theme="dark"]` and a light override on `[data-theme="light"]`.
Tailwind v4's `@theme` block (`frontend/src/index.css`) maps each property into a utility class
(`bg-bg-primary`, `text-confidence-high`, etc.) that resolves through `var(--color-bg-primary)` at
paint time. Flipping the `data-theme` attribute on `<html>` (via `useThemeStore`) repaints every
themed element instantly — no component re-renders, no JS theme-object lookup.
**Alternatives considered**: A JS theme object passed via React Context (rejected — every
consuming component would need to re-render on theme change, and Tailwind's utility classes
wouldn't compose with it without a CSS-in-JS layer this project doesn't otherwise need).
Driving dark/light off `prefers-color-scheme` media queries alone (rejected — dark is the
documented default/primary mode regardless of OS theme, docs/ui_design_system.md §3; an explicit
user toggle, persisted, must be able to override the OS preference in either direction).
**Consequences**: Adding a new token is a one-line CSS variable addition plus one `@theme` mapping
line — no React code touches color at all. The confidence scale (`color.confidence.*`) stays a
visibly distinct token family from semantic success/danger, enforced by naming, not by convention
alone.

## ADR-061: PWA service worker precaches the app shell only — no offline caching of API responses

**Context**: `vite-plugin-pwa`'s default Workbox `generateSW` strategy can runtime-cache API
responses for offline use. TitanIQ's API responses are per-user, RBAC-gated, and continuously
changing (live predictions, confidence scores, admin-only data).
**Decision**: `runtimeCaching: []` — only the built JS/CSS/HTML app shell is precached
(`globPatterns: ['**/*.{js,css,html,svg}']`); no `/api/v1/*` response is ever cached by the
service worker.
**Alternatives considered**: Caching prediction/market GET responses for offline viewing
(rejected — on a shared or borrowed device, a stale cached response from one session could
surface a previous user's data, or an administrator-only response cached during one session could
leak to a lower-privileged user opening the same installed PWA later; the staleness risk alone —
showing a resolved prediction as still pending — is also unacceptable for "live" data the product
explicitly markets as real-time).
**Consequences**: The installed PWA shell loads instantly offline (title screen, login page,
static assets); every authenticated data view still requires a live network connection, exactly
like the non-PWA browser experience. Full offline-first prediction browsing (docs/ui_design_system.md
§3's "offline support ... where feasible") is deliberately not attempted this milestone — the
security/staleness tradeoff was judged not to be "feasible" for this data shape, not merely
undone for lack of time.

## ADR-062: Landing page redesign ships as additively-scoped tokens, not a merge into the global design system

**Context**: The Milestone 10.1 "Complete Frontend Reconstruction" brief asked for a wholly new
visual identity (Bloomberg Terminal precision + Apple HIG restraint + F1 broadcast-graphics
energy) applied to "every page," starting with the Landing Page per the brief's own "proceed page
by page, wait for approval" rule. Merging new palette/type values directly into
`tokens.css`/`index.css`'s `@theme` block would immediately repaint every authenticated page
(dashboard, Prediction/Match/Team Centers, Admin Center, ~90 files) with no review of how the new
system reads on data-dense authenticated screens it hasn't been designed against yet.
**Decision**: New tokens live in `frontend/src/styles/landing-tokens.css`, scoped under a
`.titan-landing` class applied only to the Landing Page's root element, imported only by that
route's lazy-loaded chunk. The rest of the app keeps consuming the Milestone 10 "Titan Blue"
system (ADR-060) untouched. The page's signature element — a 4-segment "Confidence Telemetry" bar
replacing plain percentage badges, tier colors borrowed from F1 sector-timing grammar (purple/
green/amber) — is built as a standalone component (`pages/landing/telemetry.tsx`) so it can be
promoted into the shared `components/domain/` layer later without a rewrite, once validated here.
**Alternatives considered**: Editing `tokens.css`/`@theme` directly now, treating the whole app as
in-scope immediately (rejected — the brief's own development rule is page-by-page with approval
gates; the authenticated app's ~90 files and their contrast/accessibility assumptions haven't been
reviewed against the new palette yet, and a global edit can't be limited back to "just the landing
page" if review finds an issue). Reusing the existing `ConfidenceMeter` domain component as-is
(rejected — it renders the old semantic-mapped bar; the new sector-bar visual language and tier
cutoffs are the page's signature and deserve their own component rather than retrofitting one built
for a different visual system).
**Consequences**: No regression risk to any authenticated page from this pass. Promoting the new
system app-wide is explicitly a follow-up milestone: swap `tokens.css`'s values, delete the
`.titan-landing` scope, and migrate `ConfidenceMeter` call sites onto `ConfidenceTelemetry` (or
merge them) once the rest of the app's pages are rebuilt against it, per the brief's own
page-by-page sequencing.

## ADR-063: Landing page content is honestly illustrative, matching the previous milestone's convention — not a live data pull

**Context**: The brief asks the Landing Page to show curated, real-feeling Intelligence Cards,
News Intelligence, Community Pulse, and a Knowledge Graph preview. Every endpoint that could
supply this (`sports_router.py`, `intelligence_router.py`, `prediction_router.py`,
`graph_router.py`) is `get_current_user`-gated — there is no public, unauthenticated data source
for a first-time visitor, and the brief's own rule is "never assume backend capabilities that do
not exist."
**Decision**: Keep the honest pattern the previous Landing Page milestone established: curated
sample content in `pages/landing/sample-data.ts`, field-shape-accurate to the real backend
`_serialize_*` functions (verified by reading `apps/api/routers/*.py` directly, not
`lib/api/types.ts` — see that file's header comment for the specific DTOs where `types.ts` has
drifted from the router source), with every section that renders it carrying a visible
"Illustrative" marker.
**Alternatives considered**: Presenting the sample content as if live (rejected — dishonest, and
inconsistent with the previous milestone's own documented rationale for why it can't be live);
building a new public/anonymous-read backend endpoint just to unblock this (rejected — out of the
approved scope for this pass; the brief requires proposing additive endpoints and waiting for
approval before backend work, and no page-specific need has been reviewed yet to justify one).
**Consequences**: The Landing Page is honest about what a signed-out visitor is seeing. If a future
milestone wants genuinely live landing-page content, it needs an explicit, approved additive
endpoint (e.g. a public, rate-limited "showcase predictions" read) — tracked as an open item, not
implemented here.

## ADR-064: Multi-Sport Intelligence shows Table Tennis, not Tennis, following the backend over the brief

**Context**: The uploaded brief's Prediction Markets section lists Football, Basketball, Baseball,
and Tennis as the four sports/market groups. The actual backend's Phase One sport set
(`docs/titaniq.md` §3, `modules/sports/domain/value_objects.SportCode`) is Football, Basketball,
Baseball, and Table Tennis — Tennis is explicitly listed as a *future expansion* sport with no
provider or plugin built yet. The brief's own top-level rule states the backend is the source of
truth and instructs against assuming capabilities that don't exist.
**Decision**: The Multi-Sport Intelligence section and its market list use Table Tennis, adapting
the brief's Tennis market names 1:1 onto Table Tennis's equivalent set-based structure (Match
Winner, Set Winner, Correct Set Score, Total Points, Handicap Points, First Set Markets).
**Alternatives considered**: Building the Tennis markets/UI as specified in the brief anyway
(rejected — would advertise a sport the backend cannot serve, the exact failure mode the brief
warns against); silently dropping the fourth sport (rejected — Table Tennis is real, live, Phase
One backend capability that deserves the same "every sport, one architecture" treatment as the
other three).
**Consequences**: If Tennis is added to the backend in a future milestone (new `SportCode`,
provider, plugin), the Multi-Sport section gains a fifth tab as an additive change — no rework of
the section's structure. Flagged explicitly to the user in this milestone's handoff, not silently
resolved.

---

*Next ADR number: 065. Add new decisions here as they're made — do not retroactively edit
earlier entries; supersede instead.*
