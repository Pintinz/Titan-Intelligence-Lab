# POST-M24 MASTER DATA FABRIC RESTRUCTURING — Phase 1 Audit Report

**Status: AUDIT ONLY. No code was modified. No live API calls, no Kaggle downloads, no Celery Beat
start, no training, no Champion/provenance changes were performed to produce this report** — every
finding below comes from reading source files, greeping the repository, and read-only queries
against local `dev.db`. Per the master prompt's explicit instruction, this report **stops** and
waits for authorization before any Phase 2 implementation begins.

**Important correction to earlier session documents**: `docs/historical_data_expansion_audit.md`
and `docs/post_m24_kaggle_historical_data_audit.md` (written earlier in this session, before this
master prompt) both state basketball/baseball have "only synthetic mock fixtures" / "zero fixtures"
in `dev.db`. **That is no longer true.** Between when those docs were written and this audit,
`dev.db` was modified (two new scripts — `scripts/register_secondary_sport_providers.py` and
`scripts/seed_secondary_sport_markets.py` — were added and run) and now contains **1,708 real
basketball fixtures and 3,923 real baseball fixtures** with real NBA/MLB team data. Section 9 covers
what changed and what is still actually blocking these sports — treat this report, not the earlier
two, as current for basketball/baseball.

---

## 1. What already exists

**Provider architecture.** `SportsDataProviderPort` (`modules/sports/ports/provider_gateway.py:160`)
defines 12 async methods (teams, fixtures, countries, players, standings, team_statistics, lineups,
odds, injuries, transfers, coach). Four concrete adapters implement it: `ApiFootballAdapter` (full
implementation, all 12 methods real), `ApiBasketballAdapter`/`ApiBaseballAdapter` (real for
teams/fixtures/players/standings/team_statistics; odds/injuries/transfers/coach inherited as no-op
stubs from `_ApiSportsHttpAdapterBase`), `FootballDataOrgAdapter`/`TheSportsDbAdapter` (narrow
fixture-schedule specialists — teams/fixtures/completed-fixtures/standings only, everything else
stubbed "stays api-football's job by design"), and `MockSportsDataProvider` (one generic,
sport-agnostic mock class implementing all 12 methods with deterministic fake data, used for every
sport including table_tennis).

`SportsProviderRouter` (`modules/sports/infrastructure/providers/provider_router.py:48`) resolves
**one adapter per sport** (real if active+credentialed, else mock) and routes every capability call
for that sport through it. A second, narrower slot — `fixture_schedule_adapters`, keyed by
provider_key, not sport — exists specifically for the upcoming-fixture-schedule concern, populated
today only with `football_data_org` and `thesportsdb`. `CompetitionFixtureSourcePreference`
(`modules/ingestion/domain/entities.py:99`) is a real, durable, admin-settable per-competition
routing override, but scoped to exactly this one capability (fixture-schedule sourcing), not a
general capability-preference mechanism.

**Caching, quota, dedup — more real infrastructure than the master prompt assumed.**
- Provider HTTP responses **are** cached today, inside `SportsProviderRouter._execute`
  (`provider_router.py:84-120`) — but as an **in-process Python `dict`**, keyed by tuples like
  `("fixtures", sport_code, competition_ref, season_label)`, TTL from the DB-configured
  `provider.cache_ttl_seconds` (default 3600s). Not Redis. Doesn't survive restarts or share across
  concurrent worker processes.
- Quota protection is real and **DB-backed**: `QuotaIntelligenceEngine`
  (`modules/admin/application/quota_intelligence_engine.py`) tracks daily/monthly request/error
  counts per provider+credential, computes remaining-ratio, calls `should_throttle()` before every
  real (non-mock) call in `_execute`, and can predict exhaustion hour. This already satisfies most
  of the master prompt's "Quota Guard" section — it just isn't named `ProviderQuotaGuard`.
- A circuit breaker (`modules/admin/application/circuit_breaker.py`) is also wired into `_execute`,
  but is in-memory-per-process, same durability caveat as the response cache.
