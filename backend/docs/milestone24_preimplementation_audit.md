# Milestone 24 — Preimplementation Read-Only Audit (FINAL MILESTONE)

**Status: READ-ONLY.** No code, schema, database row, or environment variable modified. No process
started (no worker, no Beat). No external call made (no RSS, no Gemini, no sports provider).

## 1. Current project state

Continuing directly from M23's STATE A close. All findings below re-verified fresh, this session,
not reused from memory.

**Database** (`backend/dev.db`, unchanged since M23 ended):

| Table | Count |
|---|---|
| fixtures | 6,834 (380 scheduled, 6,444 completed) |
| news_articles | 319 |
| news_events | 68 (0 `VERIFIED_PRE_MATCH`, all `UNKNOWN_AVAILABILITY_TIME`) |
| intelligence_sync_runs | 39 |
| intelligence_sync_checkpoints | 8 |
| transfers | 308 (0 `VERIFIED_PRE_MATCH`) |
| lineups | 4 (0 `VERIFIED_PRE_MATCH`) |
| injuries | 30 (0 `VERIFIED_PRE_MATCH`) |
| datasets | 0 |
| models | 47 (19 champion) |
| feature_values_offline | 71,223 |
| predictions | 12,436 |
| prediction_outcomes | 11,194 |
| calibration_reports | 0 |

**Training preflight**: 0/14 football markets READY (last run: end of M23, no DB change since —
re-running would reproduce the identical result; not re-run here since Phase 0 is read-only and
nothing that could change the outcome has happened).

**Fixture calendar**: earliest `scheduled` fixture is `2026-08-21 19:00:00 UTC` — **~7.4 days from
now** (`now` = `2026-08-14T01:19:23Z`). Zero fixtures fall within the 90-minute lineup-sync window or
the 168-hour (7-day) news-sync window. This is unchanged from M23 and is the single dominant fact
governing this milestone's realistic scope — it is a calendar fact, not a code defect.

**Runtime services**: frontend, backend, and the dev-only fake-Redis process have all stopped since
M23 ended (none listening on 5173/8000/6379). No Celery worker or Beat process is running. This is
expected — nothing was left running deliberately at the end of M23.

**Git status** (repo root): 3 modified files, all from M21's explicitly-authorized fixes —
`backend/modules/ingestion/infrastructure/celery/celery_app.py` (Beat schedule wiring),
`backend/pyproject.toml` (`lupa` dependency), `backend/tests/unit/modules/ingestion/test_beat_schedule.py`
(test import fix). Untracked: `backend/celerybeat-schedule*` (Beat's local state file — not yet
gitignored), and this session's milestone 21-23 reports. No unexpected or unauthorized change exists
in the working tree.

## 2. Celery / queue architecture (re-confirmed, unmodified)

- Single shared Celery app (`titaniq_ingestion`), one production composition root
  (`apps/worker/bootstrap.py`) — no duplicate app, no autodiscovery, confirmed by source reading.
- `task_routes` (`celery_app.py`): `ingestion.sync_live_fixtures`→`live`, `ingestion.*`→`default`,
  `admin.*`→`default`. `intelligence.*` and `predictions.*` have no explicit route → fall to Celery's
  default queue name, `celery`.
- The worker's queue consumption is currently **launch-parameter-only**: `-Q celery,live,default`
  was proven to work live in M23 but is **not hardcoded anywhere in the codebase** — a worker started
  without that flag reverts to consuming only `celery`, silently stranding every `ingestion.*`/
  `admin.*` task. This is the queue-routing defect M22 found and M23 fixed *for one session*, not
  permanently.
- `bootstrap_worker()`: 5 factories, 4 task modules, fail-closed registry validation — unmodified,
  confirmed correct in every prior milestone's live test.
- Beat: `BEAT_SCHEDULE` (21 entries) is correctly wired into `celery_app.conf.beat_schedule` (M21 fix,
  confirmed persistent). **No code-level protection exists against the M22 stale-schedule incident** —
  if Beat's local `celerybeat-schedule` file has last-run timestamps older than a task's interval, that
  task fires immediately on Beat's first tick, including `predictions.check_scheduled_calibration`/
  `check_scheduled_retraining`. This is purely an operational/procedural risk today (avoided in M23 by
  simply never starting Beat), not something the code itself guards against.

## 3. Database connection-leak finding — corrected scope from M23

M23's report scoped this to `ingestion.sync_upcoming_structured_intelligence` alone, because that is
the task whose completion coincided with the observed `RuntimeError: Event loop is closed` traceback
burst. Re-reading the codebase now (read-only) shows this scoping was too narrow:

