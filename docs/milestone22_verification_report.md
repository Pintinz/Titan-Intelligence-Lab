# Milestone 22 Verification Report — Runtime Recovery, Full-Stack Health Audit & Service Restoration

**Date:** 2026-08-14
**Final status: STATE B — PARTIAL RECOVERY**

```
FRONTEND:          RUNNING (http://localhost:5173)
BACKEND:           RUNNING (http://localhost:8000)
REDIS:             RUNNING (fake-redis, 127.0.0.1:6379, reused from prior session)
DATABASE:          REACHABLE, ALL DATA INTACT
CELERY WORKER:     DEMONSTRATED WORKING, then STOPPED (deliberate safety decision)
CELERY BEAT:       DEMONSTRATED WORKING, then STOPPED (deliberate safety decision)
NEWS_SYNC_ENABLED: still `true` in .env (untouched, not this milestone's scope to edit);
                    overridden to false at the process level for every service started tonight
NEWS_BACKFILL_ENABLED: false (untouched)
EXTERNAL CALLS:    NONE (RSS/Gemini) during this milestone
DB WRITES:         NONE outside two self-contained, harmless, already-verified task executions
```

## 1. Executive summary

The user's report that "frontend and backend appear down" was correct but had a simple cause: **neither had ever been started this session** — no regression, no crash, nothing caused by Milestone 21. A full read-only audit (Phases 1–8) found the database, Redis, and Celery wiring all healthy and exactly where M21 left them. Backend and frontend were then started using the repository's own existing mechanisms and verified to communicate correctly end-to-end with real data.

While bringing Celery worker + Beat up to complete the acceptance checklist, a live Beat process's very first tick fired the *entire* schedule at once (its persisted state was stale from being stopped last session, making everything look overdue). One of those tasks — `predictions.check_scheduled_calibration` — is explicitly forbidden from running by this milestone's Phase 13 ("Do not recalibrate"). It had already completed by the time this was noticed. Investigation confirmed it caused zero effect (0/37 markets had enough samples to fit; `calibration_reports` stayed at 0 rows). Both Celery processes were stopped immediately afterward as a deliberate safety decision, documented fully in §9 and §21 below — they are **not** left running as part of this milestone's final state.

One new, real, and previously-unknown defect was found and is reported without being fixed: the **`alembic_version` bookkeeping table does not exist** in `dev.db`, even though the schema (89 tables) and all data are current and correct. This does not affect application runtime today, but would break a future `alembic upgrade` attempt.

## 2. Runtime architecture

```
Frontend (Vite, :5173) ──HTTP──> Backend (FastAPI, :8000) ──> Database (SQLite, backend/dev.db)
                                          │
                                          └──> Redis (fakeredis, :6379)

Celery Worker ──> Redis (broker/backend) ──> Database (own session factory, AUTOCOMMIT)
Celery Beat   ──> Redis (broker)         ──> dispatches to Worker via registered task names
```

## 3. Initial service status (before any action, Phase 1)

| Component | Status | Evidence |
|---|---|---|
| Frontend | STOPPED | no `node.exe` process; port 5173 not listening |
| Backend | STOPPED | no matching python process; port 8000 not listening |
| Redis | RUNNING | `fakeredis` process (PID 18340) still listening on 6379, left over from the prior session |
| Database | REACHABLE | `backend/dev.db`, 89 tables, all data intact |
| Celery Worker | STOPPED | stopped cleanly at the end of the prior session |
| Celery Beat | STOPPED | stopped cleanly at the end of the prior session |

DO NOT ASSUME THIS IS CAUSED BY M21 — confirmed correct: nothing about the M21 changes (Beat schedule wiring, `lupa`) touches frontend or backend startup at all, and both were simply never launched.

## 4. Frontend diagnosis