- Concurrent-duplicate-request suppression is real via a Redis distributed lock
  (`modules/ingestion/infrastructure/cache/redis_lock.py`, `SyncOrchestrator._run_sync` acquiring
  key `sync:{sport}:{entity_kind}:{scope}`), but scoped to whole sync-orchestration runs, not
  individual provider endpoint calls — two *different* sync scopes needing the same underlying
  resource concurrently are not deduplicated at the HTTP layer.
- Two pieces of built cache infrastructure are **dead code**: `SyncCachePort`/`RedisSyncCache` is
  wired into `SyncOrchestrator.cache` but nothing in `modules/ingestion` ever calls
  `.get`/`.set`/`.delete` on it; `CachedKGNodeRepository` (a real read-through Redis decorator for
  the knowledge-graph module) is built and tested but never wired into `composition.py` at all.

**Celery/task architecture.** One shared Celery app (`modules/ingestion/infrastructure/celery/celery_app.py`),
Redis as both broker and result backend. Queue routing was deliberately **removed** (a prior
`"live"`/`"default"` queue split existed but nothing ever consumed those queues with `-Q`, so tasks
were silently stranded — the fix was deletion, not a new routing scheme). Every task today lands on
Celery's implicit default queue. 18 Beat-schedule entries cover football, basketball, and baseball
(standings, live-fixtures, health-check, retraining, calibration, EPL-specific fixture/news/
structured-intel sync) — no table_tennis entries (consistent with no provider existing).
`apps/worker/bootstrap.py` is a composition root only; nothing autostarts Beat.

**Historical/provenance machinery is already substantially built.** `EntityReconciliationService`
matching (`modules/ingestion/application/entity_reconciliation_service.py`) is fully
provider-agnostic — matches on `(provider, external_id)` tuples via `provider_ref_index`, no
hardcoded provider strings anywhere. `provider_ref_index` (`modules/ingestion/infrastructure/persistence/models.py:66`)
is already the generic N-provider identity-linking table the restructuring needs — its own docstring
states "adding a new kind here plus a reconciler is the entire extension surface," and the
`EntityKind` enum is the only thing that would need a new value for a new source. The provenance
classification function `classify_availability` (`modules/ingestion/application/provenance.py:83`)
is already fully generic across Injury/Transfer/Lineup/Suspension and gated on
`SyncTrigger.LIVE_SCHEDULED` only — a Kaggle-style importer needs zero changes here, since tagging
imports `SyncTrigger.BACKFILL` is already correctly handled (it resolves to
`UNKNOWN_AVAILABILITY_TIME`, never `VERIFIED_PRE_MATCH`). `SyncTrigger.BACKFILL` is not a dead enum
value — it's actively set today by `scripts/backfill_squad_intelligence.py` and the production
`NewsBackfillService`. `NewsBackfillService` (M12) is a strong architectural template for "bounded,
cost-controlled, checkpointed, reuse-not-duplicate historical catch-up" (dry-run-by-default, hard
lookback ceiling, hard per-run cap, explicit enable flag) — though it only speaks to RSS-shaped
sources, not arbitrary bulk datasets.

**Database schema.** Every structured-intelligence table (`lineups`, `injuries`, `suspensions`,
`transfers`) already carries `fetched_at`, `sync_run_id`, and `availability_classification` — exactly
the provenance shape a new historical importer needs, already present, no migration required.
`Fixture.period_scores` (JSON, nullable) already exists and is populated for basketball
(`{"kind": "quarter", ...}`) and baseball (`{"kind": "inning", ...}`); a `MatchPeriodKind.HALF` enum
value exists for football's HT/FT breakdown but no football adapter writes it into `period_scores`
yet (an unrelated, pre-existing gap, not something this restructuring needs to fix). The `datasets`
table (M20) is real and SQL-backed, not in-memory. `models.feature_versions` is a real JSON column.
The last 15 migrations are all additive-only — no destructive/renamed columns — a pattern this
restructuring should continue.

**RSS→Gemini news pipeline** already has real, working cost controls: a feed checkpoint +
`content_hash` dedup blocks re-ingesting the same article (so it never becomes a Gemini candidate
twice via the normal path), a relevance filter narrows to fixture-relevant articles, and a hard cap
(`NEWS_SYNC_MAX_ARTICLES_PER_RUN=20`) truncates the candidate list *before* any Gemini call. Gemini
output is durably persisted as `NewsEvent` rows.

