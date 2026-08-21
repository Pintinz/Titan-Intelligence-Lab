# POST-M24 Master Data Fabric — Phase 5A: Secondary-Sport Market Implementation

**Verification Report**

---

## 1. Current 38-Market Inventory

Read directly from `dev.db`'s `prediction_markets` table (not assumed from any prior report):

| Sport | Markets |
|---|---|
| Football | 19 |
| Basketball | 7 |
| Baseball | 6 |
| Table Tennis | 6 |
| **Total** | **38** |

Confirms the Phase 5 audit's headline number exactly. Football's 19 all had `resolver_key` set
and a real Champion model *before* this phase; basketball/baseball/table_tennis's 19 combined
had `resolver_key = NULL` in the DB and zero Champions.

---

## 2. Placeholder-Market Findings

The real, code-level finding this phase's audit surfaced (not visible from the DB catalog alone):

- **`basketball.moneyline`, `baseball.moneyline`, `table_tennis.match_winner`** already had a
  working resolver (`_moneyline_home_win`) registered in `MARKET_OUTCOME_RESOLVERS`
  (`outcome_resolution_service.py`) *and* a real `MARKET_OUTCOME_LABELS` entry — the DB's
  `resolver_key = NULL` column was simply never written for them, a cosmetic/bookkeeping gap, not
  a functional one. `OutcomeResolutionService.resolve_for_fixture` looks up resolvers by
  `market.market_key` directly, never by the DB's `resolver_key` column.
- **`basketball.first_half_winner` (as `first_half_winner`) and `baseball.first_five_innings_winner`**
  had *no* resolver anywhere — genuinely missing, and the two markets this phase implemented.
- **Every other basketball/baseball/table_tennis market** (spread/point_spread, totals,
  team_totals, race_to, player_prop, run_line, match_handicap, correct_score, set_winner) has no
  resolver and no stored line/threshold anywhere in the codebase — see §6/§7/§9 for why each is
  BLOCKED, not silently skipped.
