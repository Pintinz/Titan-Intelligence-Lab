# POST-M24 Master Data Fabric — Phase 9 Verification Report

## Training Readiness Review → First Ready Market

**Date:** 2026-08-15
**Scope:** Runtime verification → baseline database snapshot → official `TrainingPreflightService`
run against all 14 markets with real labeled outcomes → root-cause trace of every blocking gate
→ decision on whether any legitimate code fix exists → re-run → decision gate. No training, no
Champion changes, no calibration, no Celery Beat, no fabricated data.

---

## 1. Executive Summary

Phase 9 audited every market with any real labeled training data (14 football markets; every other
market — 5 basketball, 6 baseball, 6 table_tennis, and 4 additional football "heuristic" markets —
has **zero** `prediction_outcomes` rows and was excluded from a meaningful preflight run for that
reason, confirmed by direct query, §9).

All 14 candidate markets are **BLOCKED**, each failing exactly the same two checks, for two
distinct and fully-traced reasons:

1. **`training_inference_feature_parity` / `required_feature_coverage_acceptable`** — every market
   requires `football.fixture.{home,away}_lineup_continuity` and
   `football.fixture.{home,away}_transfer_activity`. Direct query confirms **zero** rows in
   `lineups` (4 total) or `transfers` (308 total) anywhere in `dev.db` carry the
   `VERIFIED_PRE_MATCH` classification these calculators require — every one is
   `UNKNOWN_AVAILABILITY_TIME`. This is not a bug: it is the intended, explicitly-documented
   Milestone 6/7 safety gate operating exactly as designed, combined with a genuine data deficit
   (that classification is only ever assigned by a live, near-kickoff sync that requires Celery
   Beat, which has never run in this environment and which this phase is explicitly forbidden from
   starting).
2. **`dataset_provenance_persisted`** — `datasets` has 0 rows for any market. Traced to source: the
   only code path that ever calls `DatasetRegistryService.register()` is
   `ScheduledRetrainingOrchestrator._build_validate_approve_dataset()`, invoked exclusively as the
   first step of an actual retraining run. No retraining run has ever executed (by design, across
   every phase of this initiative). This is the **correct, expected state**, not a defect —
   persisting a Dataset record outside of a real training decision would be exactly the kind of
   "rewrite provenance simply to make the preflight pass" this phase's own instructions prohibit.

**No code was changed this phase.** Both blockers were investigated to their root cause and
determined to be legitimate — one an intentional, already-documented safety gate compounded by a
real data deficit that cannot be resolved without either fabricating data or running live
pre-match sync over time (both out of scope/prohibited this phase); the other a correct reflection
of "no training has ever legitimately run yet." Weakening either would violate this phase's own
explicit rules.

**Zero markets are ready for training.** Full regression suite re-run confirms zero regressions
(§16). Database state, Champion set, and champion_set_hash are byte-for-byte unchanged from Phase
8 (§14, §17).

---

## 2. Runtime Status (Part 1)

| Component | Status | Detail |
|---|---|---|
| Frontend | UP | Vite dev server already running at `http://localhost:5173` (confirmed via `netstat`, PID 5900) |
| Redis | UP | Real Redis-protocol server listening on `127.0.0.1:6379` (confirmed via `netstat`) |
| Backend | was DOWN, **restored** | Port 8000 had no listener at phase start |
| Database | UP | Local SQLite `dev.db`, confirmed reachable by both the live backend and direct read-only queries throughout this phase |

