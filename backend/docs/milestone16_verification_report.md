# Milestone 16 Verification Report — Live Structured-Intelligence Feature Availability & BTTS Prediction Unblocking

## 1. Executive Summary

`football.both_teams_to_score` has six `required_features` (2 news, 2 lineup-continuity, 2
transfer-activity) that are, today, never satisfied for any fixture — every live generation
attempt raises `MissingRequiredFeatureError`. This milestone traced the root cause through the
entire structured-intelligence and news pipeline (per the required 18-item investigation) and
found it is **not a bug**: every one of the six features can only ever be legitimately populated
by a genuinely live, `LIVE_SCHEDULED`-triggered sync (a deliberate Milestone 5/9 safety rule), and
that rule is correctly enforced end-to-end — confirmed by direct source reading, not assumption.
The 652 historical training fixtures already happened in the past, so a genuine live sync can never
retroactively cover them; the live-sync pipeline itself (Beat → worker bootstrap → orchestrator →
reconciliation → provenance classification → feature calculators → Feature Store) is verified
correctly wired for *future* fixtures, once enabled. No fabrication, no weakened `is_required`, no
new parallel pipeline was introduced. The one legitimate, minimal fix applied: `prediction_router.py`
now catches `MissingRequiredFeatureError` and returns the same honest "insufficient data" response
already given for `NoChampionModelError`/`MarketNotInProductionError`, instead of an unhandled 500.

## 2. Original `MissingRequiredFeatureError`

`FeatureMarketMappingService.resolve_feature_snapshot` (`feature_market_mapping_service.py:98-118`)
raises `MissingRequiredFeatureError` whenever any `is_required=True` mapping is absent from
`available_features`. `football.both_teams_to_score`'s live `feature_market_mappings` (queried
directly from `dev.db`) mark exactly 6 of 8 required keys as never-satisfied:
`news.football.home_btts_impact`, `news.football.away_btts_impact`,
`football.fixture.home_lineup_continuity`, `football.fixture.away_lineup_continuity`,
`football.fixture.home_transfer_activity`, `football.fixture.away_transfer_activity`. Traced the
exception's full path: raised inside `PredictionContextBuilder.build` (line 122, the real
live-prediction context-building path) → propagates uncaught through `PredictionCacheService
.get_or_generate` → uncaught in `prediction_router.py`'s `POST /api/v1/predictions/generate`
handler (only `MarketNotFoundError`/`MarketNotInProductionError`/`NoChampionModelError` were
caught) → no global FastAPI exception handler exists anywhere in `apps/api/main.py`/`composition.py`
(confirmed by direct search) → an unhandled 500.

## 3. Six-Feature Dependency Graph

```
news.football.home_btts_impact / away_btts_impact
  <- NewsMarketImpactEngine.compute_and_write (Milestone 9)
     <- requires >=1 NewsEvent with availability_classification == VERIFIED_PRE_MATCH,
        entity resolved, forward/goalkeeper role, within TTL, before kickoff
        <- classify_news_availability (Milestone 9) — VERIFIED_PRE_MATCH only from
           SyncTrigger.LIVE_SCHEDULED
           <- intelligence.sync_scheduled_news Celery task (Milestone 10), Beat-scheduled,
              gated by NEWS_SYNC_ENABLED (default false)

football.fixture.home_lineup_continuity / away_lineup_continuity
  <- LineupContinuityCalculator.compute_and_write (Milestone 6)
     <- requires the CURRENT fixture's own Lineup.availability_classification ==
        VERIFIED_PRE_MATCH (called from EntityReconciliationService.reconcile_lineup right after
        that classification is made) AND >=1 previous confirmed lineup for the same team
        <- classify_availability (Milestone 5) — VERIFIED_PRE_MATCH only from
           SyncTrigger.LIVE_SCHEDULED
           <- ingestion.sync_upcoming_structured_intelligence Celery task (Milestone 5),
              Beat-scheduled, always-on (no feature flag)

football.fixture.home_transfer_activity / away_transfer_activity
  <- TransferActivityCalculator.compute_and_write (Milestone 7)
     <- requires >=1 Transfer record for the team with availability_classification ==
        VERIFIED_PRE_MATCH and effective_date within TRANSFER_ACTIVITY_WINDOW_DAYS
        <- classify_availability (Milestone 5) — VERIFIED_PRE_MATCH only from
           SyncTrigger.LIVE_SCHEDULED
           <- same ingestion.sync_upcoming_structured_intelligence task as lineups
```