- **A structural bug, not sport-specific**: every basketball/baseball market's declared
  `required_features` (`basketball.team.form_points_last5` etc.) was an `EntityType.TEAM`-scoped
  feature. `PredictionContextBuilder` only resolves a mapped feature against the exact
  entity_type/entity_id a prediction request was made for — a fixture-level market can never see a
  team-scoped feature. This is the exact bug football's own `required_features` fix (`Fixture
  FormDifferentialCalculator`, referenced in `football.market_seeding`'s own module docstring)
  already closed; basketball/baseball never got the equivalent fix. Fixed this phase (§9).
- **A second, deeper bug found while fixing the first**: `EntityReconciliationService.
  get_or_create_match` unconditionally created every `Match` row with `started_at=None`, for
  *every* sport including football. `TeamStatisticsRepositoryPort.list_recent_by_team` — the sole
  read path every rolling-form/differential feature calculator uses — joins on `Match.started_at <
  before`; a SQL `NULL` comparison is never true, so every such feature was structurally
  unresolvable for every sport whose `Match` rows never had `started_at` set some other way.
  Football's dev.db rows happened to already carry a real `started_at` from an earlier session
  correction; basketball's and baseball's never did. Fixed this phase (§18).

---

## 3. Basketball Implementation Matrix

| Market | Catalog | Resolver | Features | Provider data | Status |
|---|---|---|---|---|---|
| `basketball.moneyline` | ✓ | ✓ (`_moneyline_home_win`) | ✓ (fixed, now fixture-scoped) | Missing: `basketball.market.overround` (no real odds provider) | **BLOCKED_BY_DATA** |
| `basketball.first_half_winner` | ✓ | ✓ **NEW** (`_first_half_winner`, reused) | ✓ (fixed, fixture-scoped) | Real quarters 1+2 in `period_scores` | **IMPLEMENTED** |
| `basketball.point_spread` | ✓ | — | — | No stored per-fixture handicap line anywhere | **BLOCKED_BY_ARCHITECTURE** |
| `basketball.game_total_points` | ✓ | — | — | No declared fixed threshold (unlike football's per-line markets) | **BLOCKED_BY_ARCHITECTURE** |
| `basketball.team_total_points` | ✓ | — | — | Same — CLASSIFICATION target needs a threshold not present | **BLOCKED_BY_ARCHITECTURE** |
| `basketball.race_to_20_points` | ✓ | — | — | Needs point-by-point/live scoring data not ingested | **BLOCKED_BY_DATA** |
| `basketball.player_points_prop` | ✓ | — | — | No `PlayerStatistics` repository port exists | **BLOCKED_BY_ARCHITECTURE** |

**Implemented this phase**: `basketball.first_half_winner`.

---

## 4. Basketball Resolver Architecture

`_first_half_winner` (already existed for `football.first_half_winner`, in
`THREE_WAY_MARKET_RESOLVERS`) is reused **verbatim, unchanged** — it reads only
`MatchResult.home_score_ht`/`away_score_ht`, with no football-specific logic inside it.
Basketball's own halftime is genuinely the real-world combined score after quarters 1+2 (the
actual rule of the sport), not a borrowed convention — so no new resolver function was written,
only a new dict registration: `THREE_WAY_MARKET_RESOLVERS["basketball.first_half_winner"] =
_first_half_winner`.

`_extract_half_time_scores` (`entity_reconciliation_service.py`) was extended to also handle
`Fixture.period_scores["kind"] == "quarter"` (summing quarters 1+2), alongside its existing
`kind == "half"` (football) branch — one function, two real period-score shapes, no duplication.

---

## 5. Basketball Feature Architecture

`basketball.fixture.form_points_diff_last5` (`EntityType.FIXTURE`) — a new
`basketball_fixture_form_differential_calculator` factory, wrapping the **existing, unmodified**
`FixtureFormDifferentialCalculator` class (the exact class football already uses) with
`sport_code="basketball", stat_key="points"`. Wired into
`EntityReconciliationService.form_differential_calculators["basketball"]` so it fires on every
future basketball `reconcile_fixture` call, same as football's already does.

`basketball.market_seeding.MARKETS`'s `required_features` was updated from the broken team-scoped
key to this new fixture-scoped key for every market that declared it (all seven) — a consistency
fix, not just a fix for the one market this phase implements, since the team-scoped key was never
correct for *any* fixture-level market.

---

## 6. Baseball Implementation Matrix

| Market | Catalog | Resolver | Features | Provider data | Status |
|---|---|---|---|---|---|
| `baseball.moneyline` | ✓ | ✓ (`_moneyline_home_win`) | ✓ (fixed, fixture-scoped) | Missing: `baseball.market.overround` (no real odds provider) | **BLOCKED_BY_DATA** |
| `baseball.first_five_innings_winner` | ✓ | ✓ **NEW** (`_first_five_innings_winner`) | ✓ (fixed, fixture-scoped) | Real innings 1-5 in `period_scores` | **IMPLEMENTED** |
| `baseball.run_line` | ✓ | — | — | No stored per-fixture handicap line | **BLOCKED_BY_ARCHITECTURE** |
| `baseball.total_runs` | ✓ | — | — | No declared fixed threshold | **BLOCKED_BY_ARCHITECTURE** |
| `baseball.team_total_runs` | ✓ | — | — | Same | **BLOCKED_BY_ARCHITECTURE** |
| `baseball.pitcher_strikeouts_prop` | ✓ | — | — | No `PlayerStatistics`/pitcher-level port | **BLOCKED_BY_ARCHITECTURE** |

**Implemented this phase**: `baseball.first_five_innings_winner`.

---

## 7. Baseball Resolver Architecture

`_first_five_innings_winner` is a **new** function (baseball has no existing "segment" resolver to
reuse — football's half-result resolvers don't map onto innings). It reads new `MatchResult`
fields `home_score_first5`/`away_score_first5`, resolves `HOME_WIN`/`AWAY_WIN`/`DRAW` — a tie
after five innings is a real, common baseball outcome, not treated as unresolved (mirrors
`_match_winner_home_draw_away`'s and `_first_half_winner`'s own three-way shape exactly).

A new `_extract_first_five_innings_scores` (`entity_reconciliation_service.py`) reads
`Fixture.period_scores["kind"] == "inning"`, summing indices 0-4 — returns `(None, None)` if fewer
than five innings are recorded or any of the first five is `None` (game postponed/abandoned before
completing five innings), never fabricated or partially summed.

`resolve_for_fixture`'s signature grew two new optional kwargs
(`home_score_first5`/`away_score_first5`); every existing caller that doesn't pass them is
unaffected (the four existing half-result markets already treat a missing segment score as "not
resolvable yet").

---

## 8. Baseball Feature Architecture

`baseball.fixture.form_runs_diff_last5` — same pattern as basketball's (§5), reusing
`FixtureFormDifferentialCalculator` with `stat_key="runs"`. Wired into
`form_differential_calculators["baseball"]`.

---

## 9. Table-Tennis Provider Audit

Re-verified from source this phase, not assumed from Phase 3:

- **Real provider adapter**: none. `composition.py`'s real-adapter map only has
  `api_football`/`api_basketball`/`api_baseball` — table tennis is entirely absent.
  `real_adapters`/`fixture_schedule_adapters` have no table_tennis entry.
- **Provider capability registration**: `PROVIDER_CAPABILITIES` (Phase 3) has no `table_tennis`
  entry — confirmed unchanged.
- **What *does* exist**: `MockSportsDataProvider(provider_key="mock_table_tennis", ...)` (a mock,
  used only for structural/dev completeness) and `table_tennis.market_seeding.py`'s 6 catalog
  markets + `table_tennis.match_winner`'s resolver in `MARKET_OUTCOME_RESOLVERS` (real *code*, no
  real *data* behind it).
- **Real fixtures**: 0 (confirmed by direct DB query — table_tennis doesn't even appear in a
  per-sport fixture-count grouping).

**Verdict: UNSUPPORTED.** No mock infrastructure was labeled operational; no market definitions
were removed or altered; no Champion was created. This is unchanged from Phase 3's own finding —
re-verified, not assumed.

---

## 10. Implemented Markets

- `basketball.first_half_winner` — real resolver (reused), real fixture-scoped feature, real
  period-score data.
- `baseball.first_five_innings_winner` — real resolver (new), real fixture-scoped feature, real
  period-score data.

Both moved from "catalog placeholder, zero resolver, zero usable feature" to "structurally
resolvable, real feature backfilled for existing fixtures." Neither has a Champion — see §22.

---

## 11. Blocked Markets

BLOCKED_BY_DATA (resolver exists, required feature genuinely unavailable):
`basketball.moneyline`, `baseball.moneyline` (both need `market.overround`, which needs real
odds — no odds provider wired for either sport), `basketball.race_to_20_points` (needs live
point-by-point data not ingested).

BLOCKED_BY_ARCHITECTURE (no resolver possible without inventing a convention this phase was told
not to invent): `basketball.point_spread`, `basketball.game_total_points`,
`basketball.team_total_points`, `basketball.player_points_prop`, `baseball.run_line`,
`baseball.total_runs`, `baseball.team_total_runs`, `baseball.pitcher_strikeouts_prop`,
`table_tennis.match_handicap`, `table_tennis.total_points`, `table_tennis.correct_score`,
`table_tennis.race_to_11_points`, `table_tennis.set_winner`.

None of these were force-implemented. §16/§17 explain the reasoning per category.

---

## 12. Unsupported Markets

All 6 table_tennis markets: `table_tennis.match_winner` (has a resolver, but 0 real fixtures —
unusable regardless), `table_tennis.correct_score`, `.match_handicap`, `.total_points`,
`.race_to_11_points`, `.set_winner`. Sport-level: UNSUPPORTED (§9).

---

## 13. Provenance

Nothing in this phase touches `SyncTrigger`, `classify_availability`, or `VERIFIED_PRE_MATCH`.
Historical import remains `SyncTrigger.BACKFILL` (untouched, Phase 4). The two new resolvers read
only *final* period scores from already-COMPLETED fixtures (`resolve_for_fixture` is only ever
called once a fixture reaches `FixtureStatus.COMPLETED` with a score) — never treated as pre-match
intelligence, never gated by `VERIFIED_PRE_MATCH` (that classification is scoped to
Lineup/Injury/Transfer/Suspension, not fixture outcomes, confirmed in Phase 4's own audit).

---

## 14. Training/Inference Parity

**PARTIAL.** For the two implemented markets, the single required feature
(`{sport}.fixture.form_{stat}_diff_last5`) is now real, fixture-scoped, and — critically — the same
feature key `market_seeding.py` declares as required and any future `PredictionEngine.generate()`
call would resolve through `PredictionContextBuilder`. There is no training/inference *mismatch*
for these two markets specifically, because neither has ever been trained (no Champion, no
Dataset) — parity is trivially satisfied by both sides pointing at the same not-yet-exercised
feature. This phase did not build or run `DatasetBuilder` against these markets (see §16) — no
training samples exist yet to compare a trained feature set against a live one, so "PARTIAL" is
the honest label until that step actually runs.

---

## 15. DatasetBuilder

**Not exercised this phase.** `DatasetBuilder` builds training samples from real `Prediction.
feature_snapshot` records (Phase 4's own confirmed architecture) — since no Champion has ever
existed for either implemented market, no `Prediction` has ever been generated against them, so
there is nothing yet for `DatasetBuilder` to read. This is expected and correct, not a gap: running
`DatasetBuilder` against zero predictions would trivially return zero samples, telling us nothing
new beyond what §14 already states.

---

## 16. TrainingPreflight

**Not run this phase.** For the same reason as §15 — `TrainingPreflightService` (per its Phase 4
role) validates a market's readiness to train against real accumulated `PredictionOutcome`/dataset
history; with zero predictions and zero datasets for either implemented market, the honest result
would be `NO_LABELS`/`INSUFFICIENT_DATA`, not a meaningful readiness signal. The real value of this
phase's fixes only becomes visible once the live-scheduled pipeline starts generating and
resolving predictions for these two markets over real time — an operational/scheduling step, not
part of this implementation phase's own scope (and specifically not something this phase is
authorized to trigger, since a Champion never existing means no predictions can be generated
without one — see the strict "no Champions" rule, §17).

---

## 17. Tests

New tests this phase (all passing):

| File | New tests |
|---|---|
| `test_outcome_resolution_service.py` | 9 (`TestSecondarySportResolvers`: basketball/baseball/table_tennis moneyline, basketball first-half-winner reuse, baseball first-five-innings winner incl. real tie + unresolved-without-data) |
| `test_period_score_extraction.py` (new file) | 9 (`_extract_half_time_scores` quarter-kind sum/partial/null/unknown-kind; `_extract_first_five_innings_scores` sum/partial/null/kind-isolation) |
| `test_windowed_feature_engineering_service.py` | 2 (basketball/baseball fixture-scoped differential join) |
| `test_entity_reconciliation_service.py` | 1 (`get_or_create_match` sets real `started_at`) |
| `test_basketball_market_seeding.py` / `test_baseball_market_seeding.py` | updated fixtures (new `differential_calculator` dependency) |
| `test_market_outcome_registry.py` | updated `MARKETS_WITH_REAL_RESOLVER` set |

Covers: resolver correctness (home/away/tie), missing-data unresolved paths, period-boundary
extraction (quarter vs. inning vs. half, cross-kind isolation), feature join correctness,
provenance (`Match.started_at`), and multi-sport isolation (football's own tests re-verified
unaffected, run together in the same suite).

---

## 18. Database Delta

| Change | Rows affected |
|---|---|
| `matches.started_at` backfilled from each match's own real `fixtures.scheduled_at` | 133 rows (was `NULL`) |
| `feature_values_offline` — new `basketball.fixture.form_points_diff_last5` rows | 231 |
| `feature_values_offline` — new `baseball.fixture.form_runs_diff_last5` rows | 1,290 |
| `feature_definitions` — 2 new entries (the two fixture-scoped diff features above) | 2 |

**Explicitly verified unchanged**: `fixtures` (6,834), `teams` (215), `competitions` (7), `seasons`
(18), `prediction_outcomes` (11,194), `datasets` (0), `models` (47, still exactly 19 champions, all
football), `predictions` (12,436), `provider_ref_index` (7,529), `news_articles` (319),
`news_events` (68), `intelligence_sync_runs` (47), `sync_checkpoints` (201). No row in any of these
tables was added, removed, or modified.

---

## 19. External API Calls

**0.** Every change this phase reads/writes only `dev.db` (SQLite, local) and the local Redis
feature store — no live provider (api-football/api-basketball/api-baseball) was ever called. The
backfill script (`scripts/backfill_secondary_sport_form_differential.py`) reads existing
`team_statistics`/`fixtures` rows already in the database; it makes no network request of any
kind.

---

## 20. Cache/Quota Impact

None. No `QuotaIntelligenceEngine`/`CircuitBreaker` state was touched — this phase never called
`SportsProviderRouter` or any live adapter.

---

## 21. Gemini Calls

**0.** Nothing this phase touches the intelligence/Gemini pipeline.

---

## 22. Champion/Model Safety

- **No model trained.** No `.fit()` call anywhere in this phase's changes.
- **No Champion created or modified.** Verified directly: `models` table still has exactly 19
  `champion`-status rows, all football, both before and after every change (§18).
- **No calibration, no retraining, no promotion.** `calibration_reports` untouched;
  `ScheduledRetrainingOrchestrator`/`AutomaticModelSelectionService` were never imported or called.
- **No Celery Beat started.** No worker process was launched this phase.

---

## 23. Remaining Blockers

1. **Odds data for basketball/baseball/table_tennis.** `basketball.moneyline`/`baseball.moneyline`
   have a real resolver but remain unresolvable until a real odds source exists for those sports
   (mirrors football's own `fetch_odds`/`FootballOddsFeatureWriter`, never built for the other
   two).
2. **No stored per-fixture line/handicap/threshold mechanism for basketball/baseball totals and
   spreads.** Football's own solution was per-line *separate markets* (`total_goals_over_under_0_5`
   etc.), not a single generic market with a runtime line — basketball/baseball's catalog wasn't
   seeded that way. Resolving this requires either reseeding per-line markets (a market-catalog
   change, out of this phase's "minimal fix" scope) or a genuine stored-line mechanism.
3. **No `PlayerStatistics` repository port.** Blocks every player-prop market
   (`basketball.player_points_prop`, `baseball.pitcher_strikeouts_prop`) structurally.
4. **Table tennis has no real provider or fixtures at all** — a much larger, out-of-scope build
   (a real provider integration) would be required before any table_tennis market could move past
   UNSUPPORTED.
5. **Zero live-scheduled prediction generation exists yet for either implemented market** — a
   Champion (and therefore any real `Prediction`/`PredictionOutcome` accumulation) requires
   Phase 6's explicit training authorization, not this phase's.

---

## 24. Recommendation for the Next Phase

Before any training authorization, a genuine `DatasetBuilder`/`TrainingPreflightService` dry run
against `basketball.first_half_winner` and `baseball.first_five_innings_winner` — once enough real
predictions exist from the live-scheduled pipeline — would give the first honest READY_FOR_TRAINING
signal for a non-football market. Separately, wiring a real odds source for basketball/baseball
would unblock their moneyline markets, which already have a working resolver and just need one
missing feature.

---

## Test Results

Targeted suites (`tests/unit/modules/predictions/` + `tests/unit/modules/ingestion/`): **985
passed, 0 failed** (before the `get_or_create_match` fix's own new test; **986 passed** including
it, verified directly).

Full backend suite: **2372 passed, 58 skipped, 0 failed** (1131.68s / 18m51s). Delta vs. the
Phase 4 baseline (2350 passed / 58 skipped / 0 failed) is **+22 passed, 0 skipped change, 0
failed** — zero regressions anywhere else in the suite, including every existing football test.

---

## Final Response Format

```
PHASE 5A STATUS:
COMPLETE

