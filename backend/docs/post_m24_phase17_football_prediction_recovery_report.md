# Post-M24 Phase 17 — Multi-Sport Prediction Recovery Report

Status: **COMPLETE** (per this segment's governing charter's 15 Objectives). Football's
Cluster A (required-feature over-declaration) and Cluster B (never-bootstrapped
dataset) are both fixed and live-verified. Basketball/baseball's analogous
stale-mapping and never-bootstrapped-dataset bugs are fixed and live-verified for
every market where a real resolver exists. Markets with no real resolver
(`BLOCKED_BY_ARCHITECTURE`) were independently audited per sport and left
untouched — no resolver was fabricated. Table tennis is confirmed
`INSUFFICIENT_VERIFIED_DATA` (zero real fixtures ever ingested). The Gemini
contextual-reconsideration/deterministic-fusion charter remains **not started** —
see "Scope note" at the end of this report; per the charter's own strict stop
condition, it is explicitly out of scope for this pass.

## 1. Executive summary

The production error `"Insufficient historical data to generate a production-quality
prediction for '<market>' yet"` was appearing across most football, basketball, and
baseball markets. Diagnostic work found this was **not** one shared root cause but
several distinct, independently-verified failure classes, repeating across sports with
the same underlying shapes but different concrete causes each time:

- **Cluster A (football, 11→14 markets)**: real Champion + real dataset existed, but
  `lineup_continuity`/`transfer_activity`/`news.*_impact` features were declared
  `required` while being structurally 0%-populated (their writers only ever fire near
  real kickoff or on live news ingestion — conditions this platform's backfilled data
  never exercised). **Fixed in the prior segment of this session.**
- **Cluster B (football, 2 markets — `match_winner`, `both_teams_to_score`)**: 652 real
  resolved outcomes existed for each, but the market had simply never been through the
  bootstrap-train-and-promote flow — `DatasetBuilder.build()` was proven (via an
  instrumented diagnostic mirroring its exact logic) to build a full, valid dataset with
  zero rejections; the bug was pure orchestration, not data quality. **Fixed this
  segment** — bootstrapped via `ScheduledRetrainingOrchestrator._check_and_retrain`,
  real Champions now serving (`logistic_regression` v3, `svm` v3).
- **Cluster C (football, 4 markets)**: zero outcomes, no provider adapter parses
  football half-time scores — genuinely `BLOCKED_BY_ARCHITECTURE`, unchanged.
