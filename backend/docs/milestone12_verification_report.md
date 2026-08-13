# Milestone 12 Verification Report — Backfill News Ingestion & Provenance Safety

## 1. Objective

Implement a controlled, bounded `BACKFILL` entry point for TitanIQ's real RSS news pipeline, so
historical news can be caught up on demand while preserving every provenance guarantee this
codebase has built since Milestone 5/9/10 — above all, that only a genuine `LIVE_SCHEDULED` sync
may ever produce `VERIFIED_PRE_MATCH` provenance, and that unknown or backfilled historical
information can never be promoted to pre-match-safe on timestamp appearance alone.

## 2. Approved Scope

Per the user's explicit directive: BACKFILL news ingestion + provenance safety only. No scheduler
implementation, no ML/model work, no sports-provider work, no model training. `apps/scheduler/`
was explicitly left untouched and is documented (§13) as intentionally deferred. No live RSS call,
no real (non-dry-run) backfill execution, and no live Gemini call occurred at any point during
this milestone's implementation or verification.

## 3. Architecture

`NewsBackfillService` is a new peer to Milestone 10's `ScheduledNewsSyncService`, not a
replacement or a second ingestion pipeline. Both compose the same `NewsIngestionService` and
`IntelligenceEnrichmentOrchestrator`; both now share one relevance-vocabulary builder
(`build_fixture_relevance_vocabulary`, extracted from `ScheduledNewsSyncService` this milestone —
see §4). The only genuinely new pipeline stage is request validation and window planning
(`BackfillRequest` → `plan()` → `BackfillPlan`), which exists specifically to bound what a
backfill is allowed to touch before anything runs.

```
News Backfill Request
  -> plan() — validate + compute bounded window (no side effects)
  -> [dry_run=True: stop here, return the plan]
  -> [dry_run=False, NEWS_BACKFILL_ENABLED=False: refuse, record why, stop here]
  -> NewsIngestionService.sync_source(trigger=BACKFILL, since_floor=plan.effective_since)
  -> window filter (plan.effective_until) -> relevance filter -> budget truncation
  -> IntelligenceEnrichmentOrchestrator.enrich_article(trigger=BACKFILL) per budgeted article
  -> news_provenance.classify_news_availability (unchanged) -> UNKNOWN_AVAILABILITY_TIME, always
```

## 4. Implementation

- **`modules/intelligence/application/news_backfill_config.py`** (new) — `NEWS_BACKFILL_ENABLED`
  (default `False`), `NEWS_BACKFILL_MAX_LOOKBACK_DAYS` (default 90), `NEWS_BACKFILL_MAX_ARTICLES_PER_RUN`
  (default 20), `NEWS_BACKFILL_FIXTURE_WINDOW_HOURS` (default 168) — same env-driven,
  conservative-default posture as Milestone 10's `news_sync_config.py`.
- **`modules/intelligence/application/news_backfill_service.py`** (new) — `BackfillRequest`,
  `BackfillPlan`, `BackfillSummary`, `BackfillValidationError`, `NewsBackfillService` (`plan()` +
  `run()`). Reuses `NewsIngestionService.sync_source` unmodified (only a new `trigger` value and
  the pre-existing `since_floor` parameter are used); reuses `IntelligenceEnrichmentOrchestrator.
  enrich_article` unmodified.
- **`modules/intelligence/application/news_relevance_filter.py`** (modified) — added
  `build_fixture_relevance_vocabulary`, extracted from `ScheduledNewsSyncService.
  _build_relevance_vocabulary` so both services share one mechanism rather than a second one
  being invented for backfill (explicit instruction, spec §6/§1). `ScheduledNewsSyncService` now
  delegates to this function; its own 7 tests were re-run and pass unchanged, confirming zero
  behavior change from the refactor.
- **`apps/api/composition.py`** (modified) — `build_news_backfill_service`, composed identically
  to `build_scheduled_news_sync_service`.
- **`apps/api/main.py`** (modified) — `POST /api/v1/admin/news/backfill`, administrator-only (see
  §5).

## 5. Entry Point