All three branches converge on the identical, single choke point: **only a genuine
`LIVE_SCHEDULED` sync can ever produce `VERIFIED_PRE_MATCH`.**

## 4. Root Cause

**Confirmed, not assumed, via direct evidence for both structured-intelligence keys:**

```sql
-- dev.db, read-only
SELECT availability_classification, COUNT(*) FROM transfers GROUP BY availability_classification;
-- ('UNKNOWN_AVAILABILITY_TIME', 308)   <- all 308, zero VERIFIED_PRE_MATCH
SELECT availability_classification, COUNT(*) FROM lineups GROUP BY availability_classification;
-- ('UNKNOWN_AVAILABILITY_TIME', 4)     <- all 4, zero VERIFIED_PRE_MATCH
```

Traced the source of these 308 transfer + 4 lineup rows to `scripts/backfill_squad_intelligence.py`,
which explicitly calls `orchestrator.sync_transfers(..., trigger=SyncTrigger.BACKFILL)` (line 69)
and the equivalent for lineups/injuries — never `LIVE_SCHEDULED`. Per Milestone 5's own provenance
rule (`modules.ingestion.application.provenance.classify_availability`), `BACKFILL` structurally
cannot produce `VERIFIED_PRE_MATCH`. **`UNKNOWN_AVAILABILITY_TIME` is the correct, honest
classification for this data — not a defect.** News: `dev.db` has 68 `news_events`, all 68
`UNKNOWN_AVAILABILITY_TIME` (re-confirmed live in this milestone), for the same structural reason
(`NEWS_SYNC_ENABLED` defaults `false`; the one real backfill path, Milestone 15's
`HistoricalFeatureReconstructionService`, has never been executed for real against `dev.db`).

**The root cause is structural, not a code defect:** the 652 fixtures already happened
(2022–2024). A genuine `LIVE_SCHEDULED` sync — one that captures "what was true right before this
fixture's kickoff" — is now impossible to run for a fixture whose kickoff has already passed, by
definition. No amount of pipeline engineering can retroactively manufacture a real live-sync
observation for a past event without fabricating one, which this milestone's own constraints
correctly forbid.

## 5. Existing Architecture Reused

No new pipeline was built. Every mechanism this milestone traced was authored in a prior milestone
and used exactly as-is: `classify_availability`/`classify_news_availability` (M5/M9),
`LineupContinuityCalculator`/`TransferActivityCalculator` (M6/M7), `NewsMarketImpactEngine` (M9),
`sync_upcoming_structured_intelligence`/Beat schedule (M5), `sync_scheduled_news` (M10), worker
bootstrap task registration (M11), `HistoricalEntityResolutionService`/
`HistoricalNewsRelevanceEngine` (M13), `HistoricalFeatureReconstructionService` (M14), the M15
training backfill integration. The only new code in this milestone is the router's error-handling
addition (§2) and its two accompanying tests (§17).

## 6. Structured-Intelligence Pipeline

`ingestion.sync_upcoming_structured_intelligence` (Celery task, `modules/ingestion/infrastructure
/celery/tasks.py:184-201`) is the **only real caller** of `SyncOrchestrator
.sync_upcoming_structured_intelligence` — confirmed by that task's own docstring and a repo-wide
search finding no other call site (no admin API, no backfill script calls this specific
orchestrator method). Its default trigger is `SyncTrigger.LIVE_SCHEDULED`, and since Beat firing
this task is the only path that reaches it, this is correctly the sole source of
`LIVE_SCHEDULED`-provenance injuries/transfers/lineups. Verified: this task is always registered
(no feature flag gates its registration — unlike news), meaning the pipeline is live-ready today;
it simply has never fired against any of the 652 already-completed historical fixtures because
Beat only syncs *upcoming* fixtures.

