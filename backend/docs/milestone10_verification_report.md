# Milestone 10 Verification Report — Real Scheduled News Ingestion, Cost Control & Temporal Safety

## 1. Executive summary

Milestone 10 gives TitanIQ a genuine, cost-bounded, provenance-safe recurring news sync — the one
piece Milestone 9 explicitly flagged as missing. It does this almost entirely by *composing*
Milestone 8/9's already-real pipeline (`NewsIngestionService`, `IntelligenceEnrichmentOrchestrator`,
real RSS/Gemini providers) rather than building a parallel one. The only genuinely new production
code is: two new `SyncTrigger` members (`ADMIN_MANUAL`, `BACKFILL`), a thin `sync_all_sources`
loop, a deterministic pre-Gemini relevance filter, a small orchestration service that hardcodes
`LIVE_SCHEDULED` and enforces a Gemini budget, one new Celery task, one new Beat entry (registered
but inert), and a small additive kickoff-safety check layered onto `NewsMarketImpactEngine`. No
migration was created — every field this milestone needed already existed. `NEWS_SYNC_ENABLED`
defaults `False`; nothing in this milestone activates live news behavior by existing.

## 2. Files changed

- `modules/intelligence/domain/value_objects.py` — `SyncTrigger.ADMIN_MANUAL`/`BACKFILL` added.
- `modules/intelligence/application/news_ingestion_service.py` — `sync_source` gained an optional
  `since_floor` param; new `sync_all_sources`.
- `modules/intelligence/application/news_provenance.py` — new
  `is_information_available_before_kickoff`.
- `modules/predictions/application/news_market_impact_engine.py` — `_team_contributions`/
  `compute_and_write` gained an optional `kickoff` param (default `None`, every existing caller
  unaffected).
- `modules/ingestion/application/entity_reconciliation_service.py` — `_compute_news_market_impact`
  now passes `fixture.scheduled_at` as `kickoff`.
- `modules/ingestion/infrastructure/celery/beat_schedule.py` — one new, always-registered,
  internally-gated Beat entry.
- `apps/api/main.py` — `trigger_news_sync` now passes `ADMIN_MANUAL`, not the now-ambiguous
  `MANUAL`.
- `apps/api/composition.py` — new `build_scheduled_news_sync_service`.

## 3. Files created

- `modules/intelligence/application/news_sync_config.py` — env-driven config constants.
- `modules/intelligence/application/news_relevance_filter.py` — deterministic pre-Gemini filter.
- `modules/intelligence/application/scheduled_news_sync_service.py` — the real orchestration.
- `modules/intelligence/infrastructure/celery/tasks.py` (+ `__init__.py`) — the Celery task.
- `docs/milestone10_preimplementation_audit.md` — Phase 1 audit (see §21 for its key findings).
- 4 new test files, 3 updated test files (see §13).

## 4. Architecture changes

```
Celery Beat (always registered, gated internally)
    -> intelligence.sync_scheduled_news task (no `trigger` param exists on it — cannot be spoofed)
    -> ScheduledNewsSyncService.run()            [hardcodes trigger=LIVE_SCHEDULED internally]
         1. NEWS_SYNC_ENABLED check -> no-op if False (default)
         2. build relevance vocabulary from upcoming fixtures' teams/players + KG aliases
         3. NewsIngestionService.sync_all_sources()   [real RSS fetch + dedup, unchanged logic]
         4. deterministic relevance filter, BEFORE any Gemini call
         5. sort deterministically, truncate to NEWS_SYNC_MAX_ARTICLES_PER_RUN
         6. IntelligenceEnrichmentOrchestrator.enrich_article() per budgeted article
              -> EventExtractionService (real Gemini) -> confidence/provenance classification
              -> NewsMarketImpactEngine (now also kickoff-gated) -> Feature Store
```

No second ingestion pipeline. No mock Gemini in this path (the router already resolves the real
adapter whenever a credentialed provider exists — untouched). No new provider.