## 2. What is missing

- **No `ProviderCapabilities` concept anywhere** — confirmed by two independent full-repo greps.
  Capability is implicit (which of the 12 port methods an adapter overrides vs. inherits a stub for)
  and undiscoverable except by reading each adapter's source. Two capabilities
  (`fetch_completed_fixtures`, alt-standings) aren't even on the Protocol — accessed via
  `getattr(adapter, ..., None)` duck-typing.
- **No `HistoricalDataImportPort` abstraction, even embryonically.** All 29 scripts under
  `scripts/` either recompute existing DB rows or call a *live* provider API to seed dev data — none
  reads from an external file/CSV/dataset. This is genuinely new surface to build, not a refactor.
- **`CrossProviderTeamMappingService.confirm_mappings` hardcodes `provider="football_data_org"`**
  (one literal string) — the only thing standing between it and true N-provider genericity. Everything
  else in that service is already provider-agnostic.
- **No "derive Season from a raw date" utility.** `Season` has `label` + a `DateRange` value object,
  but nothing today infers which season a raw historical date/competition belongs to — a new
  importer would need to write this classification logic itself.
- **Provider response cache and circuit breaker are in-memory, not distributed** — correct under a
  single worker process, silently loses effectiveness (extra API calls, not incorrect behavior) once
  multiple Celery worker processes run concurrently, which is the real deployment shape.
- **Concurrent-duplicate-request suppression only exists at the sync-run level, not per
  provider-endpoint** — a real (if narrow) gap versus the master prompt's "if two Celery tasks
  request fixture 123 concurrently, only one provider request should occur" requirement.
- **Two built pieces of cache infrastructure are unwired dead code**: `SyncCachePort`/`RedisSyncCache`
  and `CachedKGNodeRepository`.
- **No lookup-before-call guard immediately inside Gemini enrichment** (`event_extraction_service.py`
  / `intelligence_enrichment_orchestrator.py`) — currently masked by the upstream content-hash dedup
  gating the only real call path, but a latent gap if that path is ever called twice for the same
  un-deduplicated article (e.g., overlapping backfill/scheduled runs, or a retry after partial
  failure).
- **The `gemini_call_count` Ops metric is dead** — wired end-to-end (service → API → Ops UI tile)
  but never actually incremented by `GeminiAdapter`, `event_extraction_service.py`,
  `entity_extraction_service.py`, or `text_intelligence_router.py` in production code. Anyone
  reading that Ops tile today is seeing a permanent zero, not real telemetry.
- **No RSS conditional retrieval** (ETag/Last-Modified) — a bandwidth inefficiency, not a
  correctness/cost risk, since Gemini-cost dedup happens downstream regardless.
- **19 of the platform's 38 markets (all of basketball/baseball/table_tennis) have almost no outcome
  resolvers** — only `basketball.moneyline`, `baseball.moneyline`, `table_tennis.match_winner` (3 of
  19) have any resolver wired at all. This is a more basic gap than football's Group B half-result
  markets from the prior deliverable.
- **Basketball/baseball have exactly one feature calculator each** — a single generic rolling-average
  (`RollingTeamStatAverageCalculator` over points/runs, last 5 games). No differential, matchup, or
  expected-value features exist for these sports (football's whole suite of these has no
  basketball/baseball counterpart).
- **Table tennis has zero real provider, zero fixtures (real or otherwise persisted), and no
  documented target vendor anywhere** in code, docs, or `.env.example`.

## 3. What should be reused

- `provider_ref_index` + `EntityKind` enum, as-is, as the cross-provider identity index for any new
  source (Kaggle, a future basketball/baseball secondary provider, etc.) — extending it for a new
  `provider` value or a new `entity_kind` is additive, no schema change.
- `EntityReconciliationService`'s exact matching pattern (exact `(provider, external_id)` primary
  path, explicit opt-in fuzzy/secondary fallback that fails closed on ambiguity) — this is already
  the generalized reconciliation algorithm the master prompt asks for; a historical importer's
  fixture/team resolution should call into this service, not build a parallel one.
- `classify_availability` / `classify_news_availability` provenance gates — completely unchanged,
  zero modification needed; a Kaggle importer just needs to consistently pass
  `trigger=SyncTrigger.BACKFILL`.
