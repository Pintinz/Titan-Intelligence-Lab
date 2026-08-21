# POST-M24 Phase 11 — Full Multi-Sport Model Reset & Clean Retraining

**Date:** 2026-08-16
**Scope:** Deliberate model-generation reset — archive/retire the entire existing prediction/model
state across football, basketball, and baseball; rebuild training data from the current data fabric
via the existing backfill pipeline; retrain every market that legitimately qualifies; leave the rest
honestly blocked. Table tennis stays unsupported.

---

## Executive Summary

**The reset is complete. The predicted risk materialized exactly as flagged before starting: of 43
markets, only 5 came back READY_FOR_TRAINING after the reset — all 5 basketball segment-winner
markets already trained in the prior session. All 14 previously-working football markets and all
2 previously-working baseball/basketball moneyline-adjacent markets are now legitimately
BLOCKED_BY_DATA, for the same root cause already documented this session: `lineup_continuity`/
`transfer_activity` have 0% real coverage platform-wide, and the only legitimate path to real
coverage is a live, near-kickoff Celery-scheduled sync — explicitly prohibited this phase, same as
every prior phase.**

This is not a failure of execution — every step of the reset itself succeeded cleanly (snapshot,
retire, archive, delete, rebuild, retrain, regression). It is an honest, correctly-reported outcome:
**football went from 19 real Champions to 0**, because the reset discarded the only labeled training
universe football had (its 12,436 real predictions/11,194 real outcomes) and nothing about the
underlying lineup/transfer data gap changed in the meantime. The user explicitly authorized
proceeding with this understood risk before the reset began.

**Net result: 5 real Champions survive the reset (down from 26), all basketball. Football and
baseball currently have zero live-serving Champions.**

---

## Model Reset Rationale

Per the Phase 11 directive: the existing football prediction/outcome history was to be treated as
belonging to a prior model-generation state and not reused as the new training universe, regardless
of whether a specific defect in that data could be named. This was executed as specified, using only
existing architecture mechanisms — no new archival mechanism was invented.

---

## Database Snapshot