## 5. SyncTrigger changes

`modules.intelligence.domain.value_objects.SyncTrigger` now has 6 members:
`SCHEDULED, MANUAL, RETRY, LIVE_SCHEDULED, ADMIN_MANUAL, BACKFILL` — mirroring
`modules.ingestion`'s already-established split (M5), without importing it (module boundary
preserved). Only `LIVE_SCHEDULED` can ever produce `VERIFIED_PRE_MATCH`
(`classify_news_availability`'s existing `trigger is not LIVE_SCHEDULED -> UNKNOWN` rule, unchanged
— it already covered the new members correctly with no code change needed). `trigger_news_sync`
(the one real admin endpoint) now sends `ADMIN_MANUAL`. `BACKFILL` is reserved for a future
backfill script — none exists yet, confirmed in the Phase 1 audit.

## 6. Celery Beat configuration

One new entry, `sync-scheduled-news-football-epl`, always registered (Beat's schedule is static at
worker startup — a runtime toggle can't be expressed by conditionally omitting a dict entry):

```python
"sync-scheduled-news-football-epl": {
    "task": "intelligence.sync_scheduled_news",
    "schedule": timedelta(seconds=NEWS_SYNC_SCHEDULE_INTERVAL_SECONDS),  # 900s default
    "args": ("football", "21521495-4dd4-4c50-a41d-d88642322804"),  # same EPL season_id every other football entry uses
},
```

Verified live against `dev.db`: `BEAT_SCHEDULE` now has 21 entries (20 + 1), the new entry present
with the expected task name/interval/args.

## 7. Configuration variables

All in `news_sync_config.py`, `TITANIQ_`-prefixed, local `_env_bool`/`_env_int` (module-boundary
duplication, same posture as every prior `_env_int` in this codebase):

| Variable | Default | Purpose |
|---|---|---|
| `TITANIQ_NEWS_SYNC_ENABLED` | `false` | Master switch — no-op while false |
| `TITANIQ_NEWS_SYNC_INTERVAL_SECONDS` | 900 | Beat cadence |
| `TITANIQ_NEWS_SYNC_LOOKBACK_HOURS` | 48 | Floor on a fresh checkpoint's first fetch |
| `TITANIQ_NEWS_SYNC_MAX_ARTICLES_PER_RUN` | 20 | Hard Gemini budget per run |
| `TITANIQ_NEWS_SYNC_FIXTURE_WINDOW_HOURS` | 168 (7d) | Lookahead window for the relevance vocabulary |

Verified live: all five resolve to their documented defaults when unset in `dev.db`'s environment.

## 8. Relevance-filter implementation

`NewsRelevanceFilter` (`news_relevance_filter.py`) — word-boundary (not raw substring) case-
insensitive matching against a vocabulary built fresh per run from real data: every team/player in
a fixture scheduled within `NEWS_SYNC_FIXTURE_WINDOW_HOURS`, their canonical names, plus every
Knowledge Graph alias already on record (`kg_nodes.get_by_entity_ref` — the same round trip
`NewsMarketImpactEngine` already performs, no second alias system). Explicitly a cost pre-filter,
not a resolution step — real entity resolution is unchanged, still entirely post-Gemini. Word-
boundary matching specifically avoids the spec's own "aroma" vs "Roma" example (tested).

## 9. Gemini cost-control behavior

Two independent controls, both enforced before any Gemini call:
1. **Relevance filter** — an irrelevant article never reaches `enrich_article` at all.
2. **`NEWS_SYNC_MAX_ARTICLES_PER_RUN`** — relevant articles are sorted deterministically
   (`published_at` desc, article id as a stable tiebreak) and truncated to the budget *before* the
   enrichment loop starts, never mid-stream.

`DRY_RUN` (spec §22) is achievable today without new code: `NEWS_SYNC_ENABLED=true` +
`NEWS_SYNC_MAX_ARTICLES_PER_RUN=0` runs the full ingestion + relevance-filtering pipeline
(observable via the run summary's `articles_relevant`/`articles_skipped_by_relevance` counts) while
guaranteeing zero Gemini calls.

## 10. Temporal-validity implementation

Two layers, additive to each other:
- **Event-type TTL windows** (Milestone 9, unchanged) — `is_feature_eligible()` +
  `NewsMarketImpactEngine`'s existing `ttl_hours` re-check at read time.
- **New, direct fixture-kickoff check** (`is_information_available_before_kickoff`, strict `<`) —
  wired into `NewsMarketImpactEngine._team_contributions`/`compute_and_write` via an optional
  `kickoff` parameter (default `None`, zero behavior change for every M9 caller/test), populated
  by `EntityReconciliationService._compute_news_market_impact` from the real fixture's own
  `scheduled_at`. An event whose `information_available_at` is not strictly before that specific
  fixture's kickoff is excluded from that fixture's feature computation, even if otherwise
  eligible and within its TTL window — directly enforcing spec rule #9, not just relying on the
  TTL window's looser guarantee. Three direct tests prove `<`/`==`/`>` behave exactly as specified;
  one integration test proves the same rule inside the real engine; one test proves it against a
  naive (tzinfo-stripped) kickoff timestamp, the exact shape SQLite read-back produces.

## 11. Provenance behavior

`classify_news_availability` (unchanged) already made every non-`LIVE_SCHEDULED` trigger resolve
to `UNKNOWN_AVAILABILITY_TIME` — this correctly covers the two new members with zero code change:
`ADMIN_MANUAL` and `BACKFILL` can never produce `VERIFIED_PRE_MATCH`. Verified directly: the admin
endpoint's real HTTP response now reports `trigger: "admin_manual"`.

## 12. Security verification

- **Frontend cannot choose SyncTrigger** — no endpoint anywhere accepts a trigger value from a
  request body/param; `trigger_news_sync` hardcodes `ADMIN_MANUAL` server-side.
- **Task caller cannot override trigger** — `sync_scheduled_news_task`'s signature has no
  `trigger` parameter at all (asserted via `inspect.signature`, not just by convention).
  `ScheduledNewsSyncService.run` has no `trigger` parameter either — it's hardcoded inside the
  method body.
- **`NEWS_SYNC_MAX_ARTICLES_PER_RUN` cannot be bypassed** — enforced by list truncation before the
  enrichment loop even starts; tested directly with a 3-relevant/1-budget scenario.
- **Admin/manual ingestion cannot spoof `LIVE_SCHEDULED`** — tested directly against the real HTTP
  endpoint.
- **Secrets remain server-side** — inherited unchanged from M9's `GeminiAdapter` (API key travels
  only as a query param to Google's API, error messages are built from status code + response body
  only, never `str(exc)` on the request-carrying exception — nothing in M10 touches this code path).
  No new logging of credentials was added anywhere in this milestone.

## 13. Tests added

**37 test functions across 4 new files + 3 updated files** (30 net new against the M9 baseline —
7 replaced/rewrote no test, they only added):

- `tests/unit/modules/intelligence/test_news_ingestion_service.py` (+4): `since_floor` bounding a
  fresh checkpoint; `sync_all_sources` calls every source; one source's failure doesn't stop the
  others; `on_article_created` fires only for genuinely new articles.
- `tests/unit/modules/intelligence/test_news_relevance_filter.py` (8 new): normalization, relevant/
  irrelevant matching, alias matching, the word-boundary false-positive-avoidance case, empty
  vocabulary, case insensitivity.
- `tests/unit/modules/intelligence/test_scheduled_news_sync_service.py` (7 new): disabled no-ops
  entirely; enabled run always uses `LIVE_SCHEDULED`; irrelevant articles never reach enrichment;
  Gemini budget never exceeded; Gemini failure isolated + recorded, doesn't stop other articles;
  relevance vocabulary includes players and KG aliases; fixtures outside the window don't
  contribute vocabulary.
- `tests/unit/modules/intelligence/test_intelligence_celery_tasks.py` (4 new): task invokes the
  service with the resolved `now`; task signature has no `trigger` parameter; task returns the
  full summary dict; task raises a clear error without a configured factory.
- `tests/unit/modules/intelligence/test_news_provenance.py` (+3): `available_at < kickoff`
  eligible, `== kickoff` and `> kickoff` not eligible.
- `tests/unit/modules/predictions/test_news_market_impact_engine.py` (+3): post-kickoff event
  excluded even though otherwise eligible and within TTL; pre-kickoff event still contributes; a
  naive kickoff timestamp is normalized correctly (not just an aware one).
- `tests/unit/apps/test_api_news_ingestion.py` (+1): admin endpoint's real HTTP response reports
  `admin_manual`, never `live_scheduled`.

Every spec test item A–Q is covered: A (trigger distinctness, §5), B (§12), C (§5/§12), D/E
(§13 sync_all_sources tests), F/G (§8), H (unchanged from M9, re-confirmed no code path here
fabricates an entity ref), I (§9), J (§13 disabled test), K/L (§10), M (§11/§12), N (confirmed via
§18 dev.db check — no reclassification occurred, nothing in this milestone runs against dev.db's
real rows), O (full suite passing + no changes to `news_market_impact_registry.py`), P/Q (§17).

## 14. Full test-suite result

```
2096 passed, 58 skipped, 0 failed, 4 warnings in 1230.46s (0:20:30)
```

M9 baseline was 2066 passed / 58 skipped / 0 failed. Delta: **+30 passed, exactly the new test
count**, 0 skipped change, 0 failed. No regression anywhere — Milestones 5-9's own test suites
(provenance, lineup continuity, transfer activity, heuristic-market wiring, news intelligence,
prediction services, model registry, training pipeline, market registry, feature registry) all
still pass unchanged.

## 15. Database/migration status

**No migration was created.** Confirmed in the Phase 1 audit and again live against `dev.db`:
`intelligence_sync_runs.trigger` is `VARCHAR(16)` — both new values (`admin_manual` 12 chars,
`backfill` 8 chars, `live_scheduled` 14 chars) fit within the existing column, and a real
round-trip through the live admin endpoint against a SQLite-backed test DB confirmed no truncation
or constraint violation. Every other field this milestone reads or writes (`NewsEvent`'s
provenance columns, `IntelligenceSyncRun`'s counters, `NewsArticle`'s dedup columns) already
existed from Milestones 8-9.

Live `dev.db` state, checked directly, unchanged by this milestone's work (no live scheduled sync
was ever run against it — deliberately, to avoid uncontrolled real RSS/Gemini calls during
verification):
```
news_events: 68 rows, all still availability_classification='UNKNOWN_AVAILABILITY_TIME'
news_articles: 199 rows (unchanged)
intelligence_sync_runs: 23 rows (unchanged)
```

