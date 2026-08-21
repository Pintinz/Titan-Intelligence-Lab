# Milestone 21 Verification Report — Live Scheduled News Sync Activation (Phase B)

**Date:** 2026-08-13
**Final status: STATE B — ACTIVATED, NO VERIFIED_PRE_MATCH DATA**

```
NEWS SYNC:        ACTIVE (TITANIQ_NEWS_SYNC_ENABLED=true, worker+Beat ran a real cycle end-to-end)
BACKFILL:         DISABLED (unset, defaults false — untouched)
COMMUNITY:        DISABLED (untouched)
TRAINING:         NOT AUTHORIZED — not attempted
MODEL CHANGES:    NONE
CHAMPION CHANGES: NONE
```

This report documents a genuine, live, end-to-end run of the scheduled news-sync pipeline —
Celery worker + Beat both real production processes, real RSS calls, real cost-control decisions —
that produced **zero** `VERIFIED_PRE_MATCH` news events, because nothing in the fetched article set
was relevant to an upcoming fixture in the configured window. That is a correct, safe outcome, not
a bug: the pipeline's own relevance gate did its job.

Getting to a real run required finding and resolving one genuine environment gap and one genuine
pre-existing production code defect, both explicitly authorized by the user before any fix was
applied. A third defect was found and is reported, unfixed, as out of scope for tonight. None of the
three affected the news-sync task's own correctness.

---

## 1. Configuration status (no secrets exposed)

| Variable | Value | Verified how |
|---|---|---|
| `TITANIQ_NEWS_SYNC_ENABLED` | `true` | set in `backend/.env`, confirmed via `news_sync_config.NEWS_SYNC_ENABLED` at process import time |
| `TITANIQ_NEWS_BACKFILL_ENABLED` | unset (defaults `false`) | confirmed via `news_backfill_config.NEWS_BACKFILL_ENABLED` |
| `NEWS_SYNC_INTERVAL_SECONDS` | 900 (default) | unchanged |
| `NEWS_SYNC_MAX_ARTICLES_PER_RUN` | 20 (default) | unchanged |
| Community Intelligence | not touched | no provider/credentials/ingestion code added |

## 2. Pre-activation safety checks — ALL PASSED

`bootstrap_worker()` executed successfully; all 5 factories registered
(`orchestrator`/`admin_context`/`retraining_orchestrator`/`calibration_service`/`scheduled_news_sync`);
15 tasks discovered across the 4 real task modules including `intelligence.sync_scheduled_news`;
Alembic at head (`0041`); no Community Intelligence code path; no Backfill flag enabled.

## 3. Baseline snapshot (captured before the first worker start attempt)

| Table | Baseline |
|---|---|
| news_sources | 8 |
| news_articles | 199 |
| news_events | 68 |
| intelligence_sync_runs | 23 |
| intelligence_sync_checkpoints | 4 |
| feature_values_offline | 68,223 |
| predictions | 12,436 |
| prediction_outcomes | 11,183 |
| datasets | 0 |
| models | 47 (19 champion) |

`news_events`: 68 `UNKNOWN_AVAILABILITY_TIME`, 0 `VERIFIED_PRE_MATCH`, 0 `INVALID`.
`feature_values_offline` rows with `feature_key LIKE 'news.%'`: 0.

## 4. Defect 1 (dev-environment-only): fakeredis lacks Lua/`EVALSHA` — FIXED

First worker start attempt crashed during Celery's `mingle` bootstep with
`redis.exceptions.ResponseError: unknown command 'evalsha'`. Root cause: Kombu's Redis transport uses
a Lua-scripted mutex for unacked-message-visibility-restoration on every `drain_events()` call, and
`fakeredis.TcpFakeServer` (this project's dev-only Redis stand-in, since no real Redis exists on this
machine) doesn't implement `EVAL`/`EVALSHA` without the optional `lupa` interpreter. This is the first
time any milestone has run a real forked `celery worker` process end-to-end — M11's own report
explicitly scoped that out as untested — so this is a newly-discovered, genuine environment gap, not
an application defect, and not specific to news sync (it would block any real Celery worker here).