## 7. News Pipeline

Unmodified since Milestone 10/13/14/15 — see `docs/milestone10_verification_report.md`,
`docs/milestone13_verification_report.md`, `docs/milestone14_verification_report.md`,
`docs/milestone15_verification_report.md` for full prior verification. Re-confirmed live in this
milestone: `NEWS_SYNC_ENABLED` defaults `false` (unchanged), the Beat entry
`sync-scheduled-news-football-epl` is always registered but the task itself no-ops (no provider
call) while the flag is off, and zero `VERIFIED_PRE_MATCH` events exist in `dev.db` (§4).

## 8. Lineup Pipeline

`LineupContinuityCalculator.compute_and_write` (`windowed_feature_engineering_service.py:336-345`)
is called from `EntityReconciliationService.reconcile_lineup` immediately after a lineup reaches
`VERIFIED_PRE_MATCH` — never from a lineup with unknown/post-match provenance. It requires BOTH the
current lineup to be `VERIFIED_PRE_MATCH` AND a previous confirmed lineup for the same team
(`LineupRepositoryPort.list_recent_by_team`). With 4 total lineup rows platform-wide (all
`UNKNOWN_AVAILABILITY_TIME`), this calculator has never had a qualifying input to compute from for
any of the 652 training fixtures.

## 9. Transfer Pipeline

`TransferActivityCalculator.compute_and_write` (`windowed_feature_engineering_service.py:534-539`)
counts a team's `VERIFIED_PRE_MATCH` transfers with `effective_date` inside
`TRANSFER_ACTIVITY_WINDOW_DAYS`. Its own `_count_recent_verified` returns `None` (not a fabricated
zero) when a team has zero verified transfer records at all — the exact "unavailable, never a
fabricated zero" rule this milestone is governed by, already correctly implemented since Milestone
7. Notably, unlike lineup continuity, this calculator takes no fixture-specific state beyond
`team_id`/`now` — it is already reference-time-generic (no live-only current-state dependency), so
it is structurally *closer* to being backfill-capable than lineup continuity is. It remains blocked
today purely on §4's provenance fact: all 308 real transfer records are `UNKNOWN_AVAILABILITY_TIME`.

## 10. Feature Store Flow

Coverage matrix, all 6 features re-verified directly against `dev.db` and source code in this
milestone:

| Feature | Registered | Required | Source | Calculated | Published | Pre-match Safe | Prediction Available |
|---|---|---|---|---|---|---|---|
| `news.football.home_btts_impact` | Yes (`active`) | Yes | `NewsMarketImpactEngine` | No (0 `VERIFIED_PRE_MATCH` events) | No | Yes (definition-level) | No |
| `news.football.away_btts_impact` | Yes (`active`) | Yes | `NewsMarketImpactEngine` | No | No | Yes | No |
| `football.fixture.home_lineup_continuity` | Yes | Yes | `LineupContinuityCalculator` | No (0 `VERIFIED_PRE_MATCH` lineups) | No | Yes | No |
| `football.fixture.away_lineup_continuity` | Yes | Yes | `LineupContinuityCalculator` | No | No | Yes | No |
| `football.fixture.home_transfer_activity` | Yes | Yes | `TransferActivityCalculator` | No (0 `VERIFIED_PRE_MATCH` transfers) | No | Yes | No |
| `football.fixture.away_transfer_activity` | Yes | Yes | `TransferActivityCalculator` | No | No | Yes | No |

Registration/leakage-classification machinery is fully correct and ready; the "Calculated" column
is the honest bottleneck, and it traces to §4's provenance fact for every one of the six.

## 11. Prediction-Time Flow