MARKETS AUDITED:
38

FOOTBALL:
19 — unchanged, all resolvers/Champions intact, zero regressions

BASKETBALL:
7 markets — 1 IMPLEMENTED (first_half_winner), 1 BLOCKED_BY_DATA (moneyline, needs odds),
5 BLOCKED_BY_ARCHITECTURE/DATA (no stored line, or no player-stat port)

BASEBALL:
6 markets — 1 IMPLEMENTED (first_five_innings_winner), 1 BLOCKED_BY_DATA (moneyline, needs odds),
4 BLOCKED_BY_ARCHITECTURE/DATA (no stored line, or no player-stat port)

TABLE TENNIS:
6 markets — UNSUPPORTED (no real provider, no real fixtures — re-verified unchanged from Phase 3)

IMPLEMENTED RESOLVERS:
basketball.first_half_winner (reused football._first_half_winner, unchanged),
baseball.first_five_innings_winner (new: _first_five_innings_winner)

IMPLEMENTED FEATURE CALCULATORS:
basketball_fixture_form_differential_calculator, baseball_fixture_form_differential_calculator
(both reuse the existing FixtureFormDifferentialCalculator class, new sport_code/stat_key params only)

BLOCKED MARKETS:
basketball.moneyline, basketball.point_spread, basketball.game_total_points,
basketball.team_total_points, basketball.race_to_20_points, basketball.player_points_prop,
baseball.moneyline, baseball.run_line, baseball.total_runs, baseball.team_total_runs,
baseball.pitcher_strikeouts_prop