**STOPPED and reported to the user** before doing anything about it, per the master prompt's own
"If the worker cannot start cleanly: STOP" / "Do not patch around the problem silently." Offered two
options: install a real Redis server, or install `lupa`. **User chose `lupa`.**

Added `"lupa>=2.2"` to `[project.optional-dependencies].dev` in `pyproject.toml` (same dev-only tier
as the existing `fakeredis` entry) and installed it into the venv (prebuilt wheel, no compiler
needed). Verified `EVALSHA`/`SCRIPT LOAD` work both in-process and over the real TCP path the worker
uses, restarted the fake-redis server process (the fix must load in the *server* process), and
re-ran the worker start command.

**Result: the worker now starts cleanly and reaches a stable `celery@AutotecHUB ready.` state**, held
for the full observation window with no further errors. One transient
`NoScriptError`→`ConnectionError` blip occurred immediately after reconnecting — a normal
SHA-cache-miss-then-reconnect sequence, not a repeat of the Lua-scripting gap — and Celery's own retry
logic recovered automatically within ~1 second.

## 5. Defect 2 (pre-existing production code gap): Beat schedule never wired into the app — FOUND, then FIXED (explicit user authorization)

With the worker stable, Beat was started per the spec — no second schedule created, no existing
schedule modified. `modules/ingestion/infrastructure/celery/beat_schedule.py`'s single existing
`sync-scheduled-news-football-epl` entry (present since Milestone 10) was verified unchanged before
starting.

Beat started without error, but checking the fastest scheduled task (`ingestion.sync_live_fixtures`,
30s interval) over 4+ minutes showed **zero** tasks ever received by the worker. The broker's `celery`
queue length stayed at 0 the whole time. Restarting Beat with `--loglevel=debug` showed why:

```
[DEBUG] Current schedule:

[DEBUG] beat: Ticking with max interval->5.00 minutes
```

**Beat's loaded schedule was empty** — not just the news entry, none of the ~14 entries in
`BEAT_SCHEDULE`. Root cause: `modules/ingestion/infrastructure/celery/beat_schedule.py` defines the
dict `BEAT_SCHEDULE`, but grepping the entire codebase found **nothing in production code ever
assigned it to `celery_app.conf.beat_schedule`** — `celery_app.py`'s `conf.update(...)` call sets
`broker_url`/`task_serializer`/`task_routes`/etc. but never `beat_schedule`, and `bootstrap.py`'s own
docstring assumes "every existing task's ... Beat schedule entry is untouched," which reads as an
assumption the wiring already existed elsewhere rather than evidence it did. **Celery Beat has never
dispatched a single task in this project's history**, for any of its ~14 scheduled jobs — consistent
with M11's own scoping-out of a real end-to-end Beat run.

**STOPPED and reported this to the user before touching any code** — it's a real production gap, not
a dev artifact, and outside what "install lupa" had authorized. **User explicitly authorized the fix:
"yes fix it."**

**Fix applied** (`modules/ingestion/infrastructure/celery/celery_app.py`): imported `BEAT_SCHEDULE`
from `beat_schedule.py` and added `beat_schedule=BEAT_SCHEDULE` to the existing `conf.update(...)`
call — a two-line, additive change, nothing else touched. Verified directly:
`celery_app.conf.beat_schedule` now returns all 21 entries (BEAT_SCHEDULE has grown to 21 since M5/M10,
covering football/basketball/baseball).

Also fixed, same pass: `tests/unit/modules/ingestion/test_beat_schedule.py`'s
`test_beat_schedule_entries_reference_registered_task_names` was failing for an unrelated reason —
it never imported `modules.intelligence.infrastructure.celery.tasks`, so
`intelligence.sync_scheduled_news` was never in the registered-task set it checked against. Confirmed
pre-existing (identical failure with my `celery_app.py` change reverted via `git stash`). Added the
missing import, matching the test's existing pattern for the other 3 task modules.

