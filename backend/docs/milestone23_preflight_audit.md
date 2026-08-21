# Milestone 23 — Read-Only Pre-Flight Audit (Governed Live-Accumulation Attempt)

**Status: READ-ONLY.** No code, schema, or `dev.db` row modified. No process started. No external call made.

## A. Which queues each scheduled task uses

From `celery_app.conf.task_routes` (unchanged since M22):
```python
{'ingestion.sync_live_fixtures': {'queue': 'live'},
 'ingestion.*': {'queue': 'default'},
 'admin.*': {'queue': 'default'}}
```
`intelligence.sync_scheduled_news`, `predictions.check_scheduled_calibration`, `predictions.check_scheduled_retraining` have no explicit route — they fall through to Celery's default queue name, `celery`.

## B. Which queues the worker consumes

Currently: **only `celery`** (default worker invocation, no `-Q` flag — confirmed from the worker's own startup banner in every prior session's log). This milestone's authorized fix: launch with `-Q celery,live,default`.

## C. Which tasks could retrain/recalibrate models

Exactly two: `predictions.check_scheduled_calibration` (fits Platt/Isotonic calibration on existing Champions if ≥20 usable outcome samples exist per market — confirmed 0/37 markets qualified when this last ran, M22) and `predictions.check_scheduled_retraining` (evaluates retraining need; per M9.1/M196-202 history, can auto-promote a bootstrap Challenger). **Neither is a target of this milestone's dispatch list.**

## D. Whether the worker can safely run without Beat

**Yes, with one caveat found in this audit (not previously documented):** without Beat, nothing is dispatched automatically — Beat is the only source of scheduled dispatch in this codebase (confirmed: no other cron/timer mechanism exists). However, the broker (Redis) currently holds a **backlog of 191 already-dispatched, never-consumed messages** from last night's M22 Beat run (see below) — starting a worker that consumes `live`/`default` will immediately begin draining this backlog, independent of anything this session explicitly dispatches.

**Backlog inspection (read-only, `LLEN` + message-body peek):**

| Queue | Length | Contents |
|---|---|---|
| `celery` | **0** | Empty — confirms zero calibration/retraining backlog risk. |
| `live` | **175** | `ingestion.sync_live_fixtures` repeated for football/basketball/baseball (5 sport/competition combinations, ~35× each) — live-fixture status checks, not gated-feature sources. |
| `default` | **16** | `ingestion.sync_upcoming_fixtures`, `ingestion.sync_standings`(×4), `ingestion.sync_upcoming_structured_intelligence`(×2), `admin.check_all_provider_health`(×4), `ingestion.sync_standings_alt`, `ingestion.sync_completed_fixtures`(×2) — all real, all safe (none is calibration/retraining), but redundant (multiple duplicate dispatches of the same task/args). |

None of these messages carry a stale timestamp (the ones with an optional `now_iso` arg omit it, so it resolves to real current time at execution — provenance-safe regardless of queue dwell time). **This is flagged, not treated as disqualifying**: it means starting the worker triggers a larger burst of real external-provider calls than this milestone's own Phase 4/5 explicitly planned to dispatch.

## E. Whether the worker can run structured intelligence without triggering calibration/retraining

**Yes.** `ingestion.sync_upcoming_structured_intelligence` and `intelligence.sync_scheduled_news` are entirely independent Celery tasks from `predictions.check_scheduled_calibration`/`check_scheduled_retraining` — dispatching one never triggers another. The only way calibration/retraining execute is if something (Beat, or an explicit manual call) dispatches them by name. **This milestone will not dispatch them.**

## F. Current required-feature coverage — all 14 genuinely-trained football markets

Re-run fresh this milestone (`scripts/run_training_preflight.py --all-trained-football`): **0/14 READY**, unchanged in every particular from every prior run (M19/M20/M21/M22/M23-first-attempt). Every market: 8 checks PASS (market exists, feature manifest, ≥30 labeled samples, valid labels, temporal reference present, temporal split valid, feature versions known, leakage-safe), 2 hard FAILs (`training_inference_feature_parity`, `required_feature_coverage_acceptable`) on the identical set of gated keys (`{home,away}_lineup_continuity`, `{home,away}_transfer_activity`, plus 2 news-impact keys on 12 of 14 markets), 1 cosmetic FAIL (`dataset_provenance_persisted` — stale message text, real reason is simply that no dataset has ever been persisted, since no training has occurred).

## G. Current VERIFIED_PRE_MATCH counts by feature

| Source table | Total rows | `VERIFIED_PRE_MATCH` | `UNKNOWN_AVAILABILITY_TIME` |
|---|---|---|---|
| `news_events` | 68 | **0** | 68 |
| `lineups` | 4 | **0** | 4 |
| `transfers` | 308 | **0** | 308 |
| `injuries` | 30 | **0** | 30 |

Zero `VERIFIED_PRE_MATCH` observations exist anywhere in the database, on any gated feature source, confirmed directly.

## H. Current upcoming-fixture horizon

**Decisive finding.** As of this audit (`2026-08-14T00:03:50Z`):

- Fixtures with `status='scheduled'` and `scheduled_at` within the 90-minute lineup-sync window (`LINEUP_PREMATCH_WINDOW_MINUTES`): **0**
- Fixtures within the 168-hour (7-day) news-sync window (`NEWS_SYNC_FIXTURE_WINDOW_HOURS`): **0**
- Earliest scheduled fixture in the entire database: **2026-08-21 19:00:00** — **~7 days 19 hours away**, past both windows.

**Consequence:** even a fully-fixed, fully-running pipeline cannot produce a single new `VERIFIED_PRE_MATCH` lineup/transfer/injury/news observation right now — there is no fixture within reach of either sync window for the pipeline to attach intelligence to. This is not a code defect; it is a real, honest fact about the current fixture calendar.

## I. Current TrainingPreflightService result

0/14 READY (§F). Identical to baseline.

## Baseline database row counts (captured before any action this milestone)

| Table | Count |
|---|---|
| fixtures | 6,834 |
| news_articles | 277 |
| news_events | 68 |
| intelligence_sync_runs | 31 |
| intelligence_sync_checkpoints | 8 |
| transfers | 308 |
| lineups | 4 |
| injuries | 30 |
| datasets | 0 |
| models | 47 (19 champion) |
| feature_values_offline | 68,223 |
| predictions | 12,436 |
| prediction_outcomes | 11,183 |
| calibration_reports | 0 |

## STOP condition check

*"STOP if any unexpected training/retraining/calibration path can execute from the worker-only startup."*

**No such path exists.** `celery` queue (the only one calibration/retraining tasks ever land in) is empty. Without Beat, nothing dispatches them. This audit does not trigger the STOP condition — proceeding to Phase 2 is safe with respect to that specific rule.

**Separately flagged (not a STOP-condition trigger, but material):** the `live`/`default` backlog (§D) means the *scope* of external calls triggered by starting the worker is larger than "only the tasks this session explicitly dispatches" — worth the user's awareness before the worker is actually started.