**Every Celery task in the project uses the same `asyncio.run(_do())` pattern** — confirmed by direct
grep: 11 tasks in `modules/ingestion/infrastructure/celery/tasks.py`, 1 in
`modules/intelligence/infrastructure/celery/tasks.py` (`sync_scheduled_news`), 2 in
`modules/predictions/infrastructure/celery/tasks.py` (`check_scheduled_calibration`,
`check_scheduled_retraining`), 1 in `modules/admin/infrastructure/celery/tasks.py`
(`check_all_provider_health`) — 15 of 15 tasks, no exception.

The worker builds **one shared async engine per worker process** (`_build_worker_session_factory()`
in `apps/worker/bootstrap.py`, called once at `worker_process_init`), but each task tears down its own
event loop via `asyncio.run()` on every invocation. If a task's session/connection isn't fully closed
before that loop exits, Python's garbage collector later finds an orphaned aiosqlite connection tied to
a now-closed loop and logs the warning burst observed in M23. Because the GC sweep that surfaced this
happened after *many* different tasks had already run (multiple `sync_live_fixtures`,
`sync_completed_fixtures`, `sync_standings`, `admin.check_all_provider_health`,
`sync_upcoming_fixtures`, `sync_scheduled_news`, and `sync_upcoming_structured_intelligence` had all
executed by that point), **it cannot be confirmed from that single observation which specific task(s)
actually leaked** — the burst is consistent with several of them leaking, not necessarily all, and not
necessarily only the one whose completion the log line happened to be adjacent to.

**Honest assessment**: this is a real, likely-systemic pattern risk (not a proven leak in all 15 tasks
individually), non-fatal in every observation so far (the worker process itself never crashed, and
every task's actual database read/write completed correctly before any leak occurred — this is a
resource-cleanup defect, not a data-correctness one). SQLite is more tolerant of this than a
connection-limited server database would be, but it is still real technical debt in a
soon-to-be-final-milestone codebase.

## 4. Feature coverage / provenance (re-confirmed, unchanged)

All four gated-observation sources remain at exactly 0% `VERIFIED_PRE_MATCH`: `news_events` (68/68
`UNKNOWN_AVAILABILITY_TIME`), `lineups` (4/4), `transfers` (308/308), `injuries` (30/30). Every one of
the 14 genuinely-trained football markets fails identically on `training_inference_feature_parity` and
`required_feature_coverage_acceptable` for the same gated keys (`{home,away}_lineup_continuity`,
`{home,away}_transfer_activity`, plus 2 news-impact keys on 12/14 markets) — unchanged since M19.
`HistoricalEntityResolutionService`/`HistoricalNewsRelevanceEngine`/`HistoricalFeatureReconstructionService`
remain correctly gated (never substitute current roster/news for historical). `TrainingSample.reference_time`
and the M18 chronological-sort/fail-closed split logic remain intact and unmodified.

## 5. Blockers, ranked

1. **No fixture within any accumulation window** (~7.4 days until the earliest one). This is the
   dominant, calendar-driven blocker. No code change addresses it.
2. **Queue-routing fix is not persisted in code** — a future worker launch without `-Q celery,live,default`
   silently reverts to the M22 bug. This blocks *unattended* accumulation, though a manually-launched,
   correctly-flagged worker (as M23 did) still works.
3. **Beat stale-schedule risk remains procedurally, not structurally, mitigated.** Starting Beat today,
   with `celerybeat-schedule`'s current state (last real tick was M23's brief run), would very likely
   re-fire `predictions.check_scheduled_calibration` immediately (1-hour interval, already elapsed) and
   possibly `check_scheduled_retraining` (6-hour interval — need to check elapsed time at execution).
4. **Systemic connection-cleanup pattern risk** (§3) — non-fatal so far, real technical debt.
5. **`alembic_version` still missing** (carried from M22, unrelated to training, still unfixed).
6. **One pre-existing frontend test failure** (carried from M22, unrelated, still unfixed).

## 6. Proposed implementation plan (for approval — nothing below has been executed)

**M24 Phase 1 (Operational Hardening)** — scoped narrowly to blockers 2-4 above, since blocker 1 is
uncodeable and blockers 5-6 are unrelated to this milestone's mission:

- **(a) Persist the queue-routing fix in code.** Smallest correct change: add
  `worker_direct=False` is irrelevant; the actual smallest fix is either (i) setting
  `task_default_queue`/additional queue declarations via `celery_app.conf.update(...)` so a default
  `-A apps.worker.bootstrap worker` invocation (no `-Q` needed) naturally consumes `celery`, `live`,
  and `default`, or (ii) documenting the `-Q celery,live,default` flag as a mandatory, permanent part
  of the production start command (e.g., in `apps/worker/bootstrap.py`'s own docstring / a startup
  script) without changing Celery's own queue-consumption defaults. Option (i) is more robust
  (protects against a future operator forgetting the flag); option (ii) is lower-risk (zero Celery
  config semantics change). **Recommend (i)**, since Celery natively supports declaring a worker's
  queue list via `conf.update(...)` and this doesn't touch `task_routes` or any task's business logic
  — but this is a real config decision this audit is surfacing for approval, not deciding unilaterally.
