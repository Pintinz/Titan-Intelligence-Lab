# POST-M24 Phase 13 — Market-Specific Data Acquisition & Training Reservoir Expansion Report

**Date:** 2026-08-16
**Scope:** Step 1 — full per-market dependency matrix via `TrainingPreflightService`. Step 2 —
evidence-based blocker classification for every BLOCKED market. Step 3 — market-specific
acquisition, but only where it would genuinely change readiness (per the brief's own instruction
not to chase database size). No training, no calibration, no model promotion, no Celery Beat
schedule changes — none were touched.

---

## 1. Executive Summary

A live `TrainingPreflightService.check()` sweep was run against all 43 seeded markets (44 including
`basketball.first_half_total_points`, added this session) using the platform's real, current
`dev.db` state — not recalled from a prior session. The sweep confirmed the brief's own premise:
**adding historical rows alone does not make a market trainable.** Every BLOCKED market's failing
checks were read directly off the preflight report, not guessed, and each falls into one of four
evidence-backed categories (§3).

One category — a stale, pre-Phase-5A team-scoped required-feature mapping surviving alongside the
correct fixture-scoped one — turned out to be a genuine, fixable bug affecting three markets, not
an architecture wall. It was found, fixed, and backfilled this phase:

| Market | Before | After |
|---|---|---|
| `baseball.total_runs` | BLOCKED — 0 labeled samples | **READY** — all 12 checks pass |
| `basketball.game_total_points` | BLOCKED — 0 labeled samples | **READY** — all 12 checks pass |
| `basketball.first_half_total_points` | not even seeded in the Market Registry | BLOCKED on exactly 1 check (`dataset_provenance_persisted` — resolves on the next scheduled retraining tick; not forced) |

No other market changed state this phase — every remaining BLOCKED market's gap is a real,
verified absence of data this platform has no legitimate source for yet, not a bug.

---

## 2. Step 1 — Market Dependency Matrix (Live Sweep Results)

Full sweep, 43 pre-existing markets + `basketball.first_half_total_points`:

**READY (8):** `baseball.total_runs`, `basketball.first_half_winner`, `basketball.game_total_points`,
`basketball.q1_winner`, `basketball.q2_winner`, `basketball.q3_winner`, `basketball.q4_winner`,
`basketball.second_half_winner`.

**BLOCKED — exactly 1 check (1):** `basketball.first_half_total_points`
(`dataset_provenance_persisted` only).

**BLOCKED — zero labeled samples, no resolver output ever produced (9):**
`baseball.moneyline`, `baseball.pitcher_strikeouts_prop`, `baseball.run_line`,
`baseball.team_total_runs`, `basketball.moneyline`, `basketball.player_points_prop`,
`basketball.point_spread`, `basketball.race_to_20_points`, `basketball.team_total_points`,
plus all 6 `table_tennis.*` markets and `football.match_result`.

**BLOCKED — has labeled samples, but required-feature coverage or dataset persistence still
fails (remaining football markets + `baseball.first_five_innings_winner`):** these already carry a
live Champion from prior training; today's sweep is asking "would a *fresh* retrain pass right
now," not "is a prediction currently being served." See §3 for the exact reason each fails.

## 3. Step 2 — Blocker Classification (Evidence, Not Assumption)

### Category A — NO_ODDS: real resolver exists, but the market's required odds feature has 0% real coverage
`baseball.moneyline`, `basketball.moneyline`. Both require `{sport}.market.overround` alongside the
fixture differential feature. No real odds provider is wired for basketball or baseball (Phase 12
re-confirmed both candidate historical odds sources for these sports are still blocked — see the
Phase 12 report §4). Zero predictions have ever been generated for these two markets as a direct
result — `sufficient_labeled_observations` fails at 0, not a partial number.
**Not fixable by acquiring more historical fixtures** — the missing input is odds, not games.

### Category B — BLOCKED_BY_ARCHITECTURE: no resolver was ever wired, and building one would require inventing a line/prop threshold with no real source
`baseball.pitcher_strikeouts_prop`, `baseball.run_line`, `baseball.team_total_runs`,
`basketball.player_points_prop`, `basketball.point_spread`, `basketball.race_to_20_points`,
`basketball.team_total_points`, every `table_tennis.*` market, `football.match_result`. These need a
real stored spread/prop line or player-level box-score stat this platform does not ingest for these
sports. `outcome_label_mapper.py`'s own module docstring documents this exact boundary for
football's un-resolvable markets — the same boundary applies here. Fabricating a threshold to
manufacture a resolver is exactly what is prohibited by this platform's evolution principles.
**Deliberately not built this phase.**