- Package manager: npm. Framework: Vite 8 + React 19 + TypeScript.
- `frontend/node_modules` present — dependencies already installed, no install needed.
- Existing startup mechanism found in `.claude/launch.json`: a `titaniq-frontend` configuration (`npm --prefix frontend run dev`, port 5173) — this is the canonical, repository-defined way to start it.
- `frontend/.env.local` correctly points `VITE_API_BASE_URL=http://localhost:8000` at the backend.
- No configuration or runtime defect found. It was simply not running.

## 5. Backend diagnosis

- Entry point: `backend/apps/api/main.py`, FastAPI app object named `app` (`FastAPI(title="TitanIQ API", ...)`).
- Canonical start command (standard FastAPI/uvicorn convention, confirmed by the module's own `app` binding): `uvicorn apps.api.main:app --port 8000`, run from `backend/`.
- Import-time check (`python -c "import apps.api.main"`) succeeded cleanly before ever starting a live server — no import error, no missing dependency.
- Required env vars (`TITANIQ_DB_URL`, `TITANIQ_REDIS_URL`, `TITANIQ_ENCRYPTION_KEY`, `TITANIQ_SUPABASE_PROJECT_URL`) are documented in `backend/.env`; **`.env` is not auto-loaded by the app** (confirmed in a prior session — no `load_dotenv()` anywhere), so they must be exported before starting any process, which is what this recovery did.
- No configuration or runtime defect found. It was simply not running.

## 6. Redis diagnosis

- `scripts/run_local_fake_redis.py` (`fakeredis.TcpFakeServer`) was already running from the prior session (PID 18340), listening on `127.0.0.1:6379`. `PING` returned `True`.
- `lupa` (installed last session to fix Lua/`EVALSHA` support) is present and working — confirmed indirectly by the Celery worker connecting and completing `mingle` without the `unknown command 'evalsha'` error seen before that fix.
- No real Redis install exists on this machine (documented, pre-existing constraint) — this dev-only stand-in remains the correct, working substitute.

## 7. Database diagnosis

- `backend/dev.db`: 89 tables, all present, all data intact — row counts identical to where M21 left them (fixtures 6,834; teams 215; players 100; transfers 308; news_sources 8; news_articles 277; news_events 68; intelligence_sync_runs 31; intelligence_sync_checkpoints 8; feature_values_offline 68,223; datasets 0; models 47, 19 champion; predictions 12,436).
- Note: a **separate, empty (0-byte), stale `dev.db` file exists at the repo root** (`C:\...\TitanIQ\dev.db`, last modified 8/10). This is inert — `TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db` resolves relative to the process's working directory, and every backend/worker/beat process in this project is always started from `backend/`, so this file is never touched. Not a defect, just worth knowing it's there so nobody mistakes it for the real database.
- **New finding: `alembic_version` table does not exist.** `alembic current` returns nothing (no error, genuinely no stamped revision), while `alembic heads` correctly reports `0041`. Directly querying `sqlite_master` confirms no `alembic_version` table at all — yet the schema itself matches migration `0041`'s cumulative state exactly, and all 89 tables + all data are present and correct. This means the live `dev.db` was never migrated via Alembic's own tracked path (most likely created directly via `Base.metadata.create_all()` early in the project, consistent with this codebase's documented "fast local SQLite" dev pattern) — the schema is current, but Alembic itself doesn't know that. **Consequence:** running `alembic upgrade head` against this exact file today would likely fail with "table already exists" errors, since Alembic would try to apply every migration from scratch. **Not fixed** — Phase 8 is explicitly read-only ("DO NOT MODIFY ANY ROW"), and stamping a version is a real, deliberate action outside this milestone's scope. Reported for a future, explicitly-authorized fix (`alembic stamp head` is the standard remedy, once someone confirms the schema genuinely matches 0041 — which this audit's table-count/data cross-check supports but does not prove field-by-field).

## 8. Celery worker diagnosis

Verified via direct, read-only import (`bootstrap_worker()` called in-process) before ever starting a live process:
- 5/5 factories registered (`orchestrator`, `admin_context`, `retraining_orchestrator`, `calibration_service`, `scheduled_news_sync`).
- 4/4 task modules imported.
- 15/15 expected task names present in `celery_app.tasks`.
- Redis connection succeeds.

Then verified live: `celery -A apps.worker.bootstrap worker --loglevel=info --pool=solo` started cleanly, reached `celery@AutotecHUB ready.`, held stable with no errors. Confirms the `lupa` fix from the prior session persists correctly.

## 9. Celery Beat diagnosis

`celery_app.conf.beat_schedule` inspected directly: **21 entries loaded** — confirms the prior session's schedule-wiring fix (`beat_schedule=BEAT_SCHEDULE` in `celery_app.py`) persists correctly.

Started live (`celery -A apps.worker.bootstrap beat --loglevel=debug`) to confirm it starts and sees the expected schedule. **What happened next was not anticipated and is reported in full:**

Because the `celerybeat-schedule` persistence file was stale (Beat's own last-run bookkeeping, left over from being stopped last session), Beat's very first tick treated almost every entry as overdue and dispatched the *entire* schedule within milliseconds of starting — including `predictions.check_scheduled_calibration`, which Phase 13 of this milestone's own instructions explicitly forbids ("Do not recalibrate").

By the time this was noticed (a few seconds later), the task had already run to completion via the worker (which was also running, started moments earlier to verify Phase 6). **Investigated immediately:**
- Task result: `{'markets_checked': 37, 'fitted': 0, 'skipped': 37, ...}` — every market was skipped with `'reason': 'fewer than 20 usable outcome samples'`. Nothing was fitted.
- Verified directly against the database: `calibration_reports` = 0 rows (unchanged), `models` = 47 (unchanged), champion count = 19 (unchanged), `datasets` = 0, `training_runs` = 0. **Zero actual effect.**
- `intelligence.sync_scheduled_news` also fired in the same tick — result confirmed `'enabled': False`, 0 sources/articles/Gemini-calls — this task no-op'd correctly, proving the explicit process-level `TITANIQ_NEWS_SYNC_ENABLED=false` override (used instead of editing `.env`, per Phase 1's "do not modify environment variables") worked exactly as intended even though `.env` itself still says `true`.
- Every `ingestion.*` and `admin.*` task also "sent" by that same tick was **never actually consumed** by the worker — see §12 (Queue-Routing Analysis) — so none of those executed at all. No external RSS/API calls occurred from any of them.

**Both processes were stopped immediately** (within the same minute) once this was understood, as a deliberate decision: leaving a live Beat+Worker pairing running for the remainder of this audit risked `predictions.check_scheduled_retraining` (6-hour interval, not due this time — did not fire) firing later with less oversight. This is documented in full in §21.

**Net result: Beat and Worker are both confirmed to start correctly, load the correct schedule, and dispatch/consume tasks correctly. Neither is left running at the end of this milestone**, and the one real-world task execution that occurred had zero effect on any protected table.

## 10. Factory registry status

5/5: `orchestrator`, `admin_context`, `retraining_orchestrator`, `calibration_service`, `scheduled_news_sync` — all registered, confirmed both via static import and via the live worker's own startup log (`worker: 5/5 factories registered`).

## 11. Task registration status

15/15 expected task names present in `celery_app.tasks`, confirmed both statically and in the live worker's `[tasks]` startup banner:
`admin.check_all_provider_health`, `ingestion.sync_completed_fixtures`, `ingestion.sync_countries`, `ingestion.sync_fixtures`, `ingestion.sync_live_fixtures`, `ingestion.sync_odds`, `ingestion.sync_standings`, `ingestion.sync_standings_alt`, `ingestion.sync_team_statistics`, `ingestion.sync_teams`, `ingestion.sync_upcoming_fixtures`, `ingestion.sync_upcoming_structured_intelligence`, `intelligence.sync_scheduled_news`, `predictions.check_scheduled_calibration`, `predictions.check_scheduled_retraining`.

## 12. Queue-routing analysis (Phase 11 — known M21 defect, re-confirmed live)

`celery_app.conf.task_routes`:
```python
{'ingestion.sync_live_fixtures': {'queue': 'live'},
 'ingestion.*': {'queue': 'default'},
 'admin.*': {'queue': 'default'}}
```
The worker, started with no `-Q` flag, only declares/consumes the built-in `celery` queue (confirmed from its own startup banner: `[queues] .> celery exchange=celery(direct) key=celery` — nothing else).

**QUEUE ROUTING FINDING:**
- **Affected tasks:** every `ingestion.*` task (11 of them) and `admin.check_all_provider_health`.
- **Declared/routed queue:** `live` (for `sync_live_fixtures`) or `default` (all others in that group).
- **Worker-consumed queue:** `celery` only.
- **Consequence:** these tasks are dispatched by Beat but never picked up — they accumulate unconsumed in Redis (confirmed live tonight: the `live` queue grew with every 30s tick) and never execute. This is silently non-fatal (no error, no crash) but means real ingestion/health-check sync never actually happens under the current default worker invocation.
- **Tasks NOT affected** (no explicit route → fall through to Celery's default queue name, `celery`, which the worker does consume): `intelligence.sync_scheduled_news`, `predictions.check_scheduled_calibration`, `predictions.check_scheduled_retraining`. **This is the important, newly-reinforced part of this finding**: these three tasks — including the retraining-check task — bypass the routing gap entirely and *will* execute on any live Beat+Worker pairing, exactly as tonight's incident demonstrated for the calibration one.
- **Proposed minimal fix (not applied — requires separate authorization):** either start the worker with `-Q celery,live,default` to consume its own routed queues, or remove/rework `task_routes` if per-queue separation was never actually intended. Small, mechanical, but a real behavior change requiring a decision about intended architecture — not made unilaterally here.

## 13. Dependency graph — where the runtime chain was actually broken

```
Frontend  ✗ STOPPED  → Backend
Backend   ✗ STOPPED  → Database (DB itself: ✓ healthy)
Backend   (would have been) → Redis (Redis itself: ✓ healthy, was already running)
Celery Worker ✗ STOPPED → Redis (✓) → Database (✓)
Celery Beat   ✗ STOPPED → Redis (✓) → Celery Worker
```
The break was entirely "nothing was started" — every downstream dependency (DB, Redis) was already healthy and waiting.

## 14. Recovery actions taken

1. Started backend: `uvicorn apps.api.main:app --port 8000` (from `backend/`, required env vars exported). Confirmed `Application startup complete.`
2. Started frontend: via the repository's own `.claude/launch.json` `titaniq-frontend` configuration (`npm --prefix frontend run dev`, port 5173). Confirmed `VITE ready`.
3. Started Celery worker and Beat to complete Phase 6/7/9 verification (env vars exported explicitly per-process, `TITANIQ_NEWS_SYNC_ENABLED=false` for this launch, `.env` itself untouched). Both stopped again shortly after, per §9/§21.
4. No code, schema, migration, config file (`.env`, Docker, deployment config), or database row was modified during recovery. The only files changed in this milestone are this report and (transient, gitignored) `celerybeat-schedule*` state files.

## 15. Connectivity verification (Phase 10)

- **Frontend → Backend:** confirmed live in-browser. Landing page loaded real data via `GET /api/v1/public/featured-intelligence`, `/news-intelligence`, `/knowledge-graph-preview`, `/platform-summary` — all `200 OK`, including CORS preflight `OPTIONS` requests. Zero console errors.
- **Backend → Database:** confirmed by the same requests returning real, DB-backed content, and independently via direct read-only queries.
- **Backend → Redis:** confirmed via `bootstrap_worker()`'s Redis connection succeeding (backend and worker share the same `TITANIQ_REDIS_URL`) and a direct `PING`.
- **Celery Worker → Redis:** confirmed (`Connected to redis://127.0.0.1:6379/0`, `mingle` succeeded).
- **Celery Worker → Database:** confirmed via `check_scheduled_calibration` successfully reading `models`/prediction-outcome data to evaluate 37 markets (a real DB read, even though it wrote nothing).
- **Celery Beat → Redis:** confirmed (schedule persistence file written, tasks dispatched to the broker).
- **Celery Beat → Registered tasks:** confirmed (Beat dispatched by the exact registered task names; the worker's task registry matched).

## 16. External API safety verification

- **Zero RSS calls** occurred during this milestone (the one `sync_scheduled_news` execution correctly no-op'd before making any HTTP request, confirmed by `sources_attempted: 0`).
- **Zero Gemini calls** occurred (same reason).
- No sports-data provider (API-Football, football-data.org, etc.) was called — every `ingestion.*` task that Beat dispatched was never consumed by the worker (§12), so none of their HTTP calls happened.
- `admin.check_all_provider_health` was dispatched but, same as above, never consumed — no provider health checks actually ran.

## 17. Database integrity verification

Full before/after comparison across every table listed in the milestone's Phase 8/15 requirements — identical in every case except the two harmless, already-analyzed writes from `intelligence_sync_runs`/`intelligence_sync_checkpoints` growth in the *prior* session (M21), which this session's baseline already reflects:

| Table | Value (unchanged throughout M22) |
|---|---|
| fixtures | 6,834 |
| teams | 215 |
| players | 100 |
| transfers | 308 |
| news_sources | 8 |
| news_articles | 277 |
| news_events | 68 |
| feature_values_offline | 68,223 |
| datasets | 0 |
| models | 47 (19 champion) |
| predictions | 12,436 |
| calibration_reports | 0 |
| training_runs | 0 |

**No row was modified during this milestone.**

## 18. Test results (Phase 14)

- Targeted: `tests/unit/apps/test_worker_bootstrap.py` + `tests/unit/modules/ingestion/test_beat_schedule.py` — **17 passed**.
- Full backend suite: **2,227 passed, 58 skipped, 0 failed** — identical to the M21 baseline, zero regressions.
- Frontend suite (`npm run test`, vitest): **75 passed, 1 failed** (`insights-page.test.tsx`, "pins a team from search and shows its Mission Brief coverage" — a `findByText('Arsenal')` timeout after typing into the search box). Confirmed this is **pre-existing and unrelated**: `git status` shows zero frontend file changes this entire session (M21 or M22 never touched any frontend code), and the failure reproduces identically in isolation (not a batch-order flake). Not fixed — out of this milestone's scope, and Phase 14 explicitly says "Do not modify tests merely to accommodate failures." Root cause not deeply investigated (would require frontend application debugging, a different kind of work than infrastructure recovery); flagging for a future frontend-focused session.

## 19. Remaining blockers

1. **Queue-routing gap** (§12) — `ingestion.*`/`admin.*` tasks never actually run under the current default worker invocation. Fix requires an explicit architecture decision (add `-Q` flags vs. rework `task_routes`), not made here.
2. **`alembic_version` table missing** (§7) — schema is current but untracked; a future `alembic upgrade` would break against this file. Needs `alembic stamp head` (or equivalent), not applied here (Phase 8 read-only).
3. **One pre-existing frontend test failure** (§18) — `insights-page.test.tsx`'s team-search-and-pin flow. Unrelated to infrastructure, needs frontend investigation.
4. **Celery worker/Beat are not currently running** — deliberately stopped after the calibration-task incident (§9). Restoring live scheduled execution requires either fixing the queue-routing gap first (so the intended tasks actually run) and/or deciding how to handle `predictions.check_scheduled_retraining`'s exposure the same way `check_scheduled_calibration` was exposed tonight, before leaving Beat running unattended again.

## 20. Recommended M23 scope

Not started, per explicit instruction. Candidates a future milestone should consider (not decided or authorized here): (a) fix the queue-routing gap with an explicit, authorized decision on intended architecture; (b) stamp `alembic_version` to `0041` after independently confirming schema/migration parity; (c) investigate the frontend `insights-page.test.tsx` failure; (d) decide on a policy for `predictions.check_scheduled_retraining`'s exposure before ever running Beat unattended (e.g., a feature flag, a dry-run mode, or accepting the current "0 usable samples" natural gate as sufficient, matching tonight's calibration outcome).

## 21. Failure handling record (Phase 21-equivalent)

The `check_scheduled_calibration` firing was a genuine miss in this milestone's own execution — Phase 9's explicit gate was `NEWS_SYNC_ENABLED must remain false`, and that was honored correctly, but starting a live Beat process to "verify it starts and sees the schedule" (per Phase 7's instructions) was not recognized in advance as also exposing every *other* scheduled task, including the recalibration one Phase 13 explicitly forbids. This was caught within roughly a minute (via a system log-tail notification, not proactive foresight), investigated immediately and fully, confirmed to have zero real effect, and both processes were stopped. Reported here in full rather than omitted, per the standing "do not patch around or hide problems" practice this project has followed throughout M21.

## 22. Final acceptance matrix

```
[x] Frontend starts successfully.
[x] Backend API starts successfully.
[x] Frontend can communicate with backend.
[x] Database is reachable.
[x] Redis is reachable.
[x] Celery worker starts successfully.
[x] Factory registry validates 5/5.
[x] All 4 task modules register successfully.
[x] Celery Beat starts successfully.
[x] BEAT_SCHEDULE is loaded.
[x] Worker remains stable (while running — confirmed no crash; not left running, see §9/§21).
[x] Beat remains stable (while running — confirmed no crash; not left running, see §9/§21).
[x] NEWS_SYNC_ENABLED remains false unless separately authorized (process-level override held for every service started tonight; .env itself untouched).
[x] NEWS_BACKFILL_ENABLED remains false.
[x] No external RSS calls occurred during recovery.
[x] No Gemini calls occurred during recovery.
[x] No database writes occurred during the read-only audit (Phases 1-8).
[x] No model was trained.
[x] No Champion was modified.
[~] Existing tests remain green — backend 100% green (2227/0); frontend has 1 pre-existing, unrelated failure (not introduced this session).
[x] Queue-routing defect is documented with exact affected tasks.
[x] No unrelated application logic is changed.
```

## Exact commands to start the complete local stack

```bash
# 1. Redis (dev-only stand-in) — from backend/
python scripts/run_local_fake_redis.py

# 2. Backend — from backend/, with required env vars exported
export TITANIQ_DB_URL="sqlite+aiosqlite:///./dev.db"
export TITANIQ_SUPABASE_PROJECT_URL="https://irhnoilyaqgewfidhunx.supabase.co"
export TITANIQ_ENCRYPTION_KEY="<value from backend/.env>"
export TITANIQ_REDIS_URL="redis://127.0.0.1:6379/0"
export TITANIQ_ENABLE_OFFLINE_AUTH="true"
python -m uvicorn apps.api.main:app --port 8000

# 3. Frontend — from repo root
npm --prefix frontend run dev

# 4. Celery worker (Windows requires --pool=solo) — same env vars as backend, plus:
export TITANIQ_NEWS_SYNC_ENABLED="false"   # or "true" only with explicit authorization
celery -A apps.worker.bootstrap worker --loglevel=info --pool=solo

# 5. Celery Beat — same env vars
celery -A apps.worker.bootstrap beat --loglevel=info
# WARNING: starting Beat fires the entire schedule immediately if its persisted state
# (celerybeat-schedule file) is stale from a prior stop. Do not start Beat unattended
# until the queue-routing gap (§12) and the retraining/calibration exposure (§21) are
# both explicitly addressed.
```

## Final state

**STATE B — PARTIAL RECOVERY.** Frontend, backend, Redis, and the database are all up, healthy, and verified communicating end-to-end with real data. Celery worker and Beat were both demonstrated to start and run correctly but are deliberately not left running, following a real (though ultimately harmless) safety incident during verification. Three real, pre-existing issues were found and documented without being fixed (queue-routing gap, missing `alembic_version`, one frontend test). No code was changed. No training, recalibration, retraining, Champion modification, or external API call occurred.

**Not proceeding to Milestone 23.** Stopping here per explicit instruction, awaiting direction.