- `NewsBackfillService`'s shape (`plan()`/`run()` split, dry-run-by-default, hard lookback + hard
  per-run cap, explicit enable flag, structured summary result) as the template for a new
  `HistoricalDataImportPort` implementation's control-flow and observability surface.
- `QuotaIntelligenceEngine` and `CircuitBreaker` exactly as they are — they already do real,
  DB-backed (quota) and in-memory (breaker) protection; Phase 2 should audit whether the breaker
  needs to become Redis-backed, not replace either service.
- `RedisDistributedLock` and its `sync:{sport}:{entity_kind}:{scope}` key convention — extend the key
  space (e.g. add a provider-endpoint-scoped lock) rather than building a second locking mechanism.
- The existing `MockSportsDataProvider` pattern for any sport that genuinely has no real provider
  yet (table_tennis) — do not build a second mock mechanism.
- `CompetitionFixtureSourcePreference` as the seed of a more general provider-preference mechanism,
  rather than discarding it for something unrelated.

## 4. What should be generalized

- **`SportsDataProviderPort` → explicit capability declaration.** The cleanest additive path: add a
  `capabilities() -> frozenset[ProviderCapability]` method (or a class-level constant) to the
  Protocol, with a default derived from "which methods does this adapter actually override vs.
  inherit the base no-op stub" so existing adapters don't need per-method rewrites — just a
  capability-set declaration each. `fetch_completed_fixtures` and the standings-alt method should
  formally join the Protocol (as optional-capability methods) instead of remaining duck-typed.