Full recoverable export taken before any mutation, to
`C:\Users\hp\AppData\Local\Temp\claude\...\scratchpad\phase11_snapshot\` (full JSON row dumps):

| Table | Rows exported |
|---|---|
| `predictions` | 15,110 |
| `prediction_outcomes` | 13,868 |
| `datasets` | 33 |
| `models` | 63 |
| `calibration_reports` | 0 |

Reference baselines recorded for every table required to stay untouched (fixtures, matches, teams,
competitions, seasons, provider_ref_index, feature_definitions, feature_values_offline, lineups,
transfers, news_articles, news_events) — verified identical at the end of the phase (see Database
Delta).

---

## Existing Prediction Archive/Delete

Used only existing lifecycle mechanisms, per the explicit "do not invent a second archival
mechanism" instruction:

- **Models**: `ModelRegistryService.retire()` (existing `RETIRED` status) — **49 models retired**
  (26 champion + 23 candidate → all retired; 14 already-retired models untouched). Final: 63/63
  models `retired` at the moment of reset.
- **Datasets**: `DatasetRegistryService.archive()` (existing `ARCHIVED` status) — **33/33 datasets
  archived**.
- **Predictions / PredictionOutcomes**: no archive status exists for these entities anywhere in the
  schema (`PredictionStatus` is only `DRAFT`/`PUBLISHED`). Per the spec's own instruction, inventing
  an `archived` flag that doesn't exist in the architecture would itself be "a second archival
  mechanism" — so, having already taken the full recoverable snapshot above, these were deleted
  directly: **15,110 → 0 predictions, 13,868 → 0 prediction_outcomes**.

---

## Football Reset

19 Champions retired, 12,436 predictions + 11,194 outcomes removed from active state (recoverable
from snapshot). Training data rebuilt from scratch using the same real, already-proven backfill
mechanism this codebase uses everywhere (real fixture → real feature snapshot → real resolver
applied to the real final score → real `Prediction`/`PredictionOutcome` pair — never a fabricated
value), via the 4 existing scripts that together cover exactly the 14 markets that were previously
trained:

| Script | Markets covered | Predictions rebuilt |
|---|---|---|
| `backfill_match_winner_training_data.py` | football.match_winner | 652 |
| `backfill_both_teams_to_score_training_data.py` | football.both_teams_to_score | 652 |
| `backfill_correct_score_training_data.py` | football.correct_score | 823 |
| `backfill_line_aware_markets_training_data.py` | total_goals_over_under ×5, home/away_team_total_goals, home/away_clean_sheet, home/away_win_to_nil | 823 each (11 markets) |

**Total: 11,180 fresh football predictions/outcomes rebuilt — closely matching pre-reset volume
(11,194), since both are drawn from the identical real fixture/feature data.** The 4 markets with no
dedicated backfill script (`first_half_both_teams_to_score`, `first_half_goals`, `first_half_winner`,
`second_half_winner`) were never backfilled even before the reset — confirmed via the script
inventory, not assumed — so this is an unchanged, pre-existing gap, not something the reset made
worse.

**Post-reset audit of all 19 football markets**: 0/19 READY. All 18 non-deprecated markets blocked
on `training_inference_feature_parity` + `required_feature_coverage_acceptable` (+
`dataset_provenance_persisted` for markets with no dataset yet built this generation) — the exact
`lineup_continuity`/`transfer_activity` 0%-coverage blocker documented in Phase 10/10B, reproduced
identically after the reset. `football.match_result` (deprecated) blocked on
`sufficient_labeled_observations` — no backfill script ever targeted this legacy market.

**Result: football has 0 Champions after the reset (down from 19).**

---

## Basketball Reset

7 previously-trained basketball Champions retired (6 segment-winner markets + the earlier session's
work). Training data for the 9 resolvable basketball/baseball markets rebuilt via the existing
`backfill_secondary_sport_training_data.py` (same script built in this session, re-run from scratch
against the now-empty tables):

| Market | Predictions rebuilt |
|---|---|
| basketball.moneyline | 0 (0% odds-feature coverage, unchanged) |
| basketball.first_half_winner | 231 |
| basketball.second_half_winner | 231 |
| basketball.q1_winner | 231 |
| basketball.q2_winner | 231 |
| basketball.q3_winner | 231 |
| basketball.q4_winner | 231 |

**Post-reset audit**: 5/7 resolvable markets READY (q1_winner, q2_winner, q3_winner, q4_winner,
second_half_winner). All 5 retrained from scratch and promoted new real Champions via
`ScheduledRetrainingOrchestrator`'s bootstrap path (no prior Champion existed post-retirement, so
this is legitimately "first training for this generation," not a replacement decision):

| Market | New Champion algorithm |
|---|---|
| basketball.q1_winner | svm |
| basketball.q2_winner | lightgbm_gbm |
| basketball.q3_winner | lightgbm_gbm |
| basketball.q4_winner | ridge |
| basketball.second_half_winner | logistic_regression |

**New finding, unrelated to the reset**: `basketball.first_half_winner` — structurally identical to
its 5 READY siblings (231 samples, same resolver, same fixture data) — is blocked on
`training_inference_feature_parity`/`required_feature_coverage_acceptable`. Root cause: it still
carries a stale *required* mapping to the old team-scoped `basketball.team.form_points_last5`
feature (superseded everywhere else by the fixture-scoped `form_points_diff_last5` per the
documented Phase 5A fix), left behind because the market seeder is insert-only and never retracts an
old mapping. This is a genuine, pre-existing architecture defect that happened to surface now that
this market is otherwise ready — **not fixed here** (out of scope for a reset; fixing it would be
scope creep into a schema/mapping change mid-phase), reported as found.

Other 6 basketball markets (moneyline, point_spread, game_total_points, team_total_points,
race_to_20_points, player_points_prop) remain `BLOCKED_BY_DATA`/`BLOCKED_BY_ARCHITECTURE`, unchanged
from Phase 10's findings — no resolver exists for 5 of them, and moneyline lacks real odds coverage.

---

## Baseball Reset

1 previously-trained Champion (`baseball.first_five_innings_winner`) retired. Training data rebuilt
(1,288 predictions, matching pre-reset volume exactly). Post-reset audit: **BLOCKED** on
`training_inference_feature_parity`/`required_feature_coverage_acceptable` — same lineup/transfer
gap as football, now also affecting this market where it previously did not block it. Verified via
direct feature-mapping inspection this is the same universal gap, not a baseball-specific defect.

**Result: baseball has 0 Champions after the reset (down from 1).**

Other 5 baseball markets (moneyline, run_line, total_runs, team_total_runs,
pitcher_strikeouts_prop) remain `BLOCKED_BY_DATA`/`BLOCKED_BY_ARCHITECTURE`, unchanged — no resolver
exists for 4 of them, moneyline lacks real odds coverage.

---

## Table Tennis Status

**UNSUPPORTED, unchanged.** No real provider adapter exists for this sport anywhere in the
codebase (confirmed via the same provider registry already audited in Phase 10) — mock-only. No
data was fabricated. 0/6 table tennis markets touched by this reset (they had 0 predictions before
and after).

---

## Injury / Lineup / Transfer / News Pipeline — Investigated, Unchanged

Re-verified against the current, post-reset `dev.db` (not assumed from memory):

| Pipeline | Real rows | VERIFIED_PRE_MATCH rows | Status |
|---|---|---|---|
| Lineups | 4 | 0 | Unchanged from Phase 10 — no live-scheduled sync has run (Beat stayed stopped, as required) |
| Transfers | 308 | 0 | Unchanged |
| News articles | 402 | — | Unchanged |
| News events | 77 | 0 `VERIFIED_PRE_MATCH` | Unchanged |

The reset touched none of these tables (confirmed identical before/after in the Database Delta
section). This is the single root cause behind every football and baseball market's block — real,
structural, and outside this phase's authorized scope to fix (would require Celery Beat, explicitly
prohibited).

---

## Temporal Validation / Leakage / Training-Inference Parity

- **Temporal validation**: PASS. Every backfilled sample's `reference_time` is the real fixture's own
  real evaluation timestamp — no post-match information used for a pre-match feature at any point.
- **Leakage**: PASS. No feature calculator was modified; the same leakage-safe rolling-window
  calculators (`Match.started_at < before`) already verified safe in Phase 9B/10 are unchanged.
- **Training/inference parity**: the actual, correctly-reported **FAIL** for all 18 football markets
  and `baseball.first_five_innings_winner` — this is not a bug, it is the honest state of the
  platform's real data coverage for gated intelligence features, as designed.

---

## Dataset Rebuild

All 33 pre-reset datasets archived (never reused). 5 new datasets built and approved this generation
— one per newly-trained basketball market — via the real `DatasetBuilder` → `DatasetRegistryService`
pipeline inside `ScheduledRetrainingOrchestrator._build_validate_approve_dataset()`, the existing,
unmodified mechanism.

---

## Training Preflight

Full 43-market `TrainingPreflightService` audit re-run fresh against the rebuilt data:
**5/43 READY_FOR_TRAINING.**

---

## Training

`ScheduledRetrainingOrchestrator._check_and_retrain()` called **only** for the 5 markets that
independently passed preflight — never the full 43-market sweep, guaranteeing zero risk to any
unrelated market. All 5 real algorithms trained via the existing `AutomaticModelSelectionService`
11-algorithm roster.

---

## Model Evaluation / Registration / Champion Replacement

All 5 new candidates cleared real held-out evaluation and were auto-promoted straight to CHAMPION via
the orchestrator's existing bootstrap-exception path — legitimate here because no Champion existed
for any of these 5 markets post-retirement (this is "first training for this generation," not a
replacement decision requiring human sign-off). No failed model was promoted; no gate was weakened.

---

## New Prediction Generation

Real predictions generated via the production `PredictionCacheService.get_or_generate()` — the
identical code path `/api/v1/predictions/generate` uses — for all 5 new Champions against a real
completed basketball fixture, confirming true end-to-end serving (never a manually-inserted
Prediction row):

| Market | Value | Probability |
|---|---|---|
| basketball.q1_winner | HOME_WIN | 0.536 |
| basketball.q2_winner | AWAY_WIN | 0.789 |
| basketball.q3_winner | HOME_WIN | 0.567 |
| basketball.q4_winner | HOME_WIN | 0.426 |
| basketball.second_half_winner | HOME_WIN | 0.575 |

All 5 returned `status=published`. (Unrelated, pre-existing infra note surfaced during this call: the
real Gemini adapter's configured model, `gemini-2.0-flash`, returned HTTP 404 "no longer available" —
the system correctly and gracefully fell back to the mock explainability adapter, exactly as
designed; not something this phase is authorized to fix, noted for visibility.)

---

## API / Frontend / Cache / Quota Verification

- **Backend**: UP throughout (confirmed before and after).
- **Frontend**: UP throughout.
- **Redis**: UP throughout; cache/quota/circuit-breaker were never bypassed — every write in this
  phase went through the existing repository/service layer, no raw provider SDK calls were made.
- **External API calls**: 0 this phase (no provider sync was triggered — the entire reset/rebuild
  operated on data already present in `dev.db`).
- **Gemini calls**: 5 (one per live prediction generated), all correctly cache/quota-governed,
  gracefully degraded to mock on the real 404 above.

---

## Database Delta

| Table | Before | After | Delta |
|---|---|---|---|
| `models` | 63 (26 champion / 23 candidate / 14 retired) | 68 (5 champion / 63 retired) | Net -21 champion, +5 new challenger→champion, +49 retired |
| `datasets` | 33 (7 approved / 26 draft) | 38 (5 approved / 33 archived) | +5 new, all 33 old archived |
| `predictions` | 15,110 | 13,859 | -1,251 net (old universe deleted, new universe rebuilt smaller — football's 4 unresolvable markets and basketball/baseball's unresolvable markets no longer contribute) |
| `prediction_outcomes` | 13,868 | 13,854 | Same shape |
| `calibration_reports` | 0 | 0 | Unchanged — no unauthorized calibration ran |
| `fixtures` | 7,825 | 7,825 | **0 — unchanged** |
| `matches` | 844 | 844 | **0 — unchanged** |
| `teams` | 243 | 243 | **0 — unchanged** |
| `competitions` | 7 | 7 | **0 — unchanged** |
| `seasons` | 22 | 22 | **0 — unchanged** |
| `provider_ref_index` | 8,570 | 8,570 | **0 — unchanged** |
| `feature_definitions` | 47 | 47 | **0 — unchanged** |
| `feature_values_offline` | 110,962 | 110,962 | **0 — unchanged** |
| `lineups` | 4 | 4 | **0 — unchanged** |
| `transfers` | 308 | 308 | **0 — unchanged** |
| `news_articles` | 402 | 402 | **0 — unchanged** |
| `news_events` | 77 | 77 | **0 — unchanged** |

No raw historical evidence was touched, exactly as required.

---

## Regression Tests

Full backend suite re-run after the reset: **2,426 passed, 58 skipped, 0 failed** — byte-identical to
the pre-reset baseline. Zero regressions.

---

## Final Market Matrix

| Sport | Market | Resolver | Data | Injuries | Lineups | Transfers | News | Odds | Labels | Dataset | Parity | Ready | Trained | Champion |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Football | correct_score | Real (grid) | 823 samples | N/A | 0% | 0% | Optional, 0% | N/A | Real | Fresh, archived-history | FAIL | No | No | None |
| Football | total_goals_over_under (×5) | Real | 823 each | N/A | 0% | 0% | Optional, 0% | N/A | Real | Fresh | FAIL | No | No | None |
| Football | home/away_team_total_goals | Real | 823 each | N/A | 0% | 0% | Optional | N/A | Real | Fresh | FAIL | No | No | None |
| Football | home/away_clean_sheet | Real | 823 each | N/A | 0% | 0% | Optional | N/A | Real | Fresh | FAIL | No | No | None |
| Football | home/away_win_to_nil | Real | 823 each | N/A | 0% | 0% | Optional | N/A | Real | Fresh | FAIL | No | No | None |
| Football | match_winner | Real (3-way) | 652 | N/A | 0% | 0% | Optional | Required, passing | Real | Fresh | FAIL | No | No | None |
| Football | both_teams_to_score | Real | 652 | N/A | 0% | 0% | Optional | Required, passing | Real | Fresh | FAIL | No | No | None |
| Football | first_half_both_teams_to_score / first_half_goals / first_half_winner / second_half_winner | None | 0 | N/A | 0% | 0% | N/A | N/A | N/A | None | FAIL | No | No | None |
| Football | match_result (deprecated) | Real (3-way) | 0 | N/A | N/A | N/A | N/A | N/A | N/A | None | FAIL | No | No | None |
| Basketball | q1/q2/q3/q4_winner | Real | 231 each | N/A | N/A | N/A | N/A | N/A | Real | Fresh, approved | **PASS** | **Yes** | **Yes** | **Yes (new)** |
| Basketball | second_half_winner | Real | 231 | N/A | N/A | N/A | N/A | N/A | Real | Fresh, approved | **PASS** | **Yes** | **Yes** | **Yes (new)** |
| Basketball | first_half_winner | Real | 231 | N/A | N/A | N/A | N/A | N/A | Real | Fresh | FAIL (stale mapping bug) | No | No | None |
| Basketball | moneyline | Real | 0 | N/A | N/A | N/A | N/A | Required, 0% | — | None | FAIL | No | No | None |
| Basketball | point_spread / game_total_points / team_total_points / race_to_20_points / player_points_prop | None | 0 | N/A | N/A | N/A | N/A | N/A | N/A | None | FAIL | No | No | None |
| Baseball | first_five_innings_winner | Real | 1,288 | N/A | N/A | N/A | N/A | N/A | Real | Fresh | FAIL | No | No | None |
| Baseball | moneyline | Real | 0 | N/A | N/A | N/A | N/A | Required, 0% | — | None | FAIL | No | No | None |
| Baseball | run_line / total_runs / team_total_runs / pitcher_strikeouts_prop | None | 0 | N/A | N/A | N/A | N/A | N/A | N/A | None | FAIL | No | No | None |
| Table Tennis | all 6 markets | None | 0 | N/A | N/A | N/A | N/A | N/A | N/A | None | N/A | No | No | None — **UNSUPPORTED** |

---

## Remaining Blockers

1. **Universal `lineup_continuity`/`transfer_activity` 0% coverage** — blocks 18 football markets +
   `baseball.first_five_innings_winner`. Only fixable by a real, live-scheduled sync running over
   real time (Celery Beat), out of scope this phase and every prior phase.
2. **`basketball.first_half_winner` stale required-feature mapping** — a real, small, self-contained
   defect (team-scoped feature still required, structurally invisible to fixture-scoped resolution).
   Fixable independently of the reset; not touched here per scope discipline.
3. **9 basketball/baseball markets with no resolver** (point_spread, totals, props, run_line, etc.) —
   need real stored betting lines or player-level box-score data this platform doesn't ingest.
   Unchanged from Phase 10.
4. **2 moneyline markets (basketball, baseball)** — blocked on 0% real odds-feature coverage; no
   odds provider wired for these sports. Unchanged from Phase 10.
5. **Table tennis** — no real provider exists. Unchanged.

---

## FINAL STATUS

```
PHASE 11 STATUS: COMPLETE

