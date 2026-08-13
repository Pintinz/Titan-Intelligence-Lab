# Milestone 11 Verification Report — Celery Worker Runtime Wiring, Scheduled Intelligence Execution & Production Task Safety

## 1. Executive Summary

Milestone 11 closes the production runtime gap identified in its own mandatory Phase 1 audit: a
real `celery -A ... worker` process, as this codebase stood before this milestone, would never
have registered a single task (no `include=[...]`, no `autodiscover_tasks()` anywhere) and would
have raised `RuntimeError("... factory not configured")` on the first invocation of any of the
five DI-factory-backed tasks (no production caller ever invoked a `set_*_factory` function).

This milestone adds exactly one production composition root, `apps/worker/bootstrap.py`, that:
imports all four existing Celery task modules (making every task, not just the five new ones,
actually registered with the shared `celery_app`); builds a dedicated, autocommit-isolated
worker-context database engine; wires all five production factories to real, composed application
services; and validates the wiring is complete before the worker reports ready — failing closed,
with a named factory/service/affected-tasks error, if it is not.

No existing task's business logic, retry policy, or Beat schedule entry was changed. No database
migration was required. `NEWS_SYNC_ENABLED` remains `False` by default; no external API call
(RSS, Gemini, or otherwise) was made at any point during implementation or verification.

Full regression suite: **2107 passed, 58 skipped, 0 failed** — exactly +11 over the Milestone 10
baseline (2096 passed, 58 skipped, 0 failed), matching the 11 new tests added this milestone with
zero regressions elsewhere.

## 2. Initial Runtime Audit (Phase 1 Findings)

Performed read-only, directly via Grep/Read/Bash (the `Agent` tool proved unreliable earlier in
this milestone sequence and was not used for this audit). Two compounding, previously
undocumented gaps were found, both more foundational than what Milestone 10's own report had
flagged:

1. **No task module was ever imported in a production process.** `modules/ingestion/infrastructure/
   celery/celery_app.py` declares no `include=[...]`, and a full-repo grep found no call to
   `app.autodiscover_tasks()` anywhere. Every `@celery_app.task`-decorated function across all four
   task modules is invisible to a real worker process started via `celery -A ... worker` — not
   just the Milestone 10 news-sync task, but every ingestion, admin, and predictions task that
   already existed. Tests never surfaced this because they import task modules directly and run
   them eagerly in-process (`task_always_eager=True`), bypassing Celery's task registry entirely.
2. **No production caller ever invoked any of the five `set_*_factory` functions.** Each factory's
   fail-closed `RuntimeError` (already correct, left unchanged) fires on the very first real task
   execution in a live deployment, since nothing upstream ever configured it.

A secondary finding: `apps/worker/` and `apps/scheduler/` both existed as empty packages
(`__init__.py` only) — pre-existing placeholders referenced by name in `modules/sports/
bootstrap.py`'s own docstring ("apps/api and apps/worker call `build_sport_plugin_registry()` at
startup") but never filled in.

Per the milestone spec's unconditional Phase 1 instruction, work stopped after this audit and
findings were presented in chat for explicit approval before implementation began.

## 3. Celery Architecture Before This Milestone

One shared `Celery("titaniq_ingestion")` app instance (`modules/ingestion/infrastructure/celery/
celery_app.py`), Redis-backed broker/result-backend, `task_acks_late=True`, dead-letter handling
on final-retry failure via a `task_failure` signal handler, and a `configure_for_tests()` helper
used by the test suite for eager, synchronous execution. Four task modules each independently
implement the identical DI pattern: a module-level `_factory: Callable[[], Awaitable[X]] | None`,
a `set_X_factory(factory)` setter, and an `async def _get_X()` that raises a fail-closed
`RuntimeError` if the factory was never set. All four share the identical bounded-retry policy
(`autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3`). This
milestone changed none of it — every task-side symbol above is untouched.

## 4. Factory Inventory