**Full backend suite re-run after both changes: 2227 passed, 58 skipped, 0 failed** — zero
regressions.

## 6. Live verification: Beat now genuinely dispatches, worker consumes

Restarted worker + Beat with the fix in place. Beat immediately began logging real
`Scheduler: Sending due task ...` lines — the first in this project's history — firing all 5
`sync_live_fixtures` schedule entries within seconds, then every 30s exactly as configured.

## 7. Defect 3 (pre-existing production code gap, found, NOT fixed): task_routes point at queues nobody consumes

While confirming dispatch, no `Received task` line appeared for `ingestion.sync_live_fixtures`
despite Beat sending it every 30s. Checked the broker directly:

```
celery LLEN = 0
live   LLEN = 10   (growing every 30s)
default LLEN = 0
```

`celery_app.py`'s `task_routes` sends `ingestion.sync_live_fixtures` → queue `"live"`, and every
other `ingestion.*`/`admin.*` task → queue `"default"`. But the worker (started with no `-Q` flag)
only declares/consumes the built-in `celery` queue — confirmed from its own startup banner
(`[queues] .> celery exchange=celery(direct) key=celery`, nothing else listed). So `live` and
`default` queue traffic backs up forever, unconsumed.

**This does not affect the milestone's actual target task.** `intelligence.sync_scheduled_news` has
no entry in `task_routes`, so it falls through to Celery's default queue name (`"celery"`) — the one
queue this worker does consume. Confirmed: the news-sync task fired and completed normally (§8).

**Not fixed.** Real, pre-existing (would affect a real production deployment identically), but
outside tonight's authorization, and fixing it (either adding `-Q celery,live,default` to the launch
command, or removing/reworking `task_routes`) is a judgment call about intended architecture that
wasn't asked for. Flagging for a future, explicitly-scoped session. The `live` queue's ~165
accumulated dev-only messages were left in the ephemeral fakeredis instance (no persistence, cleared
on next restart) — no cleanup action taken or needed.

## 8. First live news-sync execution — real, complete observability data

Beat fired `sync-scheduled-news-football-epl` at 20:18:26 (its first-ever real firing, 900s after
Beat start). Worker received and completed it in 22.95s:

| Metric | Value |
|---|---|
| sources_attempted | 8 |
| sources_succeeded | 4 |
| sources_failed | 4 |
| articles_seen | 106 |
| articles_deduplicated | 3 |
| articles_rejected | 24 |
| articles_relevant | 0 |
| articles_skipped_by_relevance | 79 |
| articles_sent_to_gemini | **0** |
| articles_enriched | 0 |
| enrichment_failures | 0 |
| provenance_verified | 0 |
| provenance_unknown | 0 |

**Cost control confirmed working correctly**: 0 Gemini calls, because 0 articles passed the
relevance filter (relevance strictly precedes enrichment, per the existing `ScheduledNewsSyncService`
design — never touched). All 8 fetch attempts used real network calls (real RSS HTTP GETs).

Per-source results (`intelligence_sync_runs`, all `trigger='live_scheduled'`):

| Source | Status | Fetched | Created | Error |
|---|---|---|---|---|
| BBC Sport | succeeded | 50 | 47 | — |
| ESPN Sport (soccer) | failed | 0 | 0 | `no element found: line 1, column 0` (feed returned HTTP 202, empty body) |
| ESPN NBA | failed | 0 | 0 | same as above |
| 90mins | succeeded | 0 | 0 | — |
| theGaurdian | succeeded | 32 | 32 | — |
| Athletic/NYTimes NBA | failed | 0 | 0 | `not well-formed (invalid token)` — HTML, not RSS |
| Athletic/NYTimes MLB | failed | 0 | 0 | same as above |
| MLB | partial | 24 | 0 | all 24 rejected (pre-relevance stage, not the relevance filter itself) |