**Backend restoration** (no architecture change): started via the repository's own canonical
procedure, documented verbatim in `.env`'s own header comment — `set -a; source .env; set +a;
python -m uvicorn apps.api.main:app --port 8000`. Root cause of the initial failure: an earlier
manual start in this session used a freshly-generated `TITANIQ_ENCRYPTION_KEY` and no
`TITANIQ_SUPABASE_PROJECT_URL`, which crashed `SupabaseJWKSValidator` on every request needing auth
(`SupabaseAuthSettings` requires `project_url`, real error captured: `pydantic_core.ValidationError:
1 validation error for SupabaseAuthSettings / project_url / Field required`). Restarting with the
repository's own committed `.env` (real `TITANIQ_SUPABASE_PROJECT_URL`, the real
`TITANIQ_ENCRYPTION_KEY` already used to encrypt any existing provider credentials in `dev.db`)
resolved it — confirmed live: the already-open frontend tab's own polling requests
(`/api/v1/alerts/unread-count`, `/api/v1/sports/{football,basketball,baseball,table_tennis}/fixtures`)
all returned `200 OK` once the backend was restarted this way. Frontend → Backend → Database and
Backend → Redis are all confirmed live via real traffic, not a synthetic health-check.

Celery Beat: **not started**, per Part 20.

---

## 3. Baseline Database State (Part 2)

Read-only snapshot, direct SQLite query, before any Phase 9 activity:

| Table | Count |
|---|---|
| fixtures | 7,386 |
| matches | 178 |
| teams | 236 |
| competitions | 8 |
| seasons | 22 |
| feature_definitions | 47 |
| feature_values_offline | 72,744 |
| feature_values_online | *(no DB table — online feature store is Redis-only by design, confirmed no such table exists)* |
| prediction_markets | 43 |
| prediction_outcomes | 11,194 |
| predictions | 12,436 |
| datasets | 0 |
| models | 47 (19 champion / 14 candidate / 14 retired) |
| calibration_reports | 0 |
| players | 100 |
| player_statistics | 0 |
| market_lines | 0 |
| news_articles | 319 |
| news_events | 68 |
| provider_ref_index | 8,110 |
| sync_runs | 405 |
| sync_checkpoints | 203 |

**Champion set**: 19 Champions, `champion_set_hash` (SHA-256 of concatenated
`id|market_id|model_key|version|algorithm|artifact_ref|dataset_version|promoted_at` for every
champion row, ordered by `model_key`): `cc5deabbfdb7d9e709d70bbaf885c199dd66306ca35b46f0ec5d028310541312`.

All figures match Phase 8's own closing snapshot exactly — no drift occurred between phases.

---

## 4. Official Preflight — BEFORE (Part 3)

Run via the repository's own existing tool, unmodified: `scripts/run_training_preflight.py
--all-trained-football`, against all 14 markets its own docstring identifies as the only ones with
real labels (`prediction_outcomes > 0`, confirmed independently in §9).

**Result: 0/14 markets READY.**

| Market | Labeled samples | Result | Failing checks |
|---|---|---|---|
| football.correct_score | 828 | BLOCKED | parity, coverage, dataset_provenance |
| football.total_goals_over_under | 823 | BLOCKED | parity, coverage, dataset_provenance |
| football.total_goals_over_under_0_5 | 823 | BLOCKED | parity, coverage, dataset_provenance |
| football.total_goals_over_under_1_5 | 823 | BLOCKED | parity, coverage, dataset_provenance |
| football.total_goals_over_under_3_5 | 823 | BLOCKED | parity, coverage, dataset_provenance |
| football.total_goals_over_under_4_5 | 823 | BLOCKED | parity, coverage, dataset_provenance |
| football.home_win_to_nil | 823 | BLOCKED | parity, coverage, dataset_provenance |
| football.home_team_total_goals | 823 | BLOCKED | parity, coverage, dataset_provenance |
| football.home_clean_sheet | 824 | BLOCKED | parity, coverage, dataset_provenance |
| football.away_win_to_nil | 823 | BLOCKED | parity, coverage, dataset_provenance |
| football.away_team_total_goals | 823 | BLOCKED | parity, coverage, dataset_provenance |
| football.away_clean_sheet | 824 | BLOCKED | parity, coverage, dataset_provenance |
| football.match_winner | 658 | BLOCKED | parity, coverage, dataset_provenance |
| football.both_teams_to_score | 653 | BLOCKED | parity, coverage, dataset_provenance |

Every other check (`market_exists`, `feature_manifest_declared`, `sufficient_labeled_observations`,
`labels_valid`, `temporal_reference_present`, `temporal_split_valid`, `feature_versions_known`,
`intelligence_feature_leakage_safe`, `dataset_reproducible`) **passes** for all 14 markets. All
sample counts are well above the minimum (30) — see §11 for the full sufficiency discussion.

Full raw output: `scratchpad/phase9_preflight_before.log`.

---

## 5. Blocker Trace — `training_inference_feature_parity` / `required_feature_coverage_acceptable` (Parts 4-6)

**Trace**: `TrainingPreflightService._training_inference_feature_parity` /
`_required_feature_coverage_acceptable`
→ `FeatureMarketMappingRepositoryPort.list_by_market` (`is_required=True` rows)
→ `DatasetBuilder.build()`'s per-sample feature resolution
→ `feature_values_offline` (queried per fixture/feature key)
→ producer: `LineupContinuityCalculator` / `TransferActivityCalculator`
(`modules/predictions/football/lineup_continuity_calculator.py` /
`transfer_activity_calculator.py`) — these only ever write a value when the source `lineups` /
`transfers` row's `availability_classification` is `VERIFIED_PRE_MATCH`
→ classification producer: the provenance-classification service wired in
`EntityReconciliationService.reconcile_lineup` / `reconcile_transfer`, which only assigns
`VERIFIED_PRE_MATCH` for a `SyncTrigger.LIVE_SCHEDULED` sync inside the configured
pre-kickoff window (Milestone 5).

**Direct evidence** (query against `dev.db`, read-only):

```
lineups:   4 rows total, availability_classification: {'UNKNOWN_AVAILABILITY_TIME': 4}
transfers: 308 rows total, availability_classification: {'UNKNOWN_AVAILABILITY_TIME': 308}
```

Zero rows of either table, across the entire database, have ever reached `VERIFIED_PRE_MATCH`. The
only path to that classification (`LIVE_SCHEDULED` sync inside the pre-kickoff window) requires a
running Celery Beat schedule (Milestone 5.8) — and Celery Beat has never run in this environment,
across every phase of this initiative (an explicit, standing rule since Phase 5B). This is a
genuine, currently-irresolvable **data deficit** — not a bug in the calculators, not a bug in the
reconciliation pipeline, and not something a historical backfill (Phase 8) can ever satisfy: a
backfilled fixture's lineup/transfer information, even if it existed, would have unknown
availability timing by construction (`WebHistoricalSource`/`CsvHistoricalSource` never claim a
pre-match timestamp — Phase 8 §8/§9), so it could never legitimately earn `VERIFIED_PRE_MATCH`
either.

**Is `is_required=True` itself a bug?** Traced directly to `market_seeding.py`'s own committed
comment (lines 543-549, unmodified this phase):

> "`home/away_lineup_continuity`/`transfer_activity` must stay required=True on the 14 trained
> markets (Milestones 6/7 — **a training dataset should demand the pre-match feature exist**) but
> optional on these four live-formula-served markets specifically."

This is not an oversight parallel to the 4 heuristic markets' `optional_features` treatment — it is
an explicit, already-considered, and already-documented decision that these features **must** stay
required for markets destined for real training, precisely so that a future retrain cannot silently
skip real pre-match signal it should use. Making it optional now would be the exact "weakening a
gate" this phase's Part 14 prohibits, contradicting a decision this codebase's own history already
made deliberately. **Classification: intentional safety gate + real data deficit. Not a code
defect. Not fixed.**

---

## 6. Blocker Trace — `dataset_provenance_persisted` (Parts 7-8)

**Trace**: `TrainingPreflightService._dataset_provenance_persisted`
→ `DatasetRepositoryPort.list_by_market` (real, durable, SQL-backed: confirmed
`build_dataset_repo()` in `apps/api/composition.py` returns `SqlAlchemyDatasetRepository` against
the real `datasets` table — the Milestone 20 Phase A work already retired the in-memory-only
ADR-008 posture for production wiring; `InMemoryDatasetRepository` remains only for tests)
→ `datasets` table: **0 rows**, confirmed by direct query.

The wiring is real and correct — this is not the ADR-008 gap the check's own message references
(that message is a Milestone 19-era comment, now stale relative to Milestone 20's fix, but harmless
since the underlying observation — 0 rows — is independently, separately true).

**Why 0 rows, traced to source**: the only code path in the entire codebase that ever calls
`DatasetRegistryService.register()` is
`ScheduledRetrainingOrchestrator._build_validate_approve_dataset()`
(`modules/predictions/application/scheduled_retraining_orchestrator.py:269-275`), which is called
from `_check_and_retrain()` immediately followed, in the same method, by
`model_selection.select_and_register_challenger()` — i.e., dataset registration exists in this
codebase **only** as the first step of an actual retraining attempt, never as a standalone action.
No retraining run has ever executed against `dev.db` (a standing rule honored by every phase of
this initiative, including this one).

**Could this be called standalone, without training, to satisfy the check?** Yes, mechanically —
`DatasetRegistryService.register(dataset)` is a pure metadata write (`self.datasets.upsert(dataset)`
— no model fitting, no `models` table write). But doing so here, divorced from any real training
decision, was assessed and **rejected**: it would create a `datasets` row whose only purpose is to
make this one check pass, with no corresponding training ever following it in this phase (explicitly
prohibited), and a real future retraining run would build its own fresh dataset anyway (the
orchestrator always computes `next_version = latest.version + 1`) — making today's row dead,
disconnected provenance rather than genuine audit trail. This is precisely the outcome Part 8's own
instruction warns against: **"Do NOT rewrite provenance simply to make the preflight pass."**

**Classification: correct, expected current state — no training has ever legitimately run, so no
dataset has ever been legitimately committed. Not a code defect. Not fixed.**

---

## 7. Historical Odds Assessment (Part 9)

Of the 14 candidate markets, only `football.match_winner` requires odds-derived features
(`football.market.implied_probability_home`/`away`). Checked directly in its preflight output:
both features **appear** in at least one training sample (they do not appear in the
`training_inference_feature_parity` failure list) and **pass** `required_feature_coverage_acceptable`
— i.e., odds coverage is not currently a blocker for `match_winner`. (`football.correct_score`
separately shows low coverage — 1.9% — for `football.market.implied_probability_home`, but
`correct_score` is already blocked by the universal lineup/transfer gate regardless, so this is
recorded but not independently actionable this phase.)

Phase 8's football-data.co.uk historical import legitimately contains real bookmaker odds columns
but they were **not imported** into `market_lines` this phase or any prior phase (`market_lines`:
0 rows, confirmed §3) — still the real, documented, unbuilt architecture gap from Phase 8 §17.
Since no candidate market is currently blocked by odds coverage, building that import was correctly
out of scope this phase (`Part 9`'s own instruction: "do NOT build the odds import merely because
it exists as a future opportunity").

---

## 8. Market-by-Market Readiness (Part 10)

**Market-first audit, football first**: all 14 markets with real historical labels were checked
individually (§4) — all 14 BLOCKED, for the identical two reasons (§5, §6). No football market
escapes the universal lineup/transfer-continuity gate.

**The 4 remaining football markets** (`first_half_winner`, `second_half_winner`, `first_half_goals`,
`first_half_both_teams_to_score`) were **not** re-run through the preflight tool (their
`required_features` do mark lineup/transfer as optional, matching the 4 heuristic markets' pattern)
because a direct query (§9) already confirms they have **zero** `prediction_outcomes` — the
preflight's own `sufficient_labeled_observations` check would fail immediately regardless of any
feature-parity outcome, making a full preflight run structurally uninformative for them.

**Basketball**: 12 markets seeded (including the 5 quarter/half-winner markets built in Phase 5B
with real resolvers), **zero** `prediction_outcomes` for every one — no bootstrap prediction run has
ever executed against basketball fixtures, so no labeled training data exists at all, regardless of
feature availability. **NOT READY.**

**Baseball**: 6 markets seeded, **zero** `prediction_outcomes` for every one, same reason. **NOT
READY.**

**Table tennis**: 6 markets seeded, **zero** `prediction_outcomes**, no real provider or data source
exists (unchanged since Phase 5B/6/7). **UNSUPPORTED**, per this initiative's own standing rule.