| Factory | Module | Produces | Affected task(s) |
|---|---|---|---|
| `orchestrator` | `modules.ingestion.infrastructure.celery.tasks` | `SyncOrchestrator` | 11 ingestion tasks (countries, teams, fixtures, live fixtures, standings, standings-alt, upcoming fixtures, completed fixtures, upcoming structured intelligence, odds, team statistics) |
| `admin_context` | `modules.admin.infrastructure.celery.tasks` | `(ProviderManagementService, HealthIntelligenceEngine)` | `admin.check_all_provider_health` |
| `retraining_orchestrator` | `modules.predictions.infrastructure.celery.tasks` | `ScheduledRetrainingOrchestrator` | `predictions.check_scheduled_retraining` |
| `calibration_service` | `modules.predictions.infrastructure.celery.tasks` | `CalibrationFittingService` | `predictions.check_scheduled_calibration` |
| `scheduled_news_sync` | `modules.intelligence.infrastructure.celery.tasks` | `ScheduledNewsSyncService` | `intelligence.sync_scheduled_news` |

This is the exact, explicit registry now recorded in code as `FactoryRecord` entries in
`apps/worker/bootstrap.py`'s `_fresh_registry()` — one entry was found to have an inaccuracy during
testing (see §16) and was corrected.

## 5. The Production Wiring Gap (Root Cause)

Both audit findings (§2) share one root cause: this codebase has a composition root for FastAPI
(`apps/api/main.py` + `apps/api/composition.py`, wired at ASGI app import time) but never had an
equivalent for Celery. The task modules' DI-factory pattern was fully built (Milestone 5 onward)
but nothing ever called it in a real worker process — only tests did, via direct `set_*_factory`
calls in fixtures. This is precisely the gap the spec's own testing section (§13/item M) called
out by name: "the previous test architecture is part of the reason this production gap survived."

## 6. Composition-Root Implementation

`apps/worker/bootstrap.py` is the single new composition root, modeled directly on `apps/api/
composition.py`'s existing `build_*` factory-function conventions — it imports and reuses those
same builders (`build_sync_orchestrator`, `build_provider_management_service`,
`build_health_intelligence_engine`, `build_scheduled_retraining_orchestrator`,
`build_calibration_fitting_service`, `build_scheduled_news_sync_service`) rather than
reimplementing service construction. It re-exports the shared `celery_app` at module level so a
real worker starts via:

```
celery -A apps.worker.bootstrap worker --loglevel=info
```

## 7. Worker Bootstrap Implementation

`bootstrap_worker()` runs the exact sequence the spec requires: configuration validation →
database session-factory construction → task-module imports → factory registration → factory
registry validation → ready. It is directly callable and directly testable without a live Celery
worker process, and is also wired to fire automatically, exactly once per forked worker process,
via Celery's `worker_process_init` signal (chosen over `worker_ready`/`celeryd_init` because it
fires once per process, before the worker begins accepting tasks, and is the correct point to
create a process-local async DB engine — an engine created before a prefork fork is unsafe to
share across the fork boundary).

Task-module registration is explicit, four `import modules.<x>.infrastructure.celery.tasks`
statements — no `autodiscover_tasks()` was introduced, per the user's explicit instruction that
this architecture intentionally keeps registration explicit.

Database session handling uses a dedicated engine built via `apps.api.composition.build_engine()`
(the raw, uncached builder — deliberately not the `@lru_cache`-wrapped `get_engine()` FastAPI
uses, since a long-lived worker process should own a session factory independent of FastAPI's
request-scoped one) with `isolation_level="AUTOCOMMIT"` set via `execution_options`. This solves a
real problem the DI-factory contract otherwise leaves open: `Callable[[], Awaitable[X]]` returns a
constructed service with no hook for "commit at the end of the task," and no existing task's
business logic could be changed to add one (spec §11). AUTOCOMMIT makes every individual
repository statement durable immediately at flush time, without any task or service code change.
This was proven under test, not just asserted — see §16.

## 8. Factory Validation

`validate_factory_registry()` runs at the end of `bootstrap_worker()` and raises
`FactoryRegistrationError` — naming every unregistered factory's name, service, and affected task
list in one message — if any of the five required factories did not register. The worker never
reports ready with a partial wiring state; a missing dependency is a startup-time, human-visible
failure, never a silent runtime one deferred to the first real task invocation.

## 9. Scheduled News Task Verification