UNSUPPORTED MARKETS:
table_tennis.match_winner, table_tennis.correct_score, table_tennis.match_handicap,
table_tennis.total_points, table_tennis.race_to_11_points, table_tennis.set_winner

TRAINING/INFERENCE PARITY:
PARTIAL (trivially satisfied for the 2 implemented markets — neither has ever been trained yet)

PROVENANCE:
PASS

DATASET BUILDER:
NOT EXERCISED (zero predictions exist for either implemented market — nothing to build from yet)

TRAINING PREFLIGHT:
NOT RUN (same reason — would only report NO_LABELS/INSUFFICIENT_DATA, no new signal)

DATABASE MODIFIED:
YES

DATABASE DELTA:
matches.started_at backfilled for 133 rows (from each match's own real fixture scheduled_at);
+231 basketball and +1,290 baseball feature_values_offline rows; +2 feature_definitions rows.
fixtures/teams/competitions/seasons/prediction_outcomes/datasets/models/predictions/
provider_ref_index/news_articles/news_events/intelligence_sync_runs/sync_checkpoints: unchanged.

EXTERNAL API CALLS:
0

GEMINI CALLS:
0

CACHE/QUOTA:
PASS (not exercised — no live provider call made)

MODEL TRAINED:
NO

CHAMPION MODIFIED:
NO

CALIBRATION:
NO

RETRAINING:
NO

MODEL PROMOTION:
NO

CELERY BEAT:
NOT STARTED

BACKEND TESTS:
2372 passed, 58 skipped, 0 failed (baseline 2350/58/0 -> +22, zero regressions)

REGRESSIONS:
0

NEXT PHASE:
EXPLICIT TRAINING READINESS REVIEW

STOP COMPLETELY.
```