No market outside the 14 football markets in §4 has any real chance at readiness this phase — this
was confirmed by direct query rather than assumed.

---

## 9. Data Sufficiency (Part 11)

Direct query, `prediction_outcomes` joined through `predictions.market_id`, grouped by market —
the authoritative count of real, resolved training labels per market (not merely fixture count):

```
football.correct_score               828
football.away_clean_sheet             824
football.home_clean_sheet             824
football.away_team_total_goals        823
football.away_win_to_nil              823
football.home_team_total_goals        823
football.home_win_to_nil              823
football.total_goals_over_under       823
football.total_goals_over_under_0_5   823
football.total_goals_over_under_1_5   823
football.total_goals_over_under_3_5   823
football.total_goals_over_under_4_5   823
football.match_winner                 658
football.both_teams_to_score          653
[every other market — basketball(12), baseball(6), table_tennis(6),
 football.{first_half_winner,second_half_winner,first_half_goals,
 first_half_both_teams_to_score,match_result}]                        0
```

All 14 candidate markets clear the `sufficient_labeled_observations` minimum (30) by a wide margin
— fixtures, not labels, was never the bottleneck for these 14. `required_feature_coverage_acceptable`
is where the real constraint lives (§5): the feature exists in the schema and is correctly required,
but the source data it depends on has never been legitimately collected.