`sync_scheduled_news_task` (Milestone 10) was re-verified end-to-end through the real production
bootstrap path, not just its existing test-only fixture. With `bootstrap_worker()` run for real
(real env vars, real engine, real factory wiring) and `NEWS_SYNC_ENABLED` confirmed `False` (its
permanent default), invoking the task through Celery's own `.delay()` + eager-execution path
returns `{"enabled": False, "sources_attempted": 0, "articles_sent_to_gemini": 0, ...}` with zero
RSS or Gemini calls made. The task's signature still has no `trigger` parameter — confirmed
unchanged, `LIVE_SCHEDULED` remains the only reachable provenance value for this path, and only a
genuine Celery Beat firing (never this milestone's admin/backfill wiring) can produce it.

## 10. Beat / Worker Separation

No Beat schedule entry was added, removed, or modified this milestone — `beat_schedule.py` is
byte-identical to its Milestone 10 state (confirmed: the file appears in neither `git status` nor
this milestone's diff). Beat remains a pure schedule producer (task name + interval + kwargs, no
service construction, no business logic); the worker built here is the only place a task name
resolves to executable code with real dependencies. This preserves the existing separation exactly.

## 11. Failure & Retry Behavior

Unchanged. Every task's `_RETRY_KWARGS` (`autoretry_for=(Exception,), retry_backoff=True,
retry_backoff_max=300, max_retries=3`) and dead-letter-on-final-failure signal handler are
untouched — this milestone is runtime wiring only, never business-logic or failure-policy changes,
per the spec's explicit exclusion.

## 12. Idempotency

No second idempotency mechanism was introduced. Every task's existing dedup/checkpointing
(`content_hash`+`url` uniqueness for news articles, `IntelligenceSyncCheckpoint` for incremental
sync, etc.) is reused as-is — the worker bootstrap only makes the DI factories that back those
existing mechanisms actually reachable in production; it does not add any new state.

## 13. Observability

`bootstrap_worker()` logs each stage of startup (`worker: starting bootstrap`, `worker:
configuration validated`, `worker: database session factory initialized`, `worker: task modules
imported: ...`, `worker: N/N factories registered`, `worker: factory registry validated`, `worker:
ready`) via the standard `logging` module under the `titaniq.worker` logger name — no print
statements, no secret values logged. `validate_environment()`'s error message names which
environment variables are missing by name, never their values.

## 14. Security Review

No credential, API key, or encryption key value is ever logged, string-formatted, or included in
an exception message anywhere in `bootstrap.py`. `validate_environment()` reports only variable
*names*. The worker-context session factory and every factory closure open a fresh session per
invocation — no shared mutable session, no cross-task state leakage. `FernetCredentialVault`
(already existing, unchanged) is the only credential-touching dependency reachable through the
`admin_context` factory, and its decrypt path is never exercised during bootstrap itself.

## 15. External API Safety

Confirmed no external network call occurs anywhere in `bootstrap_worker()` or any of the five
factory closures at *registration* time — every factory is a lazily-evaluated `async def` closure,
never invoked during bootstrap itself; only `import_task_modules()` and env-var validation run
eagerly, neither of which touches the network. `NEWS_SYNC_ENABLED` was never toggled to `True` at
any point in this milestone's implementation or verification (confirmed via explicit
`monkeypatch.setattr(..., "NEWS_SYNC_ENABLED", False)` in the one test that exercises the task
through a real bootstrap, on top of the setting's own permanent default). No RSS feed, no Gemini
endpoint, and no sports-data provider was contacted during this milestone's work.

## 16. Tests

11 new tests in `tests/unit/apps/test_worker_bootstrap.py`, covering every item from the spec's
testing section:

- **Environment validation** — passes with all three required vars set; fails closed naming every
  missing var; blank-string values treated as missing.
- **Task module registration** — `import_task_modules()` populates `celery_app.tasks` with every
  task name declared in the factory registry. This test caught a real bug during development: the
  registry initially listed `ingestion.sync_odds_for_fixture` / `ingestion.sync_team_statistics_
  for_fixture`, but the real registered task names are `ingestion.sync_odds` / `ingestion.sync_
  team_statistics` — fixed in `bootstrap.py`, not worked around in the test.
- **Factory registry** — starts entirely unregistered; `validate_factory_registry()` fails closed
  with factory/service/affected-task detail when incomplete, passes when complete.
- **The real production bootstrap path (critical item)** —
  `test_bootstrap_worker_runs_the_real_production_path_end_to_end` calls `bootstrap.bootstrap_
  worker()` itself (the same function a real `celery -A apps.worker.bootstrap worker` process
  invokes at startup) against a real throwaway SQLite file, real env vars via `monkeypatch`, and a
  `fakeredis` stand-in — not a hand-assembled test fixture that calls `set_*_factory` manually.
- **AUTOCOMMIT persistence proof** —
  `test_bootstrap_worker_factories_persist_writes_without_an_explicit_commit` writes a
  `ProviderDefinition` through the real `admin_context` factory's service (no explicit `.commit()`
  anywhere in the call chain) and reads it back through a brand-new, independent engine/connection
  against the same file, proving the write is genuinely durable. This test caught a second real
  bug: `get_database_settings()` (like `get_vault_settings()`) is `@lru_cache`-decorated, so
  without an explicit `cache_clear()` in the test fixture, a later test's `build_engine()` call
  silently reused an earlier test's stale `TITANIQ_DB_URL` — fixed in the test fixture, not in
  production code (a real single-process worker's env vars are fixed for its whole lifetime, so
  this caching is correct in production; it only needed clearing for test isolation).
- **Fail-closed on missing configuration** — `bootstrap_worker()` raises `WorkerConfigurationError`
  before any factory registers when required env vars are absent.
- **Scheduled news task after a real bootstrap** — invokes the real Celery task via `.delay()`
  under `task_always_eager=True` (matching the existing Milestone 10 test convention) after a real
  bootstrap, confirming `NEWS_SYNC_ENABLED=False` still yields zero external calls even when the
  factory chain is fully real rather than faked.

## 17. Regression Testing vs. Milestone 10 Baseline

- Targeted regression (`tests/unit/apps/`, `modules/intelligence`, `modules/ingestion`,
  `modules/predictions`, `modules/admin`): **1626 passed, 0 failed.**
- Full suite: **2107 passed, 58 skipped, 0 failed** — Milestone 10 baseline was 2096 passed, 58
  skipped, 0 failed. Delta is exactly +11 (the new bootstrap tests), skip count unchanged, zero
  failures, zero tests modified to hide a regression.

## 18. Database Safety

No migration was written or applied. `apps/worker/bootstrap.py` is pure application/runtime wiring
— it constructs sessions and engines but defines no schema and issues no DDL. `git status`
confirms no `alembic/versions/` file was touched by this milestone. `dev.db` was not opened,
modified, or migrated at any point during this milestone's implementation or verification; every
test in `test_worker_bootstrap.py` uses a throwaway `tmp_path`-scoped SQLite file, never `dev.db`.

## 19. Files Changed

None — `apps/api/composition.py`'s only uncommitted diff predates this milestone (Milestone 9/10's
`build_football_market_seeder` fix and `build_scheduled_news_sync_service` addition); this
milestone reads from it but adds no new lines to it.

## 20. Files Created

- `apps/worker/bootstrap.py` — the production Celery worker composition root.
- `tests/unit/apps/test_worker_bootstrap.py` — 11 tests covering the full bootstrap contract.
- `docs/milestone11_verification_report.md` — this report.

## 21. Known Limitations

- `apps/scheduler/` remains an empty placeholder package — out of scope for this milestone (Beat
  itself already runs via the existing `celery -A modules.ingestion.infrastructure.celery.
  celery_app beat` entry point; no separate scheduler process was ever part of this milestone's
  brief).
- This milestone did not attempt to run an actual forked `celery worker` process end-to-end (e.g.
  via a subprocess integration test) — verification is at the `bootstrap_worker()` function level,
  which is the same code path a real worker's `worker_process_init` signal invokes, but a live
  multi-process smoke test was judged out of scope and unnecessary risk (would require a running
  Redis broker and real worker process during automated verification).
- `NEWS_SYNC_ENABLED` remains `False` in every environment by design; enabling real scheduled news
  ingestion in any environment remains a deliberate, separate operational decision, not something
  this or any prior milestone has done.

## 22. Recommended Next Milestone

With the worker now able to actually execute every existing task in production, a reasonable next
step is a controlled, observed dry run: start a real worker process (`celery -A apps.worker.
bootstrap worker`) plus Beat against a disposable environment, confirm the existing ingestion/
admin/predictions tasks fire and complete successfully end-to-end, and only after that is confirmed
stable, consider the deliberate, separately-approved step of flipping `NEWS_SYNC_ENABLED` on in a
non-production environment to observe real (rate-limited, budget-capped) scheduled news ingestion
for the first time.

---

**MILESTONE 11 IMPLEMENTATION COMPLETE.** Per the governing rule, this stops here — Milestone 12 is
not started automatically. Waiting for explicit approval before proceeding.