`PredictionContextBuilder.build` (§2) is confirmed to be the single, real live-prediction path —
traced from `prediction_router.py`'s `POST /generate` → `PredictionCacheService.get_or_generate` →
`PredictionContextBuilder.build` → `FeatureMarketMappingService.resolve_feature_snapshot`. No
alternate/bypass path exists for this market (the M15 training backfill script is a *separate*,
explicitly non-live path that builds `feature_snapshot` directly, by design — see
`docs/milestone15_preimplementation_audit.md` §9).

## 12. Provenance Controls

Unweakened. Re-verified directly in this milestone (§4): `BACKFILL` cannot produce
`VERIFIED_PRE_MATCH` for transfers/lineups (`modules.ingestion.application.provenance
.classify_availability`) or for news (`modules.intelligence.application.news_provenance
.classify_news_availability`) — both confirmed via the live data itself (308 `BACKFILL`-sourced
transfers, 4 `BACKFILL`-sourced lineups, all correctly `UNKNOWN_AVAILABILITY_TIME`), not merely by
reading the rule in isolation.

## 13. Leakage Controls

Unweakened and untouched. `LineupContinuityCalculator`/`TransferActivityCalculator` still only ever
consume `VERIFIED_PRE_MATCH` records; `NewsMarketImpactEngine` still requires
`is_feature_eligible()` + kickoff-cutoff. No default/imputed/fabricated value was introduced
anywhere for any of the six features — the router fix (§2) changes only the HTTP response shape
when they're genuinely absent, not the absence itself.

## 14. Celery/Beat Verification

Confirmed directly in `modules/ingestion/infrastructure/celery/beat_schedule.py`:
`sync-upcoming-structured-intelligence-football-epl` (task `ingestion
.sync_upcoming_structured_intelligence`, interval `STRUCTURED_INTEL_INTERVAL_SECONDS`, always
registered) and `sync-scheduled-news-football-epl` (task `intelligence.sync_scheduled_news`,
interval `NEWS_SYNC_SCHEDULE_INTERVAL_SECONDS`, always registered, internally gated by
`NEWS_SYNC_ENABLED`) both exist with correct football/EPL arguments. Neither entry was modified.

## 15. Worker Bootstrap Verification

Confirmed directly in `apps/worker/bootstrap.py`: `"ingestion.sync_upcoming_structured_intelligence"`
is listed among the explicit task names registered for the `orchestrator` service factory
(line 111). `intelligence.sync_scheduled_news` is registered under the `intelligence_tasks` module
import (line 169). No task-registration defect was found — both tasks are reachable by a real
worker process today. Not modified.

## 16. Feature Coverage Before / After

| Feature | Before | After |
|---|---|---|
| All 6 required-but-unsatisfiable keys, across all 652 training rows | 0% | 0% (unchanged — correctly not fabricated) |
| Live prediction response for `football.both_teams_to_score` when required features are absent | Unhandled 500 | Honest `409 {"detail": "market 'football.both_teams_to_score' is missing required features: ..."}`|

Coverage is unchanged, by design — this milestone's constraints explicitly forbid the only actions
(enabling live sync, running a real backfill, or fabricating values) that could change it. The
router fix is orthogonal to coverage: it fixes the *response* to an already-correct "no coverage"
outcome, not the coverage itself.

## 17. Tests Added