MODEL RESET: COMPLETE

OLD PREDICTIONS:
Before: 15,110
Archived/deleted: 15,110 (deleted, full snapshot taken first — no archive status exists for this entity)
After: 0

OLD OUTCOMES:
Before: 13,868
Archived/deleted: 13,868 (deleted, full snapshot taken first)
After: 0

OLD CHAMPIONS:
Before: 26 (19 football, 6 basketball, 1 baseball)
Retired/replaced: 26 retired (plus 23 candidates retired alongside)
Remaining: 0 of the original 26

NEW DATASETS: 5

NEW MODELS: 5

NEW CHAMPIONS: 5 (basketball.q1_winner, q2_winner, q3_winner, q4_winner, second_half_winner)

NEW PREDICTIONS: 13,859 (13,854 real backfilled training data + 5 real live-generated via PredictionCacheService)

FOOTBALL: 0/19 markets ready. 18 blocked on lineup/transfer feature-parity (same root cause as pre-reset). 1 deprecated market blocked on insufficient labels (unchanged, never had a backfill path).

BASKETBALL: 5/12 markets trained (q1-q4_winner, second_half_winner — all new real Champions). 1 blocked by a newly-surfaced stale-mapping defect (first_half_winner). 6 blocked by missing resolver/odds data (unchanged from Phase 10).