## 16. Known limitations

- **The Celery worker factory-wiring gap is pre-existing, not introduced here.** Confirmed in the
  Phase 1 audit: none of `set_orchestrator_factory`/`set_retraining_orchestrator_factory`/
  `set_calibration_service_factory` (all from M5/M8) are ever called outside tests — no real
  worker-startup entrypoint exists yet in this codebase. `set_scheduled_news_sync_service_factory`
  (this milestone's own) has the exact same shape and the exact same gap. A real Celery worker
  process would need this wiring added before any Beat-scheduled task (old or new) could actually
  execute in production. Out of scope for this milestone, same posture M9 took toward the missing
  Beat schedule itself.
- **8 of 9 registered news sources in `dev.db` have non-RSS URLs** (plain webpage URLs, not feed
  URLs) — a real scheduled run would fail cleanly and independently for those 8 (already-isolated
  per source, per §16's own design) until an operator curates real feed URLs. Data-quality, not a
  pipeline defect.
- **Relevance filtering is deterministic keyword matching, not semantic** — an accepted, documented
  limitation of a cost pre-filter (spec's own framing), not a defect in the (unaffected) resolution
  pipeline behind it.
- **No real backfill script exists yet** — `SyncTrigger.BACKFILL` is reserved, unused today.

## 17. Production enablement status

`NEWS_SYNC_ENABLED=false` everywhere by default — development, staging, and production all start
disabled. Recommended real activation sequence, matching spec §22 exactly:
1. **DISABLED** (ship state) — Beat entry registered, task fires on schedule, immediately no-ops.
2. **DRY_RUN** — `NEWS_SYNC_ENABLED=true`, `NEWS_SYNC_MAX_ARTICLES_PER_RUN=0`. Real RSS fetch +
   dedup + relevance filtering run and are observable via the task's returned summary; zero Gemini
   calls, zero cost.
3. **VALIDATION** — inspect a few DRY_RUN cycles' summaries (`sources_succeeded`,
   `articles_relevant`, `articles_skipped_by_relevance`) to confirm source health and relevance
   vocabulary quality before spending anything on Gemini.
4. **ENABLED** — raise `NEWS_SYNC_MAX_ARTICLES_PER_RUN` to a real value once (1) the worker-factory
   wiring gap (§16) is closed for a real deployment and (2) the source registry is curated to real
   feed URLs.

## 18. Acceptance-criteria checklist

- [x] SyncTrigger has unambiguous semantics (§5)
- [x] ADMIN_MANUAL exists (§5)
- [x] BACKFILL exists (§5)
- [x] LIVE_SCHEDULED exists (already did, from M9)
- [x] Manual news sync uses ADMIN_MANUAL (§5, §12)
- [x] sync_all_sources exists (§4, §13)
- [x] Scheduled Celery task exists (§6)
- [x] Scheduled task cannot accept an external trigger override (§12)
- [x] Celery Beat entry exists (§6)
- [x] NEWS_SYNC_ENABLED defaults false (§7)
- [x] NEWS_SYNC_INTERVAL_SECONDS exists (§7)
- [x] NEWS_SYNC_LOOKBACK_HOURS exists (§7)
- [x] NEWS_SYNC_MAX_ARTICLES_PER_RUN exists (§7)
- [x] Relevance filtering happens before Gemini (§8, §9)
- [x] Upcoming fixture aliases are used (§8)
- [x] Knowledge Graph aliases are reused, no second alias system (§8)
- [x] Gemini budget is enforced (§9, §12)
- [x] Provider failures are isolated (§13, inherited from M8's `sync_source` design)
- [x] Gemini failures are isolated (§13)
- [x] Temporal validity is explicitly tested (§10)
- [x] Timezone safety is explicitly tested (§10)
- [x] Only verified scheduled ingestion can produce VERIFIED_PRE_MATCH (§11)
- [x] Manual/backfill ingestion cannot spoof VERIFIED_PRE_MATCH (§11, §12)
- [x] Existing mock intelligence remains UNKNOWN_AVAILABILITY_TIME (§15)
- [x] Market-specific news impact remains intact (§4, §10 — additive only)
- [x] No unrelated markets receive news leakage (unchanged from M9, no code touched)
- [x] No model training occurs (nothing in this milestone touches training paths)
- [x] No .fit() occurs (confirmed by code review of every changed file)
- [x] No production model is changed (nothing touches ModelRegistryService)
- [x] No unnecessary migration is created (§15)
- [x] Security tests pass (§12)
- [x] Full regression suite passes (§14)
- [x] Documentation is complete (this report + the Phase 1 audit)

## Stop condition

Milestone 10 is complete and verified. Per the governing process and the user's own explicit
closing instruction: **STOP. Do not begin Milestone 11 automatically. Wait for explicit approval.**