---

## 10. Provenance Analysis (Part 12)

Confirmed, direct query:

- `sync_runs.trigger` distribution: `backfill: 1` (Phase 8's single English League Two import run),
  `live: 8`, `live_scheduled: 2`, `manual: 24`, `scheduled: 370` — Phase 8's historical import
  remains the only `backfill`-triggered run, unchanged and correctly isolated from
  `live_scheduled`.
- No `lineups`/`transfers` row was ever misclassified as `VERIFIED_PRE_MATCH` — confirmed 100% are
  `UNKNOWN_AVAILABILITY_TIME` (§5); nothing from Phase 8's backfill or any other phase has leaked
  into that classification.
- `models.provenance_status`: all 47 rows show `PROVENANCE_UNVERIFIED` — a pre-existing state,
  unrelated to and unaffected by this phase's read-only activity; recorded here for completeness,
  not investigated further since it does not bear on any of the 14 candidate markets' blocking
  checks.

No provenance semantics were touched, weakened, or reclassified this phase.

---

## 11. Leakage Analysis (Part 13)

Since zero markets reached READY, no market was carried into a leakage-specific inspection beyond
what the official preflight itself already checks: `intelligence_feature_leakage_safe` **passes**
for all 14 candidate markets (no required feature is classified `POST_MATCH_ONLY`), and
`temporal_split_valid`/`temporal_reference_present` both **pass** for all 14 (real chronological
`TIME_SERIES_SPLIT` dry runs succeed, every sample carries a real `reference_time`). No further
action was warranted or taken.

---

## 12. Code Changes

**None.** Both universal blockers (§5, §6) were traced to root cause and determined to be legitimate
— an intentional, already-documented safety gate compounded by a real, currently-irresolvable data
deficit, and the correct expected state given no training run has ever legitimately executed. No
fix exists that would not either fabricate data, weaken a deliberately-designed gate, or persist
provenance disconnected from a real training decision — all explicitly prohibited by this phase's
own rules.

---

## 13. Tests

No code changed, so no new tests were required. Existing suite re-run in full to confirm zero
regressions from this phase's read-only activity (§16).

---

## 14. Database Delta

**Zero.** Direct re-snapshot after all Phase 9 activity is byte-for-byte identical to the baseline
(§3): every table's row count is unchanged, and the champion_set_hash is identical:
`cc5deabbfdb7d9e709d70bbaf885c199dd66306ca35b46f0ec5d028310541312` (19 champions, unchanged).

---

## 15. Champion Safety (Part 19)

| Check | Result |
|---|---|
| Champion count | 19 → 19, unchanged |
| Champion IDs / hashes | `champion_set_hash` identical before/after |
| predictions | 12,436 → 12,436, unchanged |
| prediction_outcomes | 11,194 → 11,194, unchanged |
| calibration_reports | 0 → 0, unchanged |
| datasets | 0 → 0, unchanged |

No unexpected mutation. No investigation triggered.

---

## 16. Final Regression Suite Result

Real, complete run (`.venv/Scripts/python -m pytest -q`, fresh `TITANIQ_ENCRYPTION_KEY`,
`TITANIQ_REDIS_URL=redis://127.0.0.1:6379/0`, no filtering), run after all Phase 9 investigation:

```
2423 passed, 58 skipped, 4 warnings in 646.52s (0:10:46)
```

Baseline (Phase 8 close): 2,423 passed / 58 skipped / 0 failed. **Byte-identical** — confirms no
regressions, exactly as expected since no code was changed this phase. The 4 warnings are the same
pre-existing third-party deprecation notices (`starlette.testclient`/`shap` colormap API) seen in
every prior phase's run.

---

## 17. Training Authorization Status

**NOT AUTHORIZED. NOT READY.**

## 18. Remaining Blockers

1. **Lineup/transfer continuity data deficit** (universal, all 14 candidate markets): zero
   `VERIFIED_PRE_MATCH` lineup or transfer records exist anywhere in `dev.db`. The only path to
   that classification is a live, near-kickoff `LIVE_SCHEDULED` sync running on a real schedule —
   which requires Celery Beat, explicitly out of scope/prohibited this phase. This will resolve
   naturally, over real time, once Celery Beat is authorized to run and enough future fixtures pass
   through their pre-kickoff window while genuinely synced.
2. **No durable dataset commitment exists for any market** — correct, expected, given no training
   run has ever legitimately executed. Resolves automatically as the first step of a real,
   authorized training run (`ScheduledRetrainingOrchestrator._build_validate_approve_dataset`),
   not before.
3. **Historical odds** (`market_lines`) remain unimported — not currently blocking any candidate
   market, but a real, documented, unbuilt opportunity from Phase 8 (§7).
4. **Basketball/baseball/table_tennis**: zero labeled predictions exist for any market in these
   sports — no bootstrap prediction run has ever executed for basketball/baseball, and no real data
   source exists for table tennis (unchanged from every prior phase).

## 19. Recommended Next Phase

Given blocker #1 is the true long pole and cannot be resolved by code changes, the honest
recommendation is either: (a) an explicit, scoped **Celery Beat activation phase** — deliberately
out of every prior phase's scope, but the only real path to ever satisfying the lineup/transfer
continuity requirement for these 14 markets — or (b) revisit whether `is_required=True` for
lineup/transfer-continuity on these 14 markets should be reconsidered given the codebase's own
architecture may never accumulate enough real pre-match observations to unblock them within a
practical timeframe; that reconsideration is a genuine product/architecture decision, not a bug fix,
and needs explicit human authorization rather than being made unilaterally inside a readiness-audit
phase.