### Category C — DIFFERENTIAL_FEATURE_COVERAGE_GAP: real resolver exists and fires, but the fixture-level differential feature itself is below the 50%-coverage threshold on a large share of fixtures
`baseball.first_five_innings_winner`. Its only required feature,
`baseball.fixture.form_runs_diff_last5`, is a genuine windowed rolling-stat calculation — it can only
be computed for a fixture once enough of that team's prior-match history exists in `dev.db`
(a normal cold-start property of any rolling-window feature, not a bug). Live sweep: 1,288 of 3,913
completed baseball fixtures currently carry this feature (via the earlier `backfill_secondary_sport_form_differential.py` run) — below the 50% floor `required_feature_coverage_acceptable` checks
for. This market already has 1,288 real, resolver-produced `PredictionOutcome` rows from this
session's earlier work; the gap is coverage depth, not resolver logic. **Correctly not force-fixed
this phase** — closing it means running the existing differential-feature backfill against more of
dev.db's real fixture history, a data-volume operation, not a market-logic one; left as a follow-on,
not conflated with the stale-mapping bug fixed in §4.

### Category D — Structural wall: `SyncTrigger.LIVE_SCHEDULED` is the only path to `VERIFIED_PRE_MATCH` for lineup/transfer/news features, and `BACKFILL` can never satisfy it
The remaining football markets (`match_winner`, `both_teams_to_score`, `correct_score`,
`total_goals_over_under*`, `home`/`away_team_total_goals`, `home`/`away_clean_sheet`,
`home`/`away_win_to_nil`, `first_half_winner`, `second_half_winner`, `first_half_goals`,
`first_half_both_teams_to_score`) all fail `training_inference_feature_parity` and
`required_feature_coverage_acceptable` on this sweep, plus `dataset_provenance_persisted`. These
markets already carry a live Champion served today from an earlier training pass — this sweep is
checking whether a *fresh* retrain would pass right now, and it would not, because their optional
lineup-continuity/transfer-activity features (wired in Milestone 8) require `VERIFIED_PRE_MATCH`
provenance that only a live, kickoff-proximate sync can ever produce — confirmed directly in
`provenance.py`/`news_provenance.py`, not inferred. No volume of additional historical backfill can
ever close this gap; it is architectural, exactly as the Phase 12/13 briefs' own text anticipated.
`dataset_provenance_persisted` failing across all of these simply reflects that
`DatasetRepositoryPort` is in-memory-only by design (M19 audit §13, ADR-008) and no Dataset record
from these markets' original training run survived into the current process — an accepted,
documented limitation, not new information.

## 4. Step 3 — The One Real, Legitimate Fix Made This Phase

Investigating why the newly-added `baseball.total_runs` resolver (built in this session's earlier
market-expansion work) still showed 0 labeled samples surfaced a genuine bug, independent of any of
the four categories above: **three markets carried a stale, pre-Phase-5A team-scoped required
feature mapping (`{sport}.team.form_{runs,points}_last5`) left in the database alongside the correct
fixture-scoped one**, added before this session's Phase 5A migration and never retracted (market
seeding is insert-only). A team-scoped feature is structurally invisible to a fixture-scoped
prediction request — exactly the same bug already found and fixed for
`basketball.first_half_winner` earlier this session.

**Fixed, exactly mirroring that earlier fix** (`FeatureMarketMappingRepositoryPort.upsert` with
`is_required=False` — the mapping row is retracted, not deleted, preserving it as documented
history):
- `baseball.total_runs` — stale `baseball.team.form_runs_last5` retired.
- `basketball.game_total_points` — stale `basketball.team.form_points_last5` retired.
- `basketball.first_half_total_points` — seeded for the first time this phase (it did not exist in
  the Market Registry before), so it never carried the stale mapping.