- **(b) Investigate the connection-cleanup pattern precisely** (not blindly rewrite all 15 tasks).
  Read each task's actual session-close path; confirm whether `_get_orchestrator()`'s underlying
  session factory usage properly uses a context manager (`async with session_factory() as session:`)
  or relies on GC. If a real, narrow fix exists (e.g., an explicit `await session.close()` before
  `asyncio.run()`'s function returns, or wrapping the factory access in `async with`), apply it
  identically across all 15 tasks' shared helper pattern if one exists, or task-by-task if each has
  bespoke plumbing. **This is the only place this milestone would touch task code**, and only after
  explicit approval of the specific diff.
- **(c) Beat stale-schedule handling**: the master prompt's own principle is "Beat must remain separate
  from business logic" and "stale Beat schedules must never cause protected operations... to execute
  unexpectedly." Given M23 already established the working mitigation (**never start Beat; dispatch
  the specific accumulation tasks explicitly, worker-only**), and building a code-level stale-schedule
  guard (e.g., a custom scheduler class, or a startup check that resets/inspects
  `celerybeat-schedule`'s last-run timestamps before allowing Beat to tick) is a nontrivial, real
  Celery-architecture change the master prompt explicitly discourages ("do not redesign the Celery
  architecture" — M23's own constraint, still the most conservative reading of M24's "Celery
  architecture" principles section) — **recommend NOT building new Beat-safety code this milestone**,
  and continuing the proven-safe M23 pattern (worker-only, explicit dispatch, no Beat) for Phase 2 if
  approved. This keeps scope minimal and doesn't risk introducing a new, untested safety mechanism in
  the project's final milestone.

**M24 Phase 2 (Live Accumulation)** — if approved separately, would repeat M23's exact proven pattern:
worker-only (no Beat), `-Q celery,live,default`, explicit dispatch of
`ingestion.sync_upcoming_structured_intelligence` and `intelligence.sync_scheduled_news` only, safety-net
monitor watching for calibration/retraining task names throughout, full audit trail. **Given the
fixture-calendar fact (§1), this would almost certainly reproduce M23's exact result — zero new
`VERIFIED_PRE_MATCH` observations** — since nothing has changed in the underlying data since M23 ran
this same check hours ago. Re-running it today would mostly just re-fetch the same news articles
(possibly a few new ones from elapsed real-world time) and re-confirm zero structured-intelligence
eligibility. Worth doing briefly if approved, but expectations should be set honestly: this will very
likely still end at **STATE A** (per M24's own definitions) or **STATE B** (training blocked), not C
or D, because the calendar blocker (§5 item 1) cannot be resolved within a single session.

**M24 Phases 3-6 (Data Monitoring, Training, Validation, Promotion)**: contingent entirely on Phase 2
producing genuine new `VERIFIED_PRE_MATCH` observations, which — per the fixture-calendar fact — this
audit assesses as **very unlikely to happen today**. These phases would only proceed if Phase 2's real
results surprise this expectation (e.g., if this session's earlier M23 news-sync happened to catch a
fixture just entering the news window — re-checking is cheap and honest, not assumed).

## 7. External API impact if Phase 2 is approved

Same as M23: 8 RSS fetch attempts (real HTTP), 0 Gemini calls expected (relevance filter will very
likely again find nothing eligible, per §1's calendar fact), 0 sports-provider calls this time (Phase
2 as scoped here would NOT touch the `live`/`default` backlog again — that backlog was fully
disclosed and is understood; M24 should dispatch only the two specific accumulation tasks directly,
not start a queue-draining worker sweep, to keep external call volume minimal and intentional).

## 8. Database impact if Phase 1(b) (connection-leak fix) is approved

None to production data — a fix to task-level Python code (session/connection lifecycle), not to any
schema, migration, or row. If Phase 2 is also approved: `news_articles`/`intelligence_sync_runs`/
`intelligence_sync_checkpoints` may grow (same pattern as M21/M23); no other table expected to change,
per the calendar fact.

## 9. Expected training path

Given §1's calendar fact, the honest expectation is that this milestone likely ends at **STATE A**
(live accumulation infrastructure hardened and re-verified, but insufficient data — same substantive
outcome as M23) or **STATE B** (training evaluated, gates fail) if a training-authorization check is
run for completeness. **STATE C (Challenger trained) or STATE D (Champion promoted) would require a
genuine surprise in Phase 2's real results** — this audit will not manufacture that outcome and
recommends the user set that expectation now, before any further work proceeds.

---

**STOP — awaiting explicit approval before any implementation, per M24's explicit protocol.**
Nothing in §6/§7/§8 has been executed. No code changed. No process started. No external call made.