- **`SportsProviderRouter`'s per-sport-single-adapter assumption → capability-aware selection.**
  Today "one adapter serves this sport for everything" works because it happens to be true for
  football/basketball/baseball. It will not hold once a sport has two real adapters with
  complementary capabilities (exactly football's own `fixture_schedule_adapters` precedent). The
  `fixture_schedule_adapters` pattern is the right generalization target — broaden it from
  "provider-key-keyed slot for one narrow concern" to "provider-key-keyed slot selectable per
  capability," reusing `CompetitionFixtureSourcePreference`'s existing preference-storage shape
  rather than inventing a new one.
- **`CrossProviderTeamMappingService.confirm_mappings`** — parameterize the one hardcoded
  `provider="football_data_org"` literal into a method argument. This alone makes the whole service
  N-provider-generic; no other change needed.
- **The provider-response cache** — move from the in-process dict to a Redis-backed cache using the
  already-built (but currently dead) `SyncCachePort`/`RedisSyncCache`, reusing its existing
  key/TTL contract rather than inventing a new cache abstraction. This closes the "not shared across
  worker processes" gap and simultaneously stops `RedisSyncCache` from being dead code.
- **Feature-calculator wiring in `composition.py`** — the `form_differential_calculators` dict is
  literally `{"football": [...]}` today; generalizing it to a per-sport calculator registry (even a
  mostly-empty one for basketball/baseball right now) is a shape change worth making before adding
  real basketball/baseball calculators, so the registry, not a football-only special case, is the
  extension point.

## 5. What should NOT be changed

- `TrainingPreflightService`, `DatasetBuilder`, `DatasetSplitter`'s temporal-ordering logic, and the
  `datasets`/`models` table schemas — all already correct and already enforce exactly the guarantees
  (temporal integrity, training/inference parity, reproducible hashing) this restructuring must
  preserve. Zero evidence any of these need to change for multi-provider historical enrichment.
- Provenance gates (`classify_availability`, `classify_news_availability`,
  `SyncTrigger.LIVE_SCHEDULED`-only path to `VERIFIED_PRE_MATCH`) — confirmed airtight, confirmed
  already correctly handling `BACKFILL` as a non-live trigger. Do not touch.
- `EntityReconciliationService`'s core matching semantics — already provider-agnostic; risk of
  regression from a "generalization" here outweighs any benefit.
- `CompetitionType` enum (`LEAGUE`/`CUP`/`TOURNAMENT`) — flagged as coarse by prior audits, but per
  the master prompt's own instruction ("do not create a migration unless genuinely required... if
  not required, document it") — nothing in this restructuring's actual scope requires a finer
  distinction today. Documented here as a known limitation, not scheduled for a migration.
- `ApiFootballAdapter`, `FootballDataOrgAdapter`, `TheSportsDbAdapter` internals — all working,
  real, tested; the master prompt explicitly says don't rewrite them unnecessarily, and nothing in
  this audit found a genuine defect in any of the three, only a missing capability-declaration layer
  around them.
- Celery Beat schedule cadences and the queue-routing removal — the removal was itself a deliberate
  prior fix (dead queues nothing consumed); reintroducing per-task queue declarations without a
  worker invocation that actually consumes them would reintroduce the exact bug that was fixed.
- The market-seeding scripts' deliberate no-Champion posture for basketball/baseball/table_tennis
  (`seed_secondary_sport_markets.py`) — this is correct, intentional, and matches the master
  prompt's own "do not seed fake Champions" instruction. Not a gap to close in Phase 2/3.

## 6. Exact files requiring modification (for a later, authorized Phase 2/3)

Listed by restructuring concern, not in implementation order (see §10 for order):

- `modules/sports/ports/provider_gateway.py` — add capability declaration to
  `SportsDataProviderPort`; formalize `fetch_completed_fixtures` / standings-alt as part of the
  Protocol.
- `modules/sports/infrastructure/providers/api_sports_adapter.py`,
  `football_data_org_adapter.py`, `thesportsdb_adapter.py`, `mock_provider.py` — each adds a
  capability-set declaration (additive, no behavior change to existing methods).
- `modules/sports/infrastructure/providers/provider_router.py` — capability-aware adapter
  resolution; swap the in-process `_cache` dict for the `SyncCachePort` abstraction.
- `modules/ingestion/infrastructure/cache/redis_sync_cache.py` — no change needed; just needs a
  real caller (the router, once migrated).
- `modules/ingestion/application/cross_provider_team_mapping_service.py` — parameterize the
  `confirm_mappings` provider literal.
- New file(s): `modules/ingestion/ports/historical_import.py` (`HistoricalDataImportPort`),
  `modules/ingestion/infrastructure/historical_importers/kaggle_historical_importer.py` (Phase 4,
  not this phase) — mirroring `NewsBackfillService`'s dry-run/bounded/checkpointed shape and reusing
  `EntityReconciliationService` for team/fixture resolution.
- `apps/api/composition.py` — wiring for any of the above once built; `form_differential_calculators`
  generalized from a football-only dict to a real per-sport registry.
- `modules/predictions/basketball/`, `modules/predictions/baseball/` — new feature-calculator
  modules analogous to football's differential calculators, once real basketball/baseball features
  are prioritized (separate authorization per the master prompt's phased plan).

No file in this list requires a schema migration to support the change described for it.

## 7. Database/schema implications

**None required for Phase 2-4 as scoped.** Every schema element a generalized provider/historical
architecture needs already exists: `provider_ref_index` (generic identity linking),
per-entity provenance columns (`fetched_at`/`sync_run_id`/`availability_classification`) on the four
structured-intelligence tables, `Fixture.provider_refs` (JSON, multi-source attribution on the
entity itself), `datasets`/`models` tables (already real, SQL-backed). The only two schema-adjacent
items worth naming for future tracking, not action now:
- `EntityKind` enum would need a new value if a genuinely new entity type (not just a new provider
  for an existing kind) is ever ingested — a one-line, additive, no-migration change.
- Football's `period_scores` "half" kind is declared in the shared vocabulary but not yet populated
  by any football adapter — unrelated to this restructuring, worth flagging so it isn't rediscovered
  as a surprise later, but out of scope here.

## 8. Cache/quota risks

- **Process-local cache and circuit breaker under multi-worker deployment**: today's in-memory
  provider-response cache and circuit breaker mean N Celery worker processes each maintain
  independent state — a cache hit in worker A is invisible to worker B, and a circuit-open decision
  in worker A doesn't protect worker B from hammering a failing provider. This degrades quota
  efficiency (not correctness) proportional to worker count. `QuotaIntelligenceEngine` (DB-backed)
  is unaffected by this and remains the real backstop.
- **Sync-level lock does not prevent duplicate concurrent calls for the same underlying resource
  across different sync scopes** — e.g., a fixture-level odds sync and a fixture-level
  team-statistics sync running concurrently for the same fixture are not deduplicated against each
  other, only against themselves.
- **Dead cache infrastructure risk**: `SyncCachePort`/`RedisSyncCache` and `CachedKGNodeRepository`
  being unwired means any future engineer who assumes "there's already a generic cache in front of
  X" based on reading their code will be wrong until they're actually wired in — worth resolving
  (wire or remove) rather than leaving ambiguous.
- **No quota risk was found from adding Kaggle/historical import work itself** — by design, a
  file-based historical importer makes zero live API calls, so it cannot consume provider quota at
  all. The only quota interaction a historical importer has is indirect: if entity resolution needs
  a live lookup to disambiguate a team/fixture, that lookup should go through the existing
  quota-guarded router, not bypass it.

## 9. Provider-specific risks

- **Football**: lowest risk — three real adapters (`ApiFootballAdapter`,
  `FootballDataOrgAdapter`, `TheSportsDbAdapter`) already coexist via the `fixture_schedule_adapters`
  precedent; generalizing capability declaration is additive and low-blast-radius here.
- **Basketball/Baseball — situation materially changed mid-session.** `api_basketball`/`api_baseball`
  are now registered, active, and credentialed (reusing the shared API-Sports key), and `dev.db`
  now holds 1,708 real basketball and 3,923 real baseball fixtures with real NBA/MLB team data.
  Markets are seeded (7 basketball + 6 baseball, all `production` status) with **zero Champion
  models** — a deliberate, correct posture per `seed_secondary_sport_markets.py`'s own docstring,
  not a bug. **The real remaining risk for these two sports is not "no data" — it's "16 of 19
  secondary-sport markets have no outcome resolver at all"** (only the 3 `*.moneyline`/`match_winner`
  markets do) and each sport has exactly one generic rolling-average feature calculator. This is a
  more basic gap than football's post-M24 half-result-resolver work — most secondary-sport markets
  can't record a `PredictionOutcome` at all today, regardless of data volume.
- **Table tennis**: highest risk / least ready. No real provider exists anywhere in code or docs, no
  vendor is named anywhere (`.env.example`, comments, `docs/*.md`), zero fixtures (real or mock)
  are ever persisted since nothing calls the mock provider's fetch methods into the DB. Any Phase 5
  work here is blocked on a business decision (which vendor to integrate), not an engineering gap —
  correctly out of scope until that decision is made, consistent with the master prompt's own "do
  not create a fake production adapter" instruction.
- **Kaggle (once authorized in a later phase)**: primary risk is scope creep — the master prompt is
  explicit that Kaggle must never touch live-provider interfaces or provenance gates. Given
  `classify_availability`/`SyncTrigger.BACKFILL` are already correctly wired to prevent this, the
  main engineering risk is really in the *new* code (a `KaggleHistoricalImporter`) failing to set
  `trigger=BACKFILL` correctly on every write path, not in the existing gates being weak.

## 10. Implementation order (for Phase 2 onward, pending authorization)

1. **Cache/quota safety** (master prompt's own Phase 2): wire `SyncCachePort`/`RedisSyncCache` as the
   real backing store for `SportsProviderRouter`'s response cache (replacing the in-process dict);
   write the repeated-request / concurrent-request / quota-exhaustion tests the master prompt
   specifies. Low risk, no schema change, immediately improves quota efficiency under multi-worker
   deployment.
2. **Provider capability declarations** (Phase 3): add capability sets to the Protocol and every
   adapter; make `fetch_completed_fixtures`/standings-alt first-class. Purely additive, no behavior
   change to any existing call site.
3. **`CrossProviderTeamMappingService` generalization**: parameterize the one hardcoded provider
   string. Trivial, unblocks reuse by any future second provider for any sport.
4. **`HistoricalDataImportPort` + first concrete importer** (Phase 4): build the port and a
   `KaggleHistoricalImporter` (or a `football-data`-historical importer first, if a smaller first
   slice is preferred), reusing `EntityReconciliationService` and `classify_availability` as-is.
   Ship read/validate/reconcile logic behind a dry-run-by-default flag, mirroring
   `NewsBackfillService`.
5. **Basketball/baseball resolver + feature-calculator work** (separate, later authorization; this
   is now the actual bottleneck for those two sports, not data availability): wire outcome resolvers
   for the remaining 16 secondary-sport markets, and build real differential/matchup feature
   calculators analogous to football's.
6. **Table tennis**: blocked on a vendor decision; no engineering order applies until one is made.
7. **Re-run `TrainingPreflightService`** (master prompt's Phase 7) after each of the above steps that
   could plausibly change feature coverage, to confirm no market's readiness verdict silently
   changed and no market was force-marked ready.

## 11. Test strategy

- Every existing test file that exercises `SportsProviderRouter`, `EntityReconciliationService`,
  `CrossProviderTeamMappingService`, and the provenance classification functions must be re-run
  unchanged first, as a regression baseline, before any Phase 2+ change (current baseline: 2256
  passed, 58 skipped, 0 failed, confirmed in this session's prior deliverable).
- New capability-declaration tests: for each adapter, assert its declared capability set matches
  which methods it actually overrides vs. inherits a stub for (prevents declaration/implementation
  drift).
- Cache migration tests (master prompt's own Phase 2 list, verbatim): repeated request → one
  provider call; concurrent identical request → one provider call; cache hit → zero provider call;
  expired cache → provider call; quota exhaustion → safe fallback; wrong sport → no cache collision;
  wrong season → no cache collision.
- `HistoricalDataImportPort`/Kaggle importer tests (once built): schema validation failure → no
  write; ambiguous fixture match → fail closed, no write; duplicate detection → no double-insert;
  every written row asserted `sync_trigger=BACKFILL` and `availability_classification` never
  `VERIFIED_PRE_MATCH`/`LIVE_SCHEDULED`-equivalent; dry-run mode → zero writes, full plan reported.
- `CrossProviderTeamMappingService` generalization: existing football_data_org-specific tests must
  keep passing unchanged; add a second-provider parametrized test to prove the generalization is
  real, not just theoretical.
- Full backend regression suite after every phase, not just the phase's own targeted tests — this
  session's own precedent (`pytest -q` full run) should continue.

## 12. Rollback strategy

- Every proposed Phase 2-4 change is additive (new capability metadata, new cache backing store
  behind the same port interface, new importer module, one parameterized argument) — no existing
  call site's behavior changes unless it explicitly opts in, mirroring this session's own
  `resolve_for_fixture(..., home_score_ht=None)` pattern. This means rollback for any individual
  piece is simply "stop calling the new code path" / "revert the one file," not a multi-file
  coordinated rollback.
- The cache-backend swap (in-process dict → `SyncCachePort`) is the only change with real runtime
  behavior implications (cache hit/miss timing changes); it should be the first and most heavily
  tested change specifically so any regression surfaces early and in isolation, before capability
  declarations or the historical importer are layered on top.
- No migration is proposed in this phase, so there is no migration to roll back.
- `SyncTrigger.BACKFILL`-tagged historical import data can always be identified and purged by trigger
  type alone (it's a real, queryable column on every structured-intelligence table plus
  `NewsEvent`), giving a clean, targeted rollback path for a bad historical import run without
  affecting any live-sourced data.

---

## Summary

TitanIQ's existing architecture is substantially closer to what this master prompt asks for than a
first read of the prompt would suggest: a real, DB-backed quota engine; a real (if in-memory)
circuit breaker; a real distributed lock; a fully provider-agnostic entity-reconciliation core; a
generic cross-provider identity index; airtight provenance gates already correctly handling
`BACKFILL`; and a durable, reproducible dataset/model registry. The genuine gaps are narrower than
"rebuild the data fabric": (1) no explicit capability declaration on providers, (2) the response
cache and circuit breaker are process-local instead of distributed, (3) no file-based historical
import path exists yet, (4) one hardcoded provider string in the team-mapping service, and (5) for
basketball/baseball specifically, the real blocker has shifted from "no data" to "almost no outcome
resolvers and almost no feature calculators" — a fact the earlier same-session audit docs did not
yet reflect. Table tennis remains correctly, categorically blocked on a vendor decision.

**Awaiting explicit authorization before starting Phase 2 (cache/quota safety implementation).**
