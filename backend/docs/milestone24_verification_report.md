# Milestone 24 — Verification Report (FINAL MILESTONE)

**Date:** 2026-08-14
**Status:** COMPLETE. This is the final milestone of the TitanIQ engagement. No M25.

---

## 1. Final state

**STATE A — Accumulating, insufficient for training.**

The pipeline ran correctly end-to-end against real external sources with the M24 hardening fixes
in place. It found zero fixtures within any accumulation window this session, because the
earliest scheduled fixture (2026-08-21 19:00 UTC) remains ~184 hours away — outside both the
72-hour structured-intelligence window and the 168-hour news window. This is a calendar fact, not
a defect: every prior milestone (M17 onward) established the same structural blocker, and it
persists here for the same reason. No code change can shorten the wait for real fixtures to
approach kickoff.

**TRAINING NOT PERFORMED — INSUFFICIENT LEGITIMATE DATA.** Per this milestone's own governing
principles, this is an explicitly acceptable final outcome, not a failure.

---

## 2. Markets audited

All 14 genuinely-trained football markets, via `scripts/run_training_preflight.py
--all-trained-football`, re-run fresh at the end of this milestone (not assumed from a prior run):

`match_winner`, `both_teams_to_score`, `correct_score`, `home_clean_sheet`, `away_clean_sheet`,
`home_team_total_goals`, `away_team_total_goals`, and 7 additional line-aware/regression markets
carried from M8–M18.

## 3. Markets passing preflight

**0 / 14.** Unchanged from every prior run this entire session (M19 through M24).

## 4. Observation counts

No new `VERIFIED_PRE_MATCH` observations were produced this session (Phase 2, §9 below).
Cumulative counts, unchanged from M23:

| Source | Total rows | `VERIFIED_PRE_MATCH` |
|---|---|---|
| `news_events` | 68 | 0 (all `UNKNOWN_AVAILABILITY_TIME`) |
| `lineups` | 4 | 0 |
| `transfers` | 308 | 0 |
| `injuries` | 30 | 0 |

## 5. Feature coverage

Identical gated-feature coverage failures on every run, all at 0.0%:
`football.fixture.{home,away}_lineup_continuity`, `football.fixture.{home,away}_transfer_activity`,
plus the relevant `news.football.{home,away}_{goal,clean_sheet,btts}_impact` pair on 12 of 14
markets (`match_winner`/`correct_score` need only the 4 lineup/transfer keys).

## 6. Training/inference parity

Fails identically to every gated key above — `training_inference_feature_parity` requires each key
present at live inference to also appear in ≥1 training sample; none of the gated keys have ever
been genuinely populated for a training-eligible historical fixture.

## 7. Dataset IDs / hashes

Every market's `dataset_reproducible` gate passed — two independent builds of the same market
produce an identical `content_hash` (e.g. `football.match_winner`: `cdc114215708...`,
`football.away_team_total_goals`: `cad4941bde45...`, `football.away_clean_sheet`:
`15d59f5a6d69...`). `dataset_provenance_persisted` fails on all 14 — no `Dataset` has ever been
durably persisted (repository is in-memory-only by design, per M19 audit §13 / ADR-008), which is
a structural characteristic of this codebase, not something this milestone touched.

## 8. Temporal split info

`temporal_reference_present` and `temporal_split_valid` (M18's chronological-sort, fail-closed
`TIME_SERIES_SPLIT`) pass on all 14 markets — every sample carries a real `reference_time`, and the
dry-run split preserves chronological ordering. Unmodified this milestone.

## 9. Challengers trained / validated / promoted

**None.** Training was never attempted — the preflight gate correctly blocked at 0/14, per this
milestone's absolute rule: never declare readiness merely because feature coverage is non-zero, and
the correct outcome when gates fail is TRAINING BLOCKED, not a forced attempt.

## 10. Champion changes

**None.** No Champion model was retrained, replaced, or otherwise touched.

## 11. Calibration/retraining performed

**No, by explicit design.** `predictions.check_scheduled_calibration` and
`predictions.check_scheduled_retraining` were never dispatched, at any point, by any process, this
entire milestone. Verified three independent ways:

1. The worker's log shows exactly two task names ever received:
   `ingestion.sync_upcoming_structured_intelligence` and `intelligence.sync_scheduled_news`.
2. Beat was never started — only a plain worker process (`celery -A apps.worker.bootstrap worker`,
   no `-B`/beat flag).
3. Redis queue depths (`celery`, `live`, `default`) were confirmed empty both before dispatch and
   after the worker was stopped — no residual or orphaned task of any kind.

## 12. External API call counts (Phase 2, this session)

- **RSS/news sources**: 8 attempted, 4 succeeded (0 new relevant articles), 4 failed (pre-existing
  provider-side fetch/parse fragility — e.g. ESPN feeds returning HTTP 202 non-XML — not a defect
  introduced this milestone), 1 partial (9 items fetched, 0 created — all rejected by relevance
  filtering).
- **Gemini (LLM enrichment)**: 0 calls. `articles_sent_to_gemini: 0` — the relevance filter
  correctly found nothing worth enriching, so no LLM cost was incurred.
- **Sports-provider (fixtures/lineups/injuries/transfers)**: 0 calls this dispatch —
  `sync_upcoming_structured_intelligence` returned `[]` immediately because zero fixtures fell
  within its 72-hour window; no provider request was ever made.