- **Basketball/baseball stale-mapping bug**: a POST-M24 Phase 5A migration swapped
  every market's required feature from a team-scoped signal
  (`{sport}.team.form_{points,runs}_last5`) to a fixture-scoped one
  (`{sport}.fixture.form_{points,runs}_diff_last5`), because a team-scoped feature is
  structurally invisible to a fixture-scoped prediction request. The market-seeding
  spec was updated, but `_seed_market()`'s create-only seeding never retroactively
  updates an already-persisted `feature_market_mappings` row — the exact same
  create-only-seeding class of bug as football's Cluster A, independently confirmed by
  reading `basketball/market_seeding.py`'s own Phase 5A docstring, not assumed from the
  football fix. `basketball.first_half_winner` had already been fixed for this in an
  earlier milestone (task #488); this segment extended the identical, already-proven
  fix to every sibling market that never got it.
- **Basketball/baseball moneyline overround bug**: `{sport}.moneyline` requires
  `{sport}.market.overround`, which has permanent 0% real coverage — no odds provider
  is wired for basketball or baseball (confirmed via
  `scripts/backfill_secondary_sport_training_data.py`'s own docstring). This silently
  meant the historical-prediction backfill script's own honest "skip if missing
  required feature" logic never created a single `Prediction` row for moneyline on
  either sport — a genuine chicken-and-egg: no predictions → no outcomes → no dataset →
  never trainable, despite the fixture-diff feature being a real, populated signal on
  its own.
- **Basketball/baseball "real data but never bootstrapped" markets**: 5 basketball +
  4 baseball markets had real, complete datasets (231–1288 samples) but had simply
  never been run through the bootstrap orchestrator — the only preflight failure was
  `dataset_provenance_persisted` (a known, deliberate, already-documented architectural
  limitation — `DatasetRepositoryPort` is in-memory-only by design, ADR-008, M19 §13 —
  unrelated to whether the orchestrator's own bootstrap path can train on the data).
- **Table tennis**: zero real fixtures/predictions/outcomes exist anywhere in the
  database for any of its 6 markets — confirmed via direct query, not assumed. No
  provider has ever synced a table-tennis fixture. Correctly classified
  `INSUFFICIENT_VERIFIED_DATA`, no fix attempted, no data fabricated.
- **Markets genuinely `BLOCKED_BY_ARCHITECTURE`** (basketball: `point_spread`,
  `team_total_points`, `race_to_20_points`, `player_points_prop`; baseball: `run_line`,
  `team_total_runs`, `pitcher_strikeouts_prop`): no real outcome resolver exists for
  any of them — each would require a stored betting line/prop threshold or
  player-level box-score stats this platform doesn't ingest. This classification
  already existed, independently documented in the backfill script's own docstring
  from an earlier milestone; this segment verified it still holds and did **not**
  attempt to fabricate a resolver to force these markets trainable.

`football.match_result` is `status=deprecated` and correctly excluded from all counts.

## 2. Original production error

```
"Insufficient historical data to generate a production-quality prediction for
'<market>' yet — check back once enough verified completed matches have
been ingested to train a model."
```

Live-reproduced in the browser for `football.match_winner`,
`football.first_half_both_teams_to_score`, and `basketball.moneyline` (409 responses,
`NoChampionModelError` translation). A *different* honest 409
(`"market '<key>' is missing required features: ..."`) was reproduced for
`football.total_goals_over_under_1_5`, `football.correct_score`, and
(this segment) `football.match_winner` against a specific fixture whose
`form_shots_on_target_diff_last5` stat differential was never backfilled — a
per-fixture data-availability gap distinct from the systemic Cluster A/B bugs, not a
regression.

## 3. All markets audited (54, authoritative)

Queried `prediction_markets` directly, not assumed:

- **Football**: 19 (18 active + `match_result`, deprecated)
- **Basketball**: 18
- **Baseball**: 11
- **Table tennis**: 6

## 4-5. Shared root causes and fixes — see §1 above and per-sport sections below.

## 6-13. Football coverage details (prior segment — unchanged, see original Phase 1 table)

| Market | Resolver | Outcomes | Samples | Feat | Dataset | Champ | Chal | Retired | Preflight |
|---|---|---|---|---|---|---|---|---|---|
| away_clean_sheet | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| away_team_total_goals | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| away_win_to_nil | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| both_teams_to_score | Y | 652 | 652 | 6 | Y | **1 (svm, v3)** | 0 | 3 | READY (fixed this segment) |
| correct_score | N* | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| first_half_both_teams_to_score | Y | 0 | 0 | 0 | N | 0 | 0 | 1 | BLOCKED_BY_ARCHITECTURE |
| first_half_goals | Y | 0 | 0 | 0 | N | 0 | 0 | 1 | BLOCKED_BY_ARCHITECTURE |
| first_half_winner | Y | 0 | 0 | 0 | N | 0 | 0 | 1 | BLOCKED_BY_ARCHITECTURE |
| home_clean_sheet | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| home_team_total_goals | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| home_win_to_nil | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| match_result | N | 0 | 0 | 0 | N | 0 | 0 | 1 | deprecated, excluded |
| match_winner | Y | 652 | 652 | 7 | Y | **1 (logistic_regression, v3)** | 0 | 3 | READY (fixed this segment) |
| second_half_winner | Y | 0 | 0 | 0 | N | 0 | 0 | 1 | BLOCKED_BY_ARCHITECTURE |
| total_goals_over_under | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| total_goals_over_under_0_5 | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| total_goals_over_under_1_5 | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| total_goals_over_under_3_5 | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |
| total_goals_over_under_4_5 | Y | 823 | 823 | 2 | Y | 1 | 3 | 3 | READY |

Football: **14/18 active markets TRAINED_AND_SERVING**, 4 `BLOCKED_BY_ARCHITECTURE`
(half-time markets, no provider parses football half-time scores).

## 14-25. Football statistical baseline / calibration / API / frontend — unchanged from prior segment (see git history of this file for full detail); `match_winner`/`both_teams_to_score` now additionally live-verified (§29 below).

## 26. Basketball — independent audit (Objective 5)

18 markets. **Before this segment**: 8 already `READY` (`first_half_winner`,
`game_total_points`, `q1_winner`, `q2_winner`, `q3_winner`, `q4_winner`,
`second_half_winner`, `game_total_points_prediction`).

**Root cause 1 — stale required-feature mapping** (confirmed by reading
`basketball/market_seeding.py`'s own Phase 5A docstring, not assumed from football):
`basketball.team.form_points_last5` remained `is_required=True` in the DB on
`moneyline`, `point_spread`, `player_points_prop`, `team_total_points`,
`race_to_20_points` — a team-scoped feature that is structurally invisible to a
fixture-scoped prediction request, exactly the migration `first_half_winner` had
already been fixed for (task #488). Fixed via `FeatureMarketMappingService.set_required(...,
False)` — the same already-proven mechanism, extended to the 5 markets that never got
it.

**Root cause 2 — moneyline's `overround` requirement**: `basketball.market.overround`
has 0% real coverage (no odds provider wired for basketball). Also demoted to
optional. This unblocked `scripts/backfill_secondary_sport_training_data.py`'s own
honest backfill logic, which had previously skipped every fixture for moneyline.
Re-ran the script: **231 real `Prediction`/`PredictionOutcome` pairs backfilled** for
`basketball.moneyline` from real historical fixtures (never fabricated — each pairs a
real fixture's real final score with a real feature snapshot).

**Bootstrap-trained this segment** (real data existed, market had simply never gone
through `ScheduledRetrainingOrchestrator`'s bootstrap path — the only preflight
blocker was the known, deliberate `dataset_provenance_persisted` limitation, ADR-008,
unrelated to bootstrap eligibility):

| Market | Samples | Champion (algorithm, version) |
|---|---|---|
| moneyline | 231 (post-backfill) | ridge, v2 |
| first_half_total_points | 231 | ridge, v2 |
| game_total_points_199_5 | 231 | xgboost_gbm, v2 |
| game_total_points_209_5 | 231 | random_forest, v2 |
| game_total_points_229_5 | 231 | xgboost_gbm, v2 |
| game_total_points_239_5 | 231 | elastic_net, v2 |

**Confirmed `BLOCKED_BY_ARCHITECTURE`, unchanged, no resolver fabricated**:
`point_spread`, `team_total_points`, `race_to_20_points`, `player_points_prop` — no
real outcome resolver exists (would need a stored betting line/prop threshold or
player-level box-score stats not ingested by this platform). Verified via
`outcome_resolution_service.py`'s `MARKET_OUTCOME_RESOLVERS`/`THREE_WAY_MARKET_RESOLVERS`
dicts — genuinely absent, not overridden.

Basketball: **14/18 markets TRAINED_AND_SERVING**, 4 `BLOCKED_BY_ARCHITECTURE`.

## 27. Baseball — independent audit (Objective 6)

11 markets. **Before this segment**: 2 already `READY` (`total_runs`,
`total_runs_prediction`).

Same two root causes as basketball, independently re-confirmed for baseball (not
assumed identical without checking): `baseball.team.form_runs_last5` stale-required on
`moneyline`, `run_line`, `team_total_runs`, `first_five_innings_winner`,
`pitcher_strikeouts_prop`; `baseball.market.overround` (0% coverage, no baseball odds
provider) required on `moneyline`. Both demoted to optional via the same
`set_required()` mechanism.

**`baseball.first_five_innings_winner` is a direct baseball analogue of football's
Cluster A**: it already had 1288 real outcomes and a real 1288-sample dataset — the
stale `team.form_runs_last5` requirement was purely blocking `TrainingPreflightService`,
not data availability. Fixing the mapping alone was sufficient to make it trainable.

Re-ran the backfill script after the `overround` fix: **1260 real `Prediction`/
`PredictionOutcome` pairs backfilled** for `baseball.moneyline` (1288 fixtures minus 28
genuine ties, which `_moneyline_home_win`'s resolver correctly leaves unresolved —
never fabricated a winner for a tie).

**Bootstrap-trained this segment**:

| Market | Samples | Champion (algorithm, version) |
|---|---|---|
| moneyline | 1260 (post-backfill) | ridge, v2 |
| first_five_innings_winner | 1288 | elastic_net, v3 |
| total_runs_6_5 | 1288 | svm, v2 |
| total_runs_7_5 | 1288 | ridge, v2 |
| total_runs_9_5 | 1288 | svm, v2 |
| total_runs_10_5 | 1288 | svm, v2 |

**Confirmed `BLOCKED_BY_ARCHITECTURE`, unchanged**: `run_line`, `team_total_runs`,
`pitcher_strikeouts_prop` — same "no resolver, would require fabricated line/player
stats" reasoning as basketball's blocked markets.

Baseball: **8/11 markets TRAINED_AND_SERVING**, 3 `BLOCKED_BY_ARCHITECTURE`.

## 28. Table tennis — classification (Objective 7)

Direct query confirms **zero real fixtures, zero completed matches, zero predictions**
anywhere in the database for `sport_code='table_tennis'`. No provider has ever synced a
table-tennis fixture into this platform. All 6 markets (`correct_score`,
`match_handicap`, `match_winner`, `race_to_11_points`, `set_winner`, `total_points`)
are classified `INSUFFICIENT_VERIFIED_DATA`. No fix attempted — this is a pure
data-source gap (no table-tennis provider integrated), not a bug in the prediction
pipeline. Fabricating fixtures or predictions for this sport would violate the
charter's explicit anti-fabrication rule; correctly left untouched.

## 29. Live verification (Objectives 4, 14)

Live-tested in the browser (Prediction Laboratory) after all fixes:

- **`football.match_winner`** (Arsenal vs Coventry City FC returned a per-fixture
  "missing required feature" 409 — a genuine, honest, per-fixture data gap, not a
  regression; a second fixture, Everton vs Crystal Palace, generated a complete real
  prediction: Everton 48% / Crystal Palace 30% / Draw 22%, real evidence
  (`form_possession_pct_diff +1.51`, `implied_probability_home +0.09`, etc.), and a real
  AI-generated narrative).
- **`basketball.moneyline`** (Boston Celtics vs Dallas Mavericks): real prediction,
  HOME 57% / AWAY 43%, real evidence (`form_points_diff_last5 +2.80`).

Both confirm the fixed markets serve genuine, non-fabricated predictions end-to-end,
not just a passing preflight check.

## 30. Historical data integration and rolling-feature chronology (Objectives 8-9)

**Historical data**: Football 7,829 fixtures, basketball/baseball fixture counts
consistent with the per-market sample counts above (231/1288 respectively per market
family). Table tennis: 0, confirmed (see §28).

**Rolling-feature chronology**: Spot-checked `feature_values_offline.as_of` against
each feature's fixture's `scheduled_at`. Basketball (`form_points_diff_last5`) and
baseball (`form_runs_diff_last5`) show **zero** `as_of > scheduled_at` violations
(3,651 and 16,339 rows respectively, all clean). Football's
`form_shots_on_target_diff_last5` showed 1,140 of 14,917 rows with `as_of` *after*
`scheduled_at` — investigated directly rather than assumed a leak: `as_of` is the
timestamp the feature was *computed* (a 2026-08-02 backfill run), not the point-in-time
validity boundary used for training splits. The actual leakage-relevant boundary is
each `Dataset` sample's own `reference_time`, which `TrainingPreflightService`'s
`temporal_split_valid` check (`TIME_SERIES_SPLIT` chronological-ordering verification,
Milestone 18) already enforces and which **passes on every market with real samples**
in this session's full audit — confirmed, not assumed. Not a leakage bug; a
deliberate, correct separation between "computed at" and "represents point-in-time
state as of."

## 31. Database row-delta report (Objective 13)

Snapshot taken before this segment's mutations:
`backend/dev.db.snapshot_before_phase17_bootstrap_2markets`. Compared against current
`dev.db`:

| Table | Before | After | Delta |
|---|---|---|---|
| fixtures | 7829 | 7829 | 0 |
| matches | 844 | 844 | 0 |
| teams | 243 | 243 | 0 |
| players | 100 | 100 | 0 |
| competitions | 7 | 7 | 0 |
| seasons | 22 | 22 | 0 |
| prediction_markets | 54 | 54 | 0 |
| prediction_outcomes | 23206 | 24697 | **+1491** |
| feature_definitions | 47 | 47 | 0 |
| feature_values_offline | 122541 | 122541 | 0 |
| datasets | 95 | 109 | **+14** |
| models | 134 | 148 | **+14** |
| experiments | 79 | 93 | **+14** |
| calibration_reports | 0 | 0 | 0 |
| predictions | 23217 | 24715 | **+1498** |
| market_lines | 6072 | 6072 | 0 |
| provider_ref_index | 8570 | 8570 | 0 |
| news_articles | 444 | 444 | 0 |
| news_events | 80 | 80 | 0 |
| injuries | 30 | 30 | 0 |
| transfers | 308 | 308 | 0 |
| player_statistics | 0 | 0 | 0 |
| feature_market_mappings | 213 | 213 | 0 (in-place `is_required` updates, not new rows) |

**Zero mutation to any raw-data table** (fixtures/teams/matches/competitions/seasons/
market_lines/provider_ref_index/news/injuries/transfers all delta 0). Every non-zero
delta traces to a legitimate, explainable action:

- **+14 datasets/models/experiments**: exactly one per bootstrap-trained market (2
  football + 6 basketball + 6 baseball = 14).
- **+1491 prediction_outcomes / +1498 predictions**: the two moneyline backfills (231
  basketball + 1260 baseball = 1491 outcomes, matching exactly; the 7-row predictions
  surplus over outcomes comes from the bootstrap orchestrator's own candidate-training
  process, not further backfill).
- **`feature_market_mappings` row count unchanged**: `set_required()` updates an
  existing mapping's `is_required` flag in place (same row ID), never inserts —
  confirmed by the zero delta despite 18 real flag flips (12 basketball/baseball +
  the football mapping fixes from the prior segment).

No fixture, team, match, competition, news, injury, or transfer record was created,
modified, or deleted at any point in this segment.

## 32. Backend test results (Objective 1, 14)

Full `pytest tests/unit` regression suite, run after all fixes in this segment:

```
2547 passed, 4 warnings in 560.45s (0:09:20)
```

**Zero failures.** Baseline before this segment's basketball/baseball work was
2547 passed / 0 failed (the prior segment's 4 test updates for the Milestone-16
override already included) — confirms this segment's basketball/baseball/table-tennis
work introduced zero regressions.

## 33. Remaining blocked markets (evidence-backed, final)

- **Football**: `first_half_winner`, `second_half_winner`, `first_half_goals`,
  `first_half_both_teams_to_score` — `BLOCKED_BY_ARCHITECTURE` (no provider parses
  football half-time scores).
- **Basketball**: `point_spread`, `team_total_points`, `race_to_20_points`,
  `player_points_prop` — `BLOCKED_BY_ARCHITECTURE` (no resolver; would need a stored
  betting line/prop threshold or player-level stats).
- **Baseball**: `run_line`, `team_total_runs`, `pitcher_strikeouts_prop` —
  `BLOCKED_BY_ARCHITECTURE`, same reasoning.
- **Table tennis**: all 6 markets — `INSUFFICIENT_VERIFIED_DATA` (zero real fixtures
  ingested for this sport).
- **`football.match_result`** — deprecated, correctly excluded.

None of these were forced trainable by fabricating data, weakening a gate, or
inventing a resolver. All 11 `BLOCKED_BY_ARCHITECTURE` markets require a genuinely new
ingestion/data capability (half-time score parsing, betting-line ingestion, or
player-level box-score stats) that is out of this charter's scope.

## 34. Recommended next action

1. **Table tennis**: integrate a real table-tennis data provider before any prediction
   work on this sport is possible — currently zero real data exists.
2. **Half-time score parsing** (football): would unblock 4 markets currently
   `BLOCKED_BY_ARCHITECTURE` — a genuine new ingestion capability, not a config fix.
3. **Betting-line ingestion** (basketball `point_spread`, baseball `run_line`) and
   **player-level box-score stats** (basketball `team_total_points`/`player_points_prop`,
   baseball `team_total_runs`/`pitcher_strikeouts_prop`) — each is a real, separate data
   source this platform has never ingested; scoping either is a dedicated future phase.
4. **Odds provider for basketball/baseball**: `market.overround` and
   `implied_probability_*` are registered `FeatureDefinition`s with zero real writer for
   these two sports (confirmed in this session's `docs/feature_coverage_report.md`) —
   wiring a real odds provider would strengthen `moneyline`'s signal beyond the single
   fixture-diff feature it currently trains on.
5. Gemini contextual-reconsideration + deterministic-fusion architecture remains
   genuinely unbuilt (see Scope note) — recommend scoping as its own dedicated phase
   once the quantitative layer above is fully settled.

---

## Scope note

This report now covers the completion of the governing charter's 15 Objectives
(football Cluster B fix, basketball/baseball independent audit and fix, table tennis
classification, historical-data/chronology verification, DB row-delta reporting,
non-regression re-verification, and this final report). The Gemini
contextual-reconsideration + deterministic-fusion layer from the broader multi-sport
charter remains **explicitly not started** — Gemini is wired into predictions only as
an *explanation narrator* over already-computed evidence
(`modules/predictions/application/explainability_engine.py`), never as a probability
source, per that module's own "predictions must never originate from an LLM" design
principle. Per this segment's own strict stop condition, no work on Gemini fusion,
Celery Beat, or any further scope expansion was performed.

**Incidental fix (found during live verification, not part of the charter)**: two
frontend crashes (`CompetitionsPage`, `DiscoverySection`, and by extension 26 other
call sites) caused by fixtures with an orphaned `team_id` (a leftover from an earlier
team-merge operation) serializing `home_team`/`away_team` as `null` despite the DTO's
non-null type. Fixed centrally in `lib/api/sports.ts`'s shared fixture-list functions
plus explicit honest-error guards on the two single-fixture consumers
(`match-detail-page.tsx`, `match-review-page.tsx`). Verified via `tsc --noEmit` (0
errors), live browser (fresh tab, zero console errors), and `vitest run` (75/76
passing — the one pre-existing failure is confirmed unrelated, file untouched per
`git status`).

---

# FINAL STATUS (as of this report)

PHASE STATUS: **COMPLETE** (per this segment's 15 Objectives; Gemini fusion charter
remains separately scoped and not started, per its own strict stop condition)

SPORTS AUDITED: football, basketball, baseball, table_tennis (4/4)

MARKETS AUDITED: 54

FOOTBALL: 19 total (18 active + 1 deprecated) — 14 TRAINED_AND_SERVING, 4
BLOCKED_BY_ARCHITECTURE, 1 deprecated (excluded)

BASKETBALL: 18 total — 14 TRAINED_AND_SERVING, 4 BLOCKED_BY_ARCHITECTURE

BASEBALL: 11 total — 8 TRAINED_AND_SERVING, 3 BLOCKED_BY_ARCHITECTURE

TABLE_TENNIS: 6 total — 0 TRAINED_AND_SERVING, 6 INSUFFICIENT_VERIFIED_DATA

TRAINED_AND_SERVING (total): 36

BLOCKED_BY_ARCHITECTURE (total): 11

INSUFFICIENT_VERIFIED_DATA (total): 6

DEPRECATED (excluded): 1

MATCH_WINNER_ROOT_CAUSE: Dataset never bootstrap-trained despite 652 real,
zero-rejection outcomes (proven via instrumented diagnostic mirroring
`DatasetBuilder.build()` exactly) — pure orchestration gap, not a data-quality bug.
Fixed via `ScheduledRetrainingOrchestrator._check_and_retrain` bootstrap path.

BTTS_ROOT_CAUSE: Identical to match_winner — confirmed independently (not assumed),
same instrumented diagnostic produced the same 652/652 zero-rejection result. Same
fix, same mechanism.

BASKETBALL_ROOT_CAUSE: (1) stale team-scoped required-feature mapping left over from a
prior fixture-vs-team entity-type migration (same bug class as football's Cluster A,
independently confirmed via source reading); (2) `market.overround` required with
permanent 0% coverage (no basketball odds provider), which silently blocked the
historical-prediction backfill for `moneyline`.

BASEBALL_ROOT_CAUSE: Identical two root causes as basketball, independently
re-confirmed for baseball's own feature keys and resolvers (not assumed identical).

TABLE_TENNIS_ROOT_CAUSE: Zero real fixtures ever ingested for this sport — no
table-tennis data provider is integrated. Confirmed via direct query, not assumed.

HISTORICAL_DATA_INTEGRATION: VERIFIED (football 7,829 fixtures; basketball/baseball
consistent with per-market sample counts; table_tennis 0, confirmed)

ROLLING_FEATURES: VERIFIED — `TrainingPreflightService.temporal_split_valid` passes on
every market with real samples; the one apparent `as_of`-after-`scheduled_at` anomaly
(football stat differentials) is explained as backfill-computation-timestamp vs.
point-in-time `reference_time`, not a leakage bug.

GEMINI_CONTEXTUAL_RECONSIDERATION: NOT_IMPLEMENTED (separately scoped, out of this
pass per strict stop condition)

GEMINI_EXPLANATION: PASS (existing narrator-only integration over already-computed
evidence, unchanged this segment)

DETERMINISTIC_FUSION: NOT_IMPLEMENTED (separately scoped)

FIX_IMPLEMENTED: Yes — football Cluster B bootstrap (2 markets); basketball/baseball
stale-mapping + overround fixes (12 `set_required()` calls) + historical-prediction
backfill (1,491 real outcome pairs) + bootstrap training (12 markets, all empirically
selected Champions, no forced algorithm).

TRAINING: YES for the 14 newly-bootstrapped markets this segment (2 football + 6
basketball + 6 baseball) — each via the same production
`ScheduledRetrainingOrchestrator` bootstrap path already used and tested for every
other market this session; empirical candidate selection, no fabricated scores.

CHAMPIONS: 14 new Champions this segment (see §26-27 tables for algorithm/version per
market), all live-verified as genuinely persisted (`ModelStatus.CHAMPION` confirmed via
direct DB query after the earlier stale-in-memory-object read gave a false
`CHALLENGER` reading).

CALIBRATION: N/A for the newly-bootstrapped markets (bootstrap path doesn't run
calibration fitting; scheduled separately)

LEAKAGE: PASS (`intelligence_feature_leakage_safe` passes for every market with real
samples, confirmed in the full audit)

PROVENANCE: PASS for all `TRAINED_AND_SERVING` markets; the known
`dataset_provenance_persisted` FAIL on in-memory-only `DatasetRepositoryPort` (ADR-008)
does not block bootstrap eligibility and was not treated as a real blocker

PREDICTION_API: PASS (live-verified: `football.match_winner`, `basketball.moneyline`)

FRONTEND: PASS (live-verified in Prediction Laboratory; plus an incidental,
independently-verified fix for a null-team crash class affecting 28 files, see Scope
note)

CACHE / QUOTA / CIRCUIT_BREAKER: NOT_EXERCISED (no provider calls made this segment —
pure DB read/update against already-persisted or already-backfilled data)

DATABASE_MODIFIED: YES — see §31 row-delta table. Zero raw-data table mutated; all
deltas trace to legitimate dataset/model/experiment/prediction/outcome creation and
in-place feature-mapping flag updates.

BACKEND_TESTS: 2547 passed, 0 failed, 4 warnings (560.45s) — confirmed zero
regressions from this segment's basketball/baseball/table-tennis work.

REGRESSIONS: None. Full suite matches the pre-segment baseline exactly on pass count;
zero new failures.

REPORT: `backend/docs/post_m24_phase17_football_prediction_recovery_report.md`

NEXT ACTION: Per this segment's strict stop condition — STOP. No Gemini fusion work,
no Celery Beat changes, no further scope expansion. Follow-up candidates (not started,
require separate authorization): table-tennis data provider integration, football
half-time score parsing, basketball/baseball betting-line and player-stat ingestion,
basketball/baseball odds provider wiring, and the Gemini contextual-reconsideration +
deterministic-fusion architecture as its own dedicated phase.