BASEBALL: 0/6 markets ready. first_five_innings_winner now blocked on the same lineup/transfer gap that didn't block it pre-reset (real, correctly-reported consequence of discarding the old training universe). 5 blocked by missing resolver/odds data (unchanged).

TABLE TENNIS: UNSUPPORTED — no real provider exists. Unchanged.

INJURY DATA: Unchanged — real pipeline exists, 0 real injury rows currently in dev.db, not touched this phase.

LINEUP DATA: Unchanged — 4 real rows, 0 VERIFIED_PRE_MATCH. Root cause of every football/baseball block.

TRANSFER DATA: Unchanged — 308 real rows, 0 VERIFIED_PRE_MATCH.

NEWS: Unchanged — 402 real articles, 77 real events, 0 VERIFIED_PRE_MATCH.

NEWS TEMPORAL VALIDATION: PASS

LEAKAGE: PASS

TRAINING/INFERENCE PARITY: FAIL for 19 markets (correctly reported, not weakened) / PASS for the 5 trained markets

DATASET PROVENANCE: PASS for the 5 trained markets (real datasets built, validated, approved) / FAIL (correctly) for every other market — no dataset exists yet because no training has legitimately run for them

CACHE: PASS — Redis cache/quota/circuit-breaker never bypassed

QUOTA: PASS — 0 external provider API calls this phase; 5 Gemini calls, correctly governed, gracefully degraded on a real upstream 404

CHAMPION PROMOTION: PASS — all 5 new Champions promoted only after real evaluation via the existing bootstrap-exception path; no failed model promoted

FRONTEND: UP

BACKEND: UP

REDIS: UP

DATABASE: fixtures/matches/teams/competitions/seasons/provider_ref_index/feature_definitions/feature_values_offline/lineups/transfers/news_articles/news_events all delta 0. predictions -1,251 net, outcomes -14 net, models +5, datasets +5 (all reflecting authorized reset/rebuild, not unintended mutation)

EXTERNAL API CALLS: 0

GEMINI CALLS: 5

TESTS: 2,426 passed / 58 skipped / 0 failed

REGRESSIONS: 0

CELERY BEAT: NOT STARTED

CALIBRATION: NO UNAUTHORIZED CALIBRATION

RETRAINING: ONLY AUTHORIZED FULL RESET TRAINING

REPORT: backend/docs/post_m24_phase11_full_multisport_model_reset_report.md
```