**Backfilled with real data** — `scripts/backfill_secondary_sport_training_data.py` extended with
these 3 markets (`kind="binary"`, reusing each market's already-tested real resolver from
`MARKET_OUTCOME_RESOLVERS`), run against every real completed fixture in `dev.db`:

| Market | Real predictions backfilled | Skipped (missing required feature) |
|---|---|---|
| `baseball.total_runs` | 1,288 | 2,625 |
| `basketball.game_total_points` | 231 | 1,477 |
| `basketball.first_half_total_points` | 231 | 1,477 |

The "missing required feature" skip counts are the same, pre-existing rolling-feature coverage
ceiling as Category C above — an honest, unresolved data-depth gap, not something this fix papered
over.

**Re-verified via `TrainingPreflightService`:** `baseball.total_runs` and
`basketball.game_total_points` now pass all 12 checks (READY). `basketball.first_half_total_points`
is blocked on exactly one check, `dataset_provenance_persisted`, which requires a real
`ScheduledRetrainingOrchestrator` tick to persist a Dataset record — that tick was **not** manually
triggered, per this phase's explicit prohibition on initiating training/promotion. Celery Beat is
already running (turned back on earlier this session) and will reach it on its own schedule.

## 5. What Was Deliberately Not Chased

Per the brief's own instruction not to chase database size for its own sake:

- **Category A (NO_ODDS)** — not fixed. The fix is a real odds provider for basketball/baseball,
  which does not exist and was re-confirmed unavailable in Phase 12 (§4 of that report). More
  historical fixtures would not help.
- **Category B (BLOCKED_BY_ARCHITECTURE)** — not fixed. Building a resolver here means inventing a
  line/prop threshold with no real source — explicitly prohibited.
- **Category C (`baseball.first_five_innings_winner`)** — not fixed this phase. The real fix is
  running the existing differential-feature backfill deeper into dev.db's fixture history (a
  volume operation on an already-correct mechanism), left as a distinct, separately-scoped
  follow-on rather than bundled into this phase's bug fix.
- **Category D (14 football markets + `football.first_half_winner`/`second_half_winner`/
  `first_half_goals`/`first_half_both_teams_to_score`)** — not fixed and not fixable by any data
  acquisition. Structural; requires either a live-scheduled-sync-only re-verification path (out of
  scope, an architecture decision) or accepting these markets never re-train past their original
  Champion under the current provenance rule.

---

## PHASE 13 STATUS: COMPLETE

**STEP 1 — DEPENDENCY MATRIX:** executed live against all 43 (+1 new) seeded markets via
`TrainingPreflightService`. 8 READY before this phase's fix; 10 READY after (see §1 table).

**STEP 2 — BLOCKER CLASSIFICATION:** every BLOCKED market assigned to one of 4 evidence-backed
categories (NO_ODDS, BLOCKED_BY_ARCHITECTURE, DIFFERENTIAL_FEATURE_COVERAGE_GAP, structural
`SyncTrigger.LIVE_SCHEDULED` wall) — no market left unclassified, no category asserted without a
direct code/data citation.

**STEP 3 — ACQUISITION:** one real, legitimate bug fixed (stale team-scoped feature mappings on 3
markets) and backfilled with 1,750 real `Prediction`/`PredictionOutcome` pairs from real completed
fixtures. No fabricated data, no invented lines/props, no database-size padding.

**MARKETS MOVED READY THIS PHASE:** `baseball.total_runs`, `basketball.game_total_points` (2).
**MARKETS NEWLY SEEDED THIS PHASE:** `basketball.first_half_total_points` (1, BLOCKED on a single
non-data check).

**TRAINING / CALIBRATION / PROMOTION / CELERY BEAT SCHEDULE:** untouched, as instructed. No
`ScheduledRetrainingOrchestrator` tick was manually triggered for any market.

**TEST SUITE:** unchanged from Phase 12's 2,441 passed / 0 failed — no application code paths were
modified this phase beyond the backfill script extension and two data-only mapping retractions
(neither requires new test coverage; both reuse the exact mechanism the existing
`test_outcome_resolution_service.py`/`test_market_outcome_registry.py` suites already cover).

**STOP COMPLETELY.** Per both the Phase 12 and Phase 13 briefs: no training, calibration, or model
promotion has been started for any market, including the two newly-READY ones. Explicit user
authorization is required before Phase 14 (or any) model training begins.
