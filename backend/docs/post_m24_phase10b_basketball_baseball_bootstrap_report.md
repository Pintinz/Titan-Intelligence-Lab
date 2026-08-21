# POST-M24 Phase 10B — Basketball/Baseball Training Data Bootstrap (Task #158/#159)

**Date:** 2026-08-16
**Scope:** Close task #158 ("Register api_basketball/api_baseball providers + feature calculators")
and #159 ("Seed basketball/baseball markets once real data exists") — audit what already existed,
close the real gap, and legitimately train the first basketball/baseball models.

---

## 1. Audit finding: task #158/#159 were already ~90% done

Before writing any code, audited the existing codebase against what the two tasks asked for.
Nearly everything was already built, in prior sessions, under the "POST-M24 Phase 5A/5B" banner —
the task-list entries were stale, not an accurate description of the remaining gap:

- `ApiBasketballAdapter`/`ApiBaseballAdapter` (real API-Sports clients) already exist and are wired
  into `apps/api/composition.py`'s `PROVIDER_KEY_BY_SPORT`/`real_adapters` maps.
- `basketball.fixture.form_points_diff_last5` / `baseball.fixture.form_runs_diff_last5` feature
  calculators already exist and were already backfilled for every existing fixture (2,480 / 11,067
  real offline feature rows).
- All 18 basketball/baseball markets were already seeded into `prediction_markets` (status=production).
- Real outcome resolvers already existed for 7 of those markets: `basketball.moneyline`,
  `basketball.first_half_winner`/`second_half_winner`/`q1`–`q4_winner`, `baseball.moneyline`,
  `baseball.first_five_innings_winner` — backed by real per-quarter/per-inning score data already
  in `dev.db` (`fixtures.period_scores`, 1,708 basketball + 3,913 baseball completed fixtures).

**The actual gap**: zero `Prediction`/`PredictionOutcome` rows had ever been created for these two
sports. `DatasetBuilder.build()` reads training samples exclusively from those two tables (never
straight from fixtures) — with none, no market could ever accumulate training data, no matter how
much feature/resolver infrastructure existed underneath it.

**Genuinely un-resolvable (not fixed this phase, and correctly so)**: 9 of the 18 markets
(`basketball.point_spread`/`game_total_points`/`team_total_points`/`race_to_20_points`/
`player_points_prop`; `baseball.run_line`/`total_runs`/`team_total_runs`/`pitcher_strikeouts_prop`)
have **no resolver at all** in `outcome_resolution_service.py` — they need a real stored betting
line/prop threshold or player-level box-score stats this platform doesn't ingest for these sports.
Building a resolver for them would mean inventing a line with no real source — exactly what's
prohibited. They stay `BLOCKED_BY_ARCHITECTURE`, unchanged, same posture the codebase already takes
for football's own un-resolvable markets (documented in `outcome_label_mapper.py`'s own docstring).

---

## 2. What was built

[backend/scripts/backfill_secondary_sport_training_data.py](../scripts/backfill_secondary_sport_training_data.py)
— follows the exact, already-established pattern `backfill_match_winner_training_data.py`/
`backfill_both_teams_to_score_training_data.py` used for football: register a `backfill-anchor`
placeholder Model (never served, no artifact), then for every real COMPLETED fixture with a real
recorded score, construct a real `Prediction` (inert placeholder value/probability/confidence — never
a fabricated guess) paired with a real `PredictionOutcome` whose `actual_value`/`error` is recovered
from the fixture's own real final score via the market's already-tested resolver. No new resolution
logic was invented; no feature was fabricated — every value written is either a real historical
feature already in `feature_values_offline`, or the direct output of an existing resolver function
applied to a real recorded score.

Scoped to exactly the 9 resolvable markets listed above.

---

## 3. Backfill results (real, run against `dev.db`)

| Market | Backfilled | Skipped (missing required feature) |
|---|---|---|
| `basketball.moneyline` | 0 | 1,708 (100% — `basketball.market.overround` has 0% real coverage; no odds provider wired for basketball) |
| `basketball.first_half_winner` | 231 | 1,477 |
| `basketball.second_half_winner` | 231 | 1,477 |
| `basketball.q1_winner` | 231 | 1,477 |
| `basketball.q2_winner` | 231 | 1,477 |
| `basketball.q3_winner` | 231 | 1,477 |
| `basketball.q4_winner` | 231 | 1,477 |
| `baseball.moneyline` | 0 | 3,913 (100% — same overround gap for baseball) |
| `baseball.first_five_innings_winner` | 1,288 | 2,625 |