The two Athletic/NYTimes sources are **pre-existing** rows this session never touched (this session's
earlier RSS-fix work explicitly declined to guess URLs for Athletic/NYTimes domains, having found no
real public feed). ESPN Sport/ESPN NBA are URLs this session verified and fixed earlier tonight —
their live failure now (HTTP 202 with empty body, different from the earlier browser-verified 200)
is a genuine, separate finding: the feed is intermittently unavailable to a real fetcher under real
conditions, not something this session's verification missed. Not fixed tonight — no source URL was
touched, per the master prompt's explicit "do not modify source URLs unless explicitly instructed."

## 9. Provenance verification (Section 9) — trivially satisfied, zero events created

Every one of the 8 `intelligence_sync_runs` rows this run carries `trigger='live_scheduled'` —
confirmed directly from the database, not inferred. Per `news_provenance.py`'s strict equality check,
`LIVE_SCHEDULED` is the only trigger that can ever produce `VERIFIED_PRE_MATCH`. Since
`articles_relevant=0`, **zero news_events were created by this run** — `news_events` count is
unchanged at 68 (still 0 `VERIFIED_PRE_MATCH`, 0 `INVALID`). With no `VERIFIED_PRE_MATCH` events to
check, the master prompt's 9-condition-per-event verification has nothing to verify against — this is
the correct, safe outcome, not a gap in verification.

## 10. News feature verification (Section 10) — trivially satisfied

`feature_values_offline` rows with `feature_key LIKE 'news.%'`: still 0 (unchanged). No
`HISTORICALLY_RELEVANT`-vs-`NEWS_FEATURE_ELIGIBLE` conflation to check, no
`UNKNOWN_AVAILABILITY_TIME`→`VERIFIED_PRE_MATCH` violation possible, because no news feature was ever
published this run.

## 11. Market-specific verification (Section 11)

Ran `scripts/run_training_preflight.py --all-trained-football` (read-only) after the run. **0/14
markets READY** — identical to the M20 baseline. `football.both_teams_to_score`'s 6 required news/
structural features (`home_btts_impact`, `away_btts_impact`, `home_lineup_continuity`,
`away_lineup_continuity`, `home_transfer_activity`, `away_transfer_activity`) all show 0.0% coverage,
same as every other affected market — none made optional, none defaulted, none fabricated. Expected:
this run published zero news features, so market readiness cannot have changed.

One accuracy note, not a functional defect: every market's `dataset_provenance_persisted` check still
fails with the message *"DatasetRepositoryPort is in-memory-only by design — see M19 audit §13,
ADR-008."* That explanatory text is now stale — M19 Phase 4 (earlier this session's prior work)
replaced the in-memory port with a real `SqlAlchemyDatasetRepository`. The check still correctly
fails, though, for an unrelated and accurate reason: the `datasets` table has 0 rows (confirmed) —
nothing has ever actually written a Dataset through the new repository yet, since that only happens
as a side effect of a real training run, and training remains prohibited. Not fixed tonight (cosmetic,
out of scope).

## 12. Training preflight (Section 12) — informational only, training NOT authorized or attempted

0/14 READY, unchanged from baseline. No market becoming READY would have authorized training in any
case, per the master prompt's own explicit rule — moot here since none did.

## 13. Prediction safety (Section 13) — verified unchanged

`predictions`: 12,436 → 12,436 (unchanged). `prediction_outcomes`: 11,183 → 11,183 (unchanged).
`models`: 47 → 47, champion count 19 → 19 (unchanged). No `MissingRequiredFeatureError` bypass
occurred (none of the affected markets were exercised by this run). No fabricated required-feature
value was ever written.

## 14. Database delta vs. baseline (Section 14)

| Table | Baseline | After run | Δ |
|---|---|---|---|
| news_sources | 8 | 8 | 0 |
| news_articles | 199 | 277 | **+78** |
| news_events | 68 | 68 | 0 |
| intelligence_sync_runs | 23 | 31 | **+8** (one per source attempted) |
| intelligence_sync_checkpoints | 4 | 8 | **+4** (one per source that succeeded) |
| feature_values_offline | 68,223 | 68,223 | 0 |
| feature_values_offline (`news.%`) | 0 | 0 | 0 |
| predictions | 12,436 | 12,436 | 0 |
| prediction_outcomes | 11,183 | 11,183 | 0 |
| datasets | 0 | 0 | 0 |
| models | 47 | 47 | 0 |
| models (champion) | 19 | 19 | 0 |