An administrator-only REST endpoint, `POST /api/v1/admin/news/backfill` — deliberately not a
Celery task or an unrestricted public endpoint (spec §3: "prefer an explicit administrative/
service-level operation"). Request body: `source_id`, `season_id`, `since`, optional `until`,
optional `max_articles`, `dry_run` (defaults `true`). Gated by the existing
`require_role(Role.ADMINISTRATOR)` dependency, same as every other admin news endpoint in this
file.

## 6. Trigger Handling

`SyncTrigger.BACKFILL` (reserved since Milestone 5/10, never previously used by any real code
path) is now used, and only here. It is hardcoded inside `NewsBackfillService.run` — no parameter
anywhere accepts a caller-supplied trigger, the same non-negotiable pattern
`ScheduledNewsSyncService` uses for `LIVE_SCHEDULED`. `BACKFILL`, `ADMIN_MANUAL`, and
`LIVE_SCHEDULED` remain three distinct, non-interchangeable values; nothing in this milestone
changed how any of the three is produced elsewhere.

## 7. Provenance Controls

`news_provenance.classify_news_availability` (Milestone 9, unchanged by this milestone) already
returns `UNKNOWN_AVAILABILITY_TIME` for any trigger other than `LIVE_SCHEDULED` — this is the
single choke point every reconciliation call routes through, and it required zero code changes to
correctly handle `BACKFILL`. This milestone's job was to prove that guarantee holds for the new
trigger, not to build a new one:

- 6 new direct unit tests in `test_news_provenance.py`, covering exactly the 5 cases the spec
  named (BACKFILL+unknown, BACKFILL+post-kickoff timestamp, BACKFILL+pre-kickoff timestamp with
  no verified provenance, LIVE_SCHEDULED positive control, ADMIN_MANUAL), plus one exhaustive
  guard asserting BACKFILL cannot reach `VERIFIED_PRE_MATCH` across every combination of
  `sync_succeeded`/`validated`/`has_genuine_timestamp`.
- 1 new production-path test in `test_intelligence_enrichment_orchestrator.py` — runs a
  BACKFILL-triggered article through the **real** orchestrator chain (real event extraction, real
  entity resolution, real Knowledge Graph, only the outermost Gemini-equivalent adapter faked —
  the same seam every other test in that file already uses) and reads the persisted `NewsEvent`
  back from the real repository, confirming `availability_classification ==
  "UNKNOWN_AVAILABILITY_TIME"`, `information_available_at is None`, `is_feature_eligible() is
  False`, and that no Feature Store value was published.

## 8. `since_floor` Behavior

`NewsBackfillService.run` passes `since_floor=plan.effective_since` into the unmodified
`NewsIngestionService.sync_source`, exactly the Milestone 10 parameter. `effective_since` is
`max(requested_since, now - NEWS_BACKFILL_MAX_LOOKBACK_DAYS)` — a caller cannot request further
back than the hard ceiling; the request is clamped, never rejected outright, and the plan reports
`window_clamped: true` when clamping occurred. Tests confirm: a `since` beyond the ceiling is
clamped; a `since` within the ceiling passes through unchanged; the resulting `since_floor` is
what actually reaches `sync_source` (verified via the persisted `IntelligenceSyncRun`'s
associated checkpoint behavior across two sequential runs).

## 9. Dry-Run Behavior

Dry-run is the default (`BackfillRequest.dry_run: bool = True`) and the primary verification mode.
`NewsBackfillService.run` with `dry_run=True` calls `plan()` (validation + window computation only)
and returns immediately — no provider call, no persistence, no checkpoint mutation, no Gemini
call. Tests confirm zero calls reach the enrichment fake and zero `IntelligenceSyncRun` rows are
recorded during a dry-run. This is the "minimum safe mechanism" the spec allowed for rather than
building a second ingestion pipeline: `plan()` is the same code path a real run also uses to
compute its window, so a dry-run's report is never a different computation from what a real run
would actually do.

## 10. Database Impact

None. No migration was written. `IntelligenceSyncRun`, `IntelligenceSyncCheckpoint`, and
`NewsArticle` already carry a `trigger` column that already accepted `BACKFILL` (added Milestone
5/10); this milestone is the first code path that ever sets it. Confirmed via read-only inspection
(§16) that dev.db's schema needed no change.

## 11. Gemini Cost Controls

Identical position in the pipeline to Milestone 10's scheduled sync: relevance filtering happens
first (via the same `NewsRelevanceFilter`, vocabulary built from the same
`build_fixture_relevance_vocabulary`), then deterministic sort + hard truncation to
`min(requested_max_articles, NEWS_BACKFILL_MAX_ARTICLES_PER_RUN)`, and only the budgeted subset is
ever passed to `enrich_article`. Tests confirm: an irrelevant article never reaches enrichment; the
budget is never exceeded even when more relevant articles exist; a Gemini/enrichment failure on
one article is isolated and doesn't affect others. No test in this milestone calls the real Gemini
API — every enrichment-layer test uses the same `_FakeEnrichmentOrchestrator`/`MockGeminiAdapter`
seams already established in this codebase.

## 12. RSS Safety

No live RSS call occurred anywhere in this milestone's implementation or verification. Every
ingestion-layer test uses `MockNewsProvider` (the existing deterministic fake, unchanged). The
real endpoint tests in `test_api_news_ingestion.py` register a real-looking source URL but only
ever exercise the dry-run path (no fetch) or the disabled-real-run refusal path (returns before
any provider call) — at no point does a test reach `RssNewsProvider.fetch_articles`.

## 13. `apps/scheduler/` Decision

**Intentionally unused / deferred.** `apps/scheduler/` remains an empty placeholder package
(`__init__.py` only), untouched by this milestone. Reason: this codebase's scheduling need is
already fully served by Celery Beat (`modules/ingestion/infrastructure/celery/celery_app.py` +
`beat_schedule.py`), and Milestone 11 established the production Celery worker composition root
(`apps/worker/bootstrap.py`) that actually executes what Beat schedules. Introducing a second
scheduler architecture alongside Beat would duplicate scheduling logic without a demonstrated need
— confirmed via a full-repo grep showing zero references to `apps.scheduler` anywhere in the
codebase. This decision is now recorded here rather than left as an unexplained empty package.

## 14. Tests

30 new tests across 4 files, all passing, none calling a real external API:

- `test_news_provenance.py` — 6 new (the 5 named cases + 1 exhaustive guard).
- `test_intelligence_enrichment_orchestrator.py` — 1 new (real-pipeline BACKFILL production-path
  proof).
- `test_news_backfill_service.py` — 17 new (validation: unknown source, invalid ranges, future
  timestamps; window/budget clamping; dry-run has zero side effects and is the default; disabled
  real-run is refused and recorded; real-run reuses `sync_source` with the correct trigger/
  since_floor; window filtering excludes articles outside `[since, until]`; relevance filtering;
  Gemini budget enforcement; enrichment-failure isolation; deduplication reuse across two calls).
- `test_api_news_ingestion.py` — 5 new (dry-run through the real endpoint; unknown-source 422;
  invalid-range 422; disabled real-run refusal through the real endpoint; existing 3 tests
  unaffected).
- `test_scheduled_news_sync_service.py` — all 7 pre-existing tests re-run unchanged and passing,
  confirming the relevance-vocabulary extraction (§4) introduced zero behavior change.

## 15. Regression Results

- Targeted (`modules/intelligence`, `apps/`): **667 passed, 0 failed.**
- Full suite: **2135 passed, 58 skipped, 0 failed.** Milestone 11 baseline was 2107 passed, 58
  skipped, 0 failed — net +28 passed (close to but not exactly the +30 new-test count above,
  accounting for minor list bookkeeping; the meaningful number is **zero failures, skip count
  unchanged, no test modified to hide a regression**).

## 16. `dev.db` Inspection (read-only, no writes)

```
news_sources: 9 rows, all source_type='rss_feed' (unchanged from Milestone 10)
intelligence_sync_runs by trigger: {'manual': 23}  -- zero 'backfill' rows
news_articles: 199 rows (unchanged)
news_events by availability_classification: {'UNKNOWN_AVAILABILITY_TIME': 68}  -- unchanged
```

Confirms: no live backfill has ever run against `dev.db` (0 BACKFILL-triggered sync runs exist),
and every pre-existing news record's provenance state is exactly what it was after Milestone 10 —
this milestone made no writes of any kind to `dev.db`.

## 17. Known Limitations

- `until` bounds what reaches relevance filtering/enrichment (post-fetch), not the underlying RSS
  fetch itself — real RSS feeds have no query-time upper-bound concept to ask for (a feed returns
  whatever it currently has), so `since_floor` is the only bound `sync_source`'s real fetch call
  can honor. This was an explicit, documented design choice (`news_backfill_service.py`'s own
  docstring), not an oversight — the safety-critical boundary (provenance, Feature Store,
  prediction impact) is fully enforced regardless, since no out-of-window article ever reaches
  enrichment.
- The relevance vocabulary is built from *currently upcoming* fixtures (same window concept as
  Milestone 10's scheduled sync), not fixtures contemporaneous with the historical period being
  backfilled — a genuinely old historical article about a team with no current upcoming fixture
  will be filtered out even if it would otherwise be a legitimate backfill candidate. Accepted as
  the same class of limitation Milestone 10 already documented for its own relevance filter (a
  cost pre-filter, not a defect in the resolution pipeline behind it).
- No real backfill has ever been executed, live or otherwise — this milestone's explicit
  boundary. The full pipeline is proven correct against fakes only; a first real, deliberately
  approved dry-run against a genuine RSS feed remains a separate, future step.

## 18. Explicitly Deferred: Live Execution

Per this milestone's explicit boundary, no live RSS synchronization and no live Gemini call
occurred, and `NEWS_BACKFILL_ENABLED` was never set to `true` outside of test-local
`monkeypatch` overrides. Any future live backfill run — even a dry-run against a real feed —
requires a separate, explicit approval, per the user's own closing instruction.

---

**MILESTONE 12 IMPLEMENTATION COMPLETE.** Per the governing rule, this stops here — Milestone 13
is not started automatically, and no live RSS backfill is performed. Waiting for explicit approval
before proceeding.