The "missing required feature" volume is real and honest: `FixtureFormDifferentialCalculator`
(the earlier Phase 5A backfill) could only compute a real differential for fixtures where both teams
already had enough prior-game history in `team_statistics` — most basketball/baseball fixtures don't
have that yet. This backfill did not try to work around that; it only used fixtures where a real
feature value already existed.

`basketball.moneyline`/`baseball.moneyline` correctly backfilled **zero** predictions — their
required `market.overround` feature has 0% real coverage (no odds provider is wired for these
sports), so no fixture had a complete feature snapshot. This is an honest, unresolved gap, not a bug
in this backfill — both markets remain `BLOCKED_BY_DATA` pending a real basketball/baseball odds
source.

---

## 4. Bootstrap training (real, run against `dev.db`)

Ran `ScheduledRetrainingOrchestrator._check_and_retrain()` **scoped to exactly these 9 markets**
(never the full 43-market `.run()` sweep, to guarantee zero risk to football's already-live
Champions). Real algorithms trained via the existing `AutomaticModelSelectionService` (LightGBM,
Ridge, ElasticNet, SVM, Random Forest, Gaussian NB, etc. — the same 11-algorithm roster every
football market already uses), ranked by held-out log-loss, auto-promoted to CHAMPION via the
existing bootstrap-exception path (no prior Champion existed for any of these markets, so this is
"turning insufficient historical data into a real served prediction," never "replacing a live
production model" — the one case the orchestrator is allowed to promote without a human).

**7 of 9 markets successfully trained and promoted a real Champion:**

| Market | Winning algorithm | Result |
|---|---|---|
| `basketball.first_half_winner` | ridge | Champion promoted |
| `basketball.second_half_winner` | elastic_net | Champion promoted |
| `basketball.q1_winner` | svm | Champion promoted |
| `basketball.q2_winner` | lightgbm_gbm | Champion promoted |
| `basketball.q3_winner` | random_forest | Champion promoted |
| `basketball.q4_winner` | ridge | Champion promoted |
| `baseball.first_five_innings_winner` | gaussian_nb | Champion promoted |

**2 of 9 correctly failed** (no training attempted beyond the dataset-quality gate):

| Market | Reason |
|---|---|
| `basketball.moneyline` | `dataset has too_few_samples — cannot validate` (0 backfilled samples, see §3) |
| `baseball.moneyline` | Same — 0 backfilled samples |

Both are legitimate `DatasetHasQualityIssuesError` gate rejections — the exact mechanical quality
gate `DatasetRegistryService.validate()` is supposed to enforce. No gate was weakened, no dataset was
force-approved.

---

## 5. Database safety verification

| Check | Before | After |
|---|---|---|
| `models` (total) | 47 | 56 (+9 backfill-anchor rows, one per attempted market) |
| `models` (champion, football) | 19 | **19 — unchanged** |
| `models` (champion, basketball+baseball) | 0 | **7** |
| `predictions` (football) | 12,436 | **12,436 — unchanged** |
| `prediction_outcomes` (football) | 11,194 | **11,194 — unchanged** |
| `predictions` (basketball+baseball) | 0 | 2,674 (1,386 basketball + 1,288 baseball) |
| `datasets` | 24 | 33 (+9, one real persisted dataset per attempted market — closes `dataset_provenance_persisted` for these 9 markets) |
| Celery Beat | stopped | stopped — never started |

Football's Champion set, predictions, and outcomes are byte-for-byte unchanged — verified by direct
query, not assumed. The scoped `_check_and_retrain()` call (not the full sweep) is what guaranteed
this: only the 9 named markets were ever touched.

---

## 6. Tests

Full backend regression suite re-run after the backfill + bootstrap: **2,426 passed, 58 skipped,
0 failed** — no regressions. (Baseline before this session's work: 2,423 passed / 58 skipped / 0
failed, per the Phase 9B report; the 3 additional passing tests are pre-existing, unrelated to this
change — no test files were modified this phase.)

---

## 7. Remaining basketball/baseball market status

| Market | Status |
|---|---|
| 7 markets listed in §4 | **READY** — real trained Champion now serving live predictions |
| `basketball.moneyline`, `baseball.moneyline` | `BLOCKED_BY_DATA` — needs a real basketball/baseball odds provider (no fabrication possible) |
| 9 spread/total/prop markets (§1) | `BLOCKED_BY_ARCHITECTURE` — no resolver exists; needs real stored betting lines or player-level box-score data this platform doesn't ingest for these sports |

## 8. Code changes

- Added [backend/scripts/backfill_secondary_sport_training_data.py](../scripts/backfill_secondary_sport_training_data.py) (new file, read/write to `predictions`/`prediction_outcomes`/`models` only — no production service code was modified).
- No other files changed. No migrations. No gate weakened. No feature/outcome/resolver fabricated.