Growth is confined to `news_articles`/`intelligence_sync_runs`/`intelligence_sync_checkpoints` —
exactly the tables the spec expects to grow. No prediction, model, or training table changed at all.

## 15. Local-dev limitation (Section 15)

No supervisor, no persistent process manager exists here. fakeredis was observed dying unexpectedly
multiple times across this session with no automatic restart. Both Celery processes were manually
started, manually observed, and manually stopped this session — this is
**PROSPECTIVE DATA ACCUMULATION ACTIVE DURING A CONTROLLED DEV SESSION**, never continuous production
operation, and does not persist after the session ends (both processes were stopped at the end of
this milestone).

## 16. External API accountability (Section 16)

8 real RSS HTTP requests made (one per configured news source), 4 succeeded, 4 failed (feed-level
errors, not rate-limiting). 0 Gemini API calls (correctly gated by the relevance filter — nothing
warranted enrichment). No rate-limit response was observed from any source.

## 17. Security (Section 17)

No credentials logged, persisted outside the encrypted `provider_credentials` store, or exposed in
this report. Neither of the two fixed defects, nor the third (unfixed) one, ever touched a provider
credential path.

## 18. Community Intelligence (Section 18) — untouched

No provider, API, credentials, ingestion path, or feature mapping added or enabled.

## 19. Backfill (Section 19) — untouched

`TITANIQ_NEWS_BACKFILL_ENABLED` remains unset/false. No backfill endpoint or task was ever called.

## 20. Accumulation expectation (Section 20)

This single run correctly produced zero training-relevant observations — expected and healthy. Real
accumulation requires: an upcoming fixture inside the configured window + a genuinely relevant
pre-kickoff article about it, which did not exist in tonight's live article set. No historical
observation was fabricated or retroactively reclassified to manufacture progress.

## 21. Failure handling record (Section 21)

Both real defects encountered (Lua/`EVALSHA`, Beat schedule wiring) were **stopped on and reported
before any fix was applied**, with explicit user authorization obtained before each fix. The third
defect (queue routing) was found, confirmed not to block the milestone's actual target task, and
reported without being fixed, since no authorization was sought or given for it. No fix was ever
applied silently.

## 22. Summary flags

```
NEWS SYNC:        ACTIVE
BACKFILL:         DISABLED
COMMUNITY:        DISABLED
TRAINING:         NOT AUTHORIZED
MODEL CHANGES:    NONE
CHAMPION CHANGES: NONE
```

## 23. Final state

**STATE B — ACTIVATED, NO VERIFIED_PRE_MATCH DATA.** The pipeline is now genuinely live and correct:
worker and Beat both run real production code paths, Beat dispatches on schedule, the worker consumes
and executes the news-sync task, real external RSS calls were made, cost controls held Gemini calls to
zero exactly when nothing warranted them, and every safety gate (provenance trigger, relevance filter,
feature-parity gate, training-preflight gate) behaved exactly as designed. Zero `VERIFIED_PRE_MATCH`
events were produced on this first run — not a failure, the honest result of a real-world article set
that didn't overlap with an in-window upcoming fixture. **Not STATE E** — `TrainingPreflightService`
independently reports 0/14 READY, unchanged.

## 24. Mandatory stop

Stopping here. No Milestone 22. No training, retraining, recalibration, promotion, backfill-enabling,
Community-Intelligence-enabling, or safety-gate weakening was performed or will be performed without
further explicit approval. Both Celery processes were stopped cleanly at the end of this session;
nothing is left running. Two real defects (Lua/`EVALSHA`, Beat schedule wiring) were fixed with
explicit authorization; a third (queue routing for `ingestion.*`/`admin.*` tasks) was found and left
unfixed, reported here for a future explicitly-scoped session.