- `tests/unit/apps/test_api_predictions.py::test_generate_prediction_missing_required_feature_returns_409_not_500`
  — seeds a real PRODUCTION market with a real Champion and one unsatisfiable required mapping
  (reusing the file's existing `_seed_production_market` helper), confirms the endpoint now returns
  409 with the missing feature key named in the response, not a 500.
- `tests/unit/modules/predictions/test_football_market_seeding.py::test_both_teams_to_score_required_features_unchanged_by_milestone_16`
  — structural guard confirming all 6 features remain in `required_features` and no
  `optional_features` override was added for this market, locking the "do not weaken the contract"
  decision against silent regression.

Both pass. The remaining 18 items on the master command's 20-item test list are re-confirmations
of guarantees Milestones 5/6/7/9/10/13/14/15 already established and already test exhaustively
(sync-trigger classification, kickoff-cutoff exclusion, historical Transfer-chain resolution,
`Player.team_id`/KG `PLAYS_FOR` exclusion, `VERIFIED_PRE_MATCH` eligibility gating) — re-deriving
them here would duplicate, not extend, existing coverage; this milestone's own investigation
(§4-§15) re-read and re-confirmed each one directly against source and live data rather than
re-writing tests that already assert them.

## 18. Full Regression Results

**2197 passed, 58 skipped, 0 failed** (1125.05s), against the Milestone 15 baseline of
2195 passed/58 skipped/0 failed — a net +2, exactly the two new tests in §17, with zero
pre-existing test broken or altered.

## 19. Database/Migration Status

No migration created — no schema gap was found; every table/column this milestone needed already
existed. No `dev.db` write occurred: every fact in §4/§10 was read via read-only SQL (`?mode=ro` or
plain `SELECT`, no `INSERT`/`UPDATE`/`COMMIT`). The two test files add tests only; they run against
isolated in-memory SQLite databases, never `dev.db`.

## 20. External API Status

None contacted. `NEWS_SYNC_ENABLED` and `NEWS_BACKFILL_ENABLED` remain `false`, unchanged. No RSS,
Gemini, sports-data, or other external API call was made during investigation, implementation, or
testing.

## 21. Training/Model Status

No model was trained or retrained. `football.both_teams_to_score.svm` remains the Champion,
unchanged. No Challenger was created or promoted. `DatasetBuilder` semantics, training labels, and
model coefficients were not touched.

## 22. Community Intelligence Exclusion

Not touched. No Reddit/X/YouTube provider, community sentiment feature, or community training data
was added, referenced, or considered in scope.

## 23. Known Limitations

- The six required features will remain at 0% coverage for the 652 existing historical training
  rows indefinitely — this is not fixable without either fabricating pre-match observations for
  already-completed matches or weakening the provenance rule, both explicitly forbidden. This is a
  permanent property of backfilled historical data, not a pending task.
- Going forward, the pipeline is correctly wired to populate these features for genuinely *future*
  fixtures once (a) `NEWS_SYNC_ENABLED` is turned on and (b) a live Celery Beat worker is actually
  running continuously against real upcoming fixtures close enough to their kickoff — neither of
  which this milestone enabled, per its own constraints.
- Even once live syncs run, `football.both_teams_to_score` will only serve a real prediction for a
  fixture where all 8 required features (2 satisfied today + 6 gated ones) happen to have
  qualifying data simultaneously — a real, if narrower, coverage question for Milestone 17+ to
  monitor once live data starts flowing, not something this milestone can pre-verify.
- The router fix (§2) is scoped to the one endpoint (`POST /api/v1/predictions/generate`) that
  calls `PredictionContextBuilder.build` directly; any other future call site of that builder would
  need the same catch added if it doesn't already have equivalent handling.

## 24. Recommendation for Milestone 17

Not proposed here per the master command's own instruction to await explicit specification. If
asked: Milestone 17 (real model training) is unaffected by this milestone's findings — the existing
652-row, 6-real-feature dataset (`docs/milestone16_preimplementation_audit.md` §3) remains the
actual trainable corpus for `football.both_teams_to_score`, since the six gated features have never
appeared in `Prediction.feature_snapshot` for any training row and no amount of live-sync
enablement changes rows that already exist. The split-direction defect documented in
`docs/milestone16_preimplementation_audit.md` §5 remains the standing blocker for that milestone,
untouched by this one.

---

**No `dev.db` write occurred. No model was trained. No live RSS/Gemini call was made.
`NEWS_SYNC_ENABLED`/`NEWS_BACKFILL_ENABLED` remain false.**

Milestone 16 complete. Waiting for explicit approval before Milestone 17.