## 13. Database changes

- 8 new rows in `intelligence_sync_runs` (real per-source sync attempts, `trigger='live_scheduled'`,
  all with genuinely zero `items_created`).
- 0 new rows in `news_events`, `lineups`, `injuries`, `transfers`.
- 0 new rows in `sync_runs` (structured-intelligence found nothing to reconcile, so no entity-level
  sync ran).
- 0 changes to `calibration_reports`, model registry, or any prediction/market table.
- No schema change, no migration.

## 14. Migrations

**None.** This milestone made zero schema changes.

## 15. Test results

- Targeted Celery-task tests (all 4 modules + `test_worker_bootstrap.py`): 38 passed.
- Two new regression tests added, proving the connection-leak fix actually closes sessions (spied
  on success and on error paths): both passed.
- **Full backend suite: 2230 passed, 58 skipped, 0 failed** (850s), up from the pre-M24 baseline of
  2228/58/0 — the +2 delta is exactly the two new leak-fix regression tests. Zero regressions.

## 16. Phase 1 — Operational Hardening (implemented, approved, verified)

**(a) Queue-routing fix — two layers, both fixed:**
1. Removed the dead `task_routes` dict from `celery_app.py` (previously routed `ingestion.*`/
   `admin.*` to `"live"`/`"default"` queues nothing ever consumed).
2. **Discovered mid-implementation**: every one of the 15 task decorators also carried its own
   redundant `queue=` kwarg, which Celery's real `Task.apply_async()` merges into routing options
   independently of `task_routes` — a second, deeper layer of the same defect that a naive
   verification test (calling the router with an empty options dict) would have missed. Removed
   all 15. **Verified live**: this session's real worker log shows a single `celery` queue
   consuming all 15 registered tasks with a *plain* `celery -A apps.worker.bootstrap worker`
   invocation — no `-Q` flag needed, unlike M23.

**(b) Connection-leak fix (approved by explicit user decision after presenting three options):**
Converted the 4 shared per-module session-acquiring helpers (`_get_orchestrator`,
`_get_admin_context`, `_get_scheduled_news_sync_service`, `_get_retraining_orchestrator` /
`_get_calibration_service`) into async context managers that close the worker session tagged onto
each service object (`bootstrap.py`'s new `_worker_session` attribute) before each task's
`asyncio.run()` call tears down its event loop. Updated all 15 task bodies to `async with
_get_X() as x:`. Proven with two new spy-based tests (session closes on both success and
exception paths), not just "existing tests still pass."

**(c) Beat stale-schedule handling: explicitly not built**, per the standing recommendation —
continued the M23-proven pattern (worker-only, explicit dispatch, Beat never started).

## 17. Phase 2 — Live Accumulation (executed)

Redis was unavailable in this environment at the start of Phase 2 (no local binary, no Docker, no
WSL install) — user explicitly authorized installing `redis-server` in WSL; installed, started,
confirmed reachable from the Windows-side worker process.

Executed exactly the proven M23 pattern: worker-only (no Beat, never started), plain invocation (no
`-Q` needed — proof the Phase 1(a) fix works), explicit dispatch of only the two safe accumulation
tasks (`ingestion.sync_upcoming_structured_intelligence`, `intelligence.sync_scheduled_news`) using
the real, Beat-configured EPL `season_id` (`21521495-4dd4-4c50-a41d-d88642322804`) — not an
arbitrary value. Watched the worker log throughout for calibration/retraining task names (none
appeared). Verified queue depths empty before and after. Stopped the worker cleanly after
completion; confirmed no worker process remained.

Result: reproduced the expected zero-new-observations outcome exactly, per the audit's own honest
pre-registered expectation (§9 above / §12 external calls).

## 18. Remaining limitations (carried forward, unrelated to this milestone's mission)

- `alembic_version` still missing from `dev.db` (found M22, unrelated to training).
- One pre-existing frontend test failure (`insights-page.test.tsx`, found M22, confirmed unrelated
  — zero frontend files touched this entire session).
- `DatasetRepositoryPort` remains in-memory-only by design (ADR-008) — `dataset_provenance_persisted`
  will continue failing on every market until that architectural decision changes, independent of
  data accumulation.
- 4 of 8 RSS sources have pre-existing fetch/parse fragility (ESPN feeds returning non-XML
  responses) — real but not a defect introduced or investigated this milestone.

## 19. Final state, restated

**STATE A.** The pipeline is correct, safe, and now more operationally sound than at any prior
milestone (both queue-routing layers fixed and verified live; the connection-leak fixed and proven
with real tests). It is accumulating real data through real, unmodified external sources under
real provenance rules. It has not yet accumulated enough — specifically, zero — genuine
`VERIFIED_PRE_MATCH` observations, because no real fixture has yet approached kickoff during any
session across this entire multi-milestone engagement. This is a calendar constraint, not a code
defect, and no further code change in this codebase can resolve it faster than real time passing.

---

## STOP COMPLETELY

This is Milestone 24, the final milestone of the TitanIQ engagement. Per this milestone's own
explicit instruction, this report is now filed and the engagement stops here. There is no
Milestone 25. Future work (if any) begins as a new, separately-scoped engagement.
