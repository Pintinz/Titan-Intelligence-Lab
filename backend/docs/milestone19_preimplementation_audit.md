# Milestone 19 — Training/Inference Parity & Intelligence Feature Readiness

## Phase 1: Read-Only Audit + Phase 2: Implementation Plan (proposal only, not executed)

Status: **PHASE 1 COMPLETE — PHASE 2 PLAN PROPOSED — WAITING FOR EXPLICIT APPROVAL BEFORE PHASE 4 (IMPLEMENT)**

This document covers Milestone 19 Phases 1–2 only, per the master prompt's own RULE 10 STOP
protocol (`PHASE 3 — WAIT FOR APPROVAL` is a distinct stage from `PHASE 2 — IMPLEMENTATION
PLAN`). No code was changed to produce this report. No migration was applied. No model was
trained. `dev.db` was read-only for the entire audit (verified in §17).

---

## 1. Executive Summary

TitanIQ's football prediction platform has 14 genuinely-trained markets (real labels, real
historical features, real Champions — confirmed unchanged from Milestone 17). All 14 currently
**fail training/inference parity**: every one of them declares at least 4 "gated" intelligence
features (`home_lineup_continuity`, `away_lineup_continuity`, `home_transfer_activity`,
`away_transfer_activity`, and for 9 of the 14, two `news.*` impact features) as
`is_required=True` in `feature_market_mappings` — and **none of those gated features has ever
appeared in a single historical training sample**, across ~11,000 historical predictions,
verified two independent ways (§4, §9).

This is not a bug in any calculator, and Milestone 16's fix (turning `MissingRequiredFeatureError`
into an honest 409 instead of a silent 500) remains correct and untouched. The root cause is
structural and was already identified in Milestone 16/17: `VERIFIED_PRE_MATCH` provenance for
news/lineup/transfer data can only ever be produced by the `LIVE_SCHEDULED` Celery Beat sync path
(confirmed correct and intact, §6), and that path has not yet accumulated a single legitimately
classified observation in `dev.db` — `lineups` (4 rows), `transfers` (308 rows), and `news_events`
(68 rows) are **100% `UNKNOWN_AVAILABILITY_TIME`**, with zero `VERIFIED_PRE_MATCH` rows anywhere.

Two additional, previously under-quantified gaps were confirmed this milestone:
- **Feature-version provenance breaks at the exact moment a feature snapshot is built** — nothing
  from `resolve_feature_snapshot()` downward (`Prediction.feature_snapshot`, `TrainingSample`,
  `Dataset`, `DatasetLineage`) carries a per-sample feature version. `ModelDefinition.feature_versions`
  is populated (Milestone 4's fix works), but reports "whatever `FeatureDefinition.version` is
  *right now*," not what version the training sample was actually built with (§10).
- **Zero Dataset/TrainingRun rows have ever been durably persisted** — `get_dataset_repo()` in
  `apps/api/composition.py` is wired to `InMemoryDatasetRepository()` by explicit design (matching
  Milestone 17's finding), and no code path anywhere constructs a `TrainingRunModel` row despite
  the table existing since Milestone 4. This is a known, documented posture (ADR-008
  mock-first/adapter-swap), not an oversight (§11).

**Bottom line for §13/§22: NO MARKET IS READY FOR M20 TRAINING.** The smallest remaining blocker
is identical across all 14 markets: zero real `VERIFIED_PRE_MATCH` lineup/transfer observations
exist yet, for any fixture, past or upcoming, in this `dev.db`.

---

## 2. Audit Scope

Read-only. Inspected (via 4 parallel research passes + direct file reads + direct `dev.db`
read-only SQL, `sqlite3.connect("file:dev.db?mode=ro", uri=True)`):

- `modules/features/domain/entities.py`, `feature_registration_service.py`, `feature_store_service.py`
- `modules/predictions/application/feature_market_mapping_service.py`, `dataset_builder_service.py`,
  `dataset_splitter.py`, `training_pipeline_service.py`, `model_selection_service.py`,
  `model_registry_service.py`, `scheduled_retraining_orchestrator.py`, `backtest_service.py`,
  `validation_service.py`, `windowed_feature_engineering_service.py`,
  `historical_feature_reconstruction_service.py`, `news_market_impact_engine.py`,
  `news_market_impact_registry.py`
- `modules/predictions/domain/entities.py`, `dataset.py`, `ports/dataset_repository.py`,
  `ports/ml_model.py`, `infrastructure/persistence/{models,mappers}.py`,
  `infrastructure/persistence/in_memory_dataset_repository.py`
- `modules/intelligence/domain/entities.py`, `news_provenance.py`, `news_validity_policy.py`,
  `historical_news_relevance_engine.py`, `historical_entity_resolution_service.py`,
  `feature_store_enrichment_service.py`, `news_ingestion_service.py`, `news_relevance_filter.py`,
  `scheduled_news_sync_service.py`, `news_backfill_service.py`
- `modules/sports/domain/entities.py` (`Transfer.effective_date`)
- `modules/ingestion/infrastructure/celery/beat_schedule.py`, `tasks.py`,
  `modules/ingestion/application/sync_orchestrator.py`, `entity_reconciliation_service.py`
- `apps/api/composition.py`, `apps/api/routers/prediction_router.py`
- `scripts/backfill_squad_intelligence.py`
- `dev.db` (read-only): `prediction_markets`, `models`, `feature_market_mappings`,
  `feature_definitions`, `feature_definition_versions`, `feature_values_offline`, `datasets`,
  `training_runs`, `model_artifacts`, `model_evaluations`, `news_events`, `news_articles`,
  `lineups`, `transfers`, `predictions.feature_snapshot`, `intelligence_sync_runs`

No file was modified. No migration was written or applied.

---

## 3. Markets Audited

38 total markets (unchanged from Milestone 17): 19 football, 7 basketball, 6 baseball,
6 table_tennis. Basketball/baseball/table_tennis remain Champion-less (0 rows with
`models.status='champion'` for any non-football market — reconfirmed this milestone, §17).

Of the 19 football markets, **14 are genuinely trained** (`prediction_outcomes` count > 0,
reconfirmed identical to Milestone 17's counts):

| Market | Outcomes | Algorithm | Model version |
|---|---|---|---|
| `football.correct_score` | 824 | logistic_regression | v2 |
| `football.total_goals_over_under_4_5` | 823 | catboost_gbm | v2 |
| `football.total_goals_over_under_3_5` | 823 | gaussian_nb | v2 |
| `football.total_goals_over_under_1_5` | 823 | catboost_gbm | v2 |
| `football.total_goals_over_under_0_5` | 823 | catboost_gbm | v2 |
| `football.total_goals_over_under` | 823 | elastic_net | v2 |
| `football.home_win_to_nil` | 823 | catboost_gbm | v2 |
| `football.home_team_total_goals` | 823 | catboost_gbm | v2 |
| `football.home_clean_sheet` | 823 | logistic_regression | v2 |
| `football.away_win_to_nil` | 823 | catboost_gbm | v2 |
| `football.away_team_total_goals` | 823 | lightgbm_gbm | v2 |
| `football.away_clean_sheet` | 823 | catboost_gbm | v2 |
| `football.match_winner` | 654 | logistic_regression | v2 |
| `football.both_teams_to_score` | 652 | svm | v2 |

The remaining 5 football markets (`first_half_both_teams_to_score`, `first_half_goals`,
`first_half_winner`, `second_half_winner`, `match_result`) are heuristic placeholders
(`algorithm='heuristic_logistic_v1'`, `dataset_version=None`, `artifact_ref=None`,
0 `prediction_outcomes`) — unchanged from Milestone 17, out of scope for M20 candidacy.
`match_result` is additionally `status='deprecated'`.

---

## 4. Training Feature Inventory

`DatasetBuilder.build()` (`dataset_builder_service.py:190-194`) constructs `TrainingSample.features`
by copying `Prediction.feature_snapshot` verbatim — it does not call the Feature Store or any
calculator directly. So "what training actually used" is exactly what real historical
`Prediction.feature_snapshot` rows contain. Direct inspection of every `feature_snapshot`
ever recorded for the 14 trained markets (729–906 rows per market) shows the **feature key set
is identical across all runs for a given market pattern** — no partial/missing-key rows, no
schema drift within a market. Aggregated by market:

| Market pattern | Feature keys ever present in `feature_snapshot` |
|---|---|
| `*_clean_sheet`, `*_win_to_nil`, `*_team_total_goals`, `total_goals_over_under*` | `expected_home_goals`, `expected_away_goals`, `form_corners_diff_last5`, `form_fouls_diff_last5`, `form_possession_pct_diff_last5`, `form_shots_on_target_diff_last5`, `form_shots_total_diff_last5` (7 keys) |
| `both_teams_to_score` | `form_corners_diff_last5`, `form_fouls_diff_last5`, `form_possession_pct_diff_last5`, `form_shots_on_target_diff_last5`, `form_shots_total_diff_last5`, `market.overround` (6 keys) |
| `correct_score` | `expected_home_goals`, `expected_away_goals`, `form_shots_on_target_diff_last5`, `market.implied_probability_home` (4 keys) |
| `match_winner` | `form_corners_diff_last5`, `form_fouls_diff_last5`, `form_possession_pct_diff_last5`, `form_shots_on_target_diff_last5`, `form_shots_total_diff_last5`, `market.implied_probability_away`, `market.implied_probability_home` (7 keys) |

**Zero occurrences, in any of the ~11,000 historical `feature_snapshot` rows inspected, of**:
`football.fixture.home_lineup_continuity`, `football.fixture.away_lineup_continuity`,
`football.fixture.home_transfer_activity`, `football.fixture.away_transfer_activity`,
`news.football.home_goal_impact`, `news.football.away_goal_impact`,
`news.football.home_btts_impact`, `news.football.away_btts_impact`,
`news.football.home_clean_sheet_impact`, `news.football.away_clean_sheet_impact`.

Cross-checked against the offline Feature Store directly: `feature_values_offline` has 68,223
rows across exactly **11 distinct `feature_key`s**, none of which is any lineup/transfer/news
key (confirmed by `LIKE '%lineup_continuity%' OR LIKE '%transfer_activity%' OR LIKE 'news.%'`
returning 0 rows). Both independent sources agree: **the 6 gated features have never been
computed for a single historical fixture.**

---

## 5. Inference Feature Inventory

`feature_market_mappings` (184 rows total, football subset queried directly) declares, for every
one of the 14 trained markets, at minimum the 4 gated lineup/transfer features as
`is_required=True`; 9 of the 14 (`*_clean_sheet`, `*_win_to_nil`, `*_team_total_goals`,
`total_goals_over_under*`) additionally require the matching pair of `news.*` impact features.
Full per-market required-feature lists:

| Market | Required (gated) | Required (core) | Optional |
|---|---|---|---|
| `away_clean_sheet` / `home_clean_sheet` | lineup×2, transfer×2, news.clean_sheet_impact×2 (6) | expected_home/away_goals (2) | — |
| `away_win_to_nil` / `home_win_to_nil` | lineup×2, transfer×2, news.clean_sheet_impact×2 (6) | expected_home/away_goals (2) | — |
| `away_team_total_goals` / `home_team_total_goals` | lineup×2, transfer×2, news.goal_impact×2 (6) | expected_home/away_goals (2) | — |
| `total_goals_over_under` (+4 threshold variants) | lineup×2, transfer×2, news.goal_impact×2 (6) | expected_home/away_goals (2) | — |
| `both_teams_to_score` | lineup×2, transfer×2, news.btts_impact×2 (6) | form_shots_on_target_diff, overround (2) | 5 form diffs |
| `correct_score` | lineup×2, transfer×2 (4) | expected_home/away_goals, form_shots_on_target_diff, implied_probability_home (4) | — |
| `match_winner` | lineup×2, transfer×2 (4) | form_shots_on_target_diff, implied_probability_home/away (3) | 5 form diffs |

Every required "core" feature (`expected_*_goals`, `market.implied_probability_*`,
`market.overround`, `form_shots_on_target_diff_last5`) **does** appear in historical training
data (§4) — these are the features that give the 14 markets their real predictive signal today.
The required gated features do not, and never have.

---

## 6. Training/Inference Parity Matrix

| MARKET | TRAINING COVERAGE (gated) | LIVE COVERAGE (gated) | HISTORICAL RECONSTRUCTABILITY | TEMPORAL SAFETY | PARITY | STATUS |
|---|---|---|---|---|---|---|
| away_clean_sheet | 0% | 0% | NO | YES (M18) | FAIL | NOT_READY |
| away_team_total_goals | 0% | 0% | NO | YES | FAIL | NOT_READY |
| away_win_to_nil | 0% | 0% | NO | YES | FAIL | NOT_READY |
| both_teams_to_score | 0% | 0% | NO | YES | FAIL | NOT_READY |
| correct_score | 0% | 0% | NO | YES | FAIL | NOT_READY |
| home_clean_sheet | 0% | 0% | NO | YES | FAIL | NOT_READY |
| home_team_total_goals | 0% | 0% | NO | YES | FAIL | NOT_READY |
| home_win_to_nil | 0% | 0% | NO | YES | FAIL | NOT_READY |
| match_winner | 0% | 0% | NO | YES | FAIL | NOT_READY |
| total_goals_over_under (+4 variants) | 0% | 0% | NO | YES | FAIL | NOT_READY |

"LIVE COVERAGE" = fraction of fixtures for which a required gated feature currently resolves
to a real value in the Feature Store; 0% because `lineups`/`transfers`/`news_events` have zero
`VERIFIED_PRE_MATCH` rows today (§7–§8). "HISTORICAL RECONSTRUCTABILITY" = NO because no
dedicated reconstruction path exists for lineup continuity or transfer activity (unlike news,
which has `HistoricalNewsRelevanceEngine` for that exact purpose, §9) — the *only* way either
feature ever gets a value, past or present, is a real `EntityReconciliationService.reconcile_lineup`
/ `reconcile_fixture` run recording a genuinely `VERIFIED_PRE_MATCH` `Lineup`/`Transfer` row.

No feature was made optional to produce this matrix. Milestone 16's `MissingRequiredFeatureError`
→ 409 translation remains exactly as implemented; RULE 5 of the M19 prompt is honored.

---

## 7. News Intelligence Readiness

Re-confirmed and extended from Milestone 9/10/13/14/16 (independent audit pass, this milestone):

1. **Can `BACKFILL` produce `VERIFIED_PRE_MATCH`? NO.** `news_provenance.py:70-71`:
   `if trigger is not SyncTrigger.LIVE_SCHEDULED: return ...UNKNOWN_AVAILABILITY_TIME`. Strict
   equality against one enum value; `news_backfill_service.py` always passes
   `trigger=SyncTrigger.BACKFILL`.
2. **Can `ADMIN_MANUAL` produce `VERIFIED_PRE_MATCH`? NO.** Same conditional catches it.
3. **Is `LIVE_SCHEDULED` the only legitimate path? YES.** `scheduled_news_sync_service.py`
   hardcodes `trigger=SyncTrigger.LIVE_SCHEDULED` internally with no caller-supplied override;
   `sync_scheduled_news_task` (Celery) has no `trigger` parameter at all. Grep across `modules/`
   confirms exactly one production call site ever sets `SyncTrigger.LIVE_SCHEDULED`.
4. **Are post-kickoff events rejected? YES.** `news_market_impact_engine.py:209-211` calls
   `is_information_available_before_kickoff` (`news_provenance.py:77-89`), strict inequality
   (`information_available_at < kickoff`), additive to the TTL/eligibility check.
5. **Does `HISTORICALLY_RELEVANT` bypass `is_feature_eligible()`? NO.** They are distinct
   classifications; `is_feature_eligible()` (`NewsEvent`, `entities.py:125-133`) requires
   `availability_classification == VERIFIED_PRE_MATCH` AND every resolved entity `RESOLVED` —
   `HistoricalNewsRelevanceEngine`'s `HISTORICALLY_RELEVANT` path never sets that field and
   never writes a feature directly.
6. **Does historical player-team resolution ever use `Player.team_id` or KG `PLAYS_FOR`? NO.**
   `HistoricalEntityResolutionService` resolves membership exclusively via
   `TransferRepositoryPort.list_by_player` chained by `Transfer.effective_date`
   (`historical_entity_resolution_service.py:61-96`, returns
   `team_id=latest_transfer.to_team_id`). Every `Player.team_id`/`PLAYS_FOR` reference found by
   grep in historical-labeled files is a comment documenting the exclusion, not a live read.

Current `dev.db` state: `news_events` = 68 rows, **100% `UNKNOWN_AVAILABILITY_TIME`**
(`event_type` breakdown: transfer 39, manager_change 24, injury 2, suspension 1,
training_update 1, weather_report 1). `intelligence_sync_runs` shows 23 runs, all
`trigger='manual'` — zero `LIVE_SCHEDULED` runs have executed in this `dev.db` yet (consistent
with `NEWS_SYNC_ENABLED` defaulting to `false`, confirmed absent from `.env`, §18).

**Verdict: News Intelligence architecture is correctly and safely wired end-to-end, but has
produced zero training-eligible observations to date.** This is honest, fail-closed behavior,
not a defect.

---

## 8. Historical News Training Readiness

Per §7, `is_feature_eligible()` is the sole gate for a `NewsEvent` reaching a feature, and it can
only be satisfied by a `VERIFIED_PRE_MATCH` classification, which can only come from
`LIVE_SCHEDULED`. Classifying all 68 current `news_events`:

| Classification | Count |
|---|---|
| NEWS_TRAINING_ELIGIBLE | 0 |
| NEWS_UNKNOWN_AVAILABILITY | 68 |
| NEWS_HISTORICALLY_RELEVANT_BUT_PROVENANCE_UNVERIFIED | 0 (none evaluated via `HistoricalNewsRelevanceEngine` outside test fixtures) |
| NEWS_ENTITY_UNRESOLVED / NEWS_MARKET_UNRESOLVED / NEWS_POST_KICKOFF / NEWS_INVALID | not reached — all 68 fail the availability gate first |

No availability timestamp was fabricated to produce this table — `information_available_at` is
`NULL` on every one of the 68 `news_events` and 199 `news_articles` rows queried; the
`UNKNOWN_AVAILABILITY_TIME` classification is the honest default, never backfilled from
`published_at`.

---

## 9. Lineup Intelligence Readiness

`LineupContinuityCalculator` (`windowed_feature_engineering_service.py:268`) is the **sole**
implementation — one class, one write path (`EntityReconciliationService.reconcile_lineup`,
`entity_reconciliation_service.py:632`), used identically for both the live-sync path
(`SyncTrigger.LIVE_SCHEDULED`) and any historical/backfill path. There is no second,
training-specific reimplementation — confirmed by grepping every call site of
`compute_and_write` across `modules/`. Formula: `|current_starters ∩ previous_starters| /
|previous_starters|`, gated to fire only when the just-reconciled `Lineup.availability_classification
== VERIFIED_PRE_MATCH`; returns `None` (never a fabricated 0) when no prior lineup exists.
Leakage class hardcoded `PRE_MATCH_SAFE`; TTL 24h.

Because the *same* calculator is used everywhere, there is **no training/inference semantic
mismatch** for this feature — the parity failure in §4–§6 is entirely a *coverage* problem
(the calculator has essentially never fired with a `VERIFIED_PRE_MATCH` lineup available), not a
*definition* problem.

Current `dev.db` state: `lineups` = 4 rows, **100% `UNKNOWN_AVAILABILITY_TIME`**. All 4 were
recorded via `scripts/backfill_squad_intelligence.py`, which explicitly passes
`trigger=SyncTrigger.BACKFILL` (quoted, lines 68-69, 112) — correctly and honestly excluded from
`VERIFIED_PRE_MATCH` per §7's rule.

---

## 10. Transfer Intelligence Readiness

`TransferActivityCalculator` (`windowed_feature_engineering_service.py:461`), same single-path
finding as §9 (`EntityReconciliationService._compute_transfer_activity` is the only caller).
Formula: `count(transfers where availability_classification == VERIFIED_PRE_MATCH and
effective_date in [now-30d, now))`; returns `None` (not a fabricated 0) if zero verified records
exist for the team. Leakage class `PRE_MATCH_SAFE`.

`Transfer.effective_date` (`modules/sports/domain/entities.py:340`, required field) is the sole
temporal key used — the calculator never reads `Player.team_id` or any roster "current
membership" field; team scoping comes from the `team_id` argument the caller passes
(`fixture.home_team_id`/`away_team_id`), not from a Player lookup.

Current `dev.db` state: `transfers` = 308 rows, **100% `UNKNOWN_AVAILABILITY_TIME`** (all from
`scripts/backfill_squad_intelligence.py`'s explicit `SyncTrigger.BACKFILL`, same as §9).

---

## 11. Historical Entity-Resolution Status

`HistoricalEntityResolutionService` correctly walks `Transfer.effective_date` chains and never
touches `Player.team_id`/KG `PLAYS_FOR` (§7 point 6, independently re-verified by the
lineup/transfer research pass). This mechanism is sound and ready; it is not the blocking factor
— the blocking factor is upstream (zero `VERIFIED_PRE_MATCH` source rows to resolve against, §7–§10).

---

## 12. Feature-Version Traceability

Chain as it exists in code today:

1. `FeatureDefinition.version` (`modules/features/domain/entities.py:42`, default `1`) — bumped
   only by `FeatureRegistrationService.update_formula` (`feature_registration_service.py:196`),
   which also snapshots the pre-bump state into `feature_definition_versions`
   (`FeatureDefinitionVersionModel`).
2. **Break point**: `FeatureMarketMappingService.resolve_feature_snapshot`
   (`feature_market_mapping_service.py:98-118`) returns `dict[str, float]` — key→value only, no
   version attached. Nothing downstream (`Prediction.feature_snapshot`, `TrainingSample.features`,
   `DatasetLineage.feature_keys`, `Dataset`) has a field to carry a per-sample version even in
   principle — `DatasetLineage` carries `feature_keys: tuple[str, ...]` only.
3. `ModelDefinition.feature_versions` **is** populated today — by
   `AutomaticModelSelectionService._resolve_feature_versions()`
   (`model_selection_service.py:221-233`), which looks up each `dataset.lineage.feature_keys`
   against the **live/current** `FeatureDefinitionRepositoryPort` at registration time. This
   correctly fixed Milestone 4's "always `{}`" bug, but it reports "whatever version each
   feature is *right now*," not "what version the training sample was actually built with" —
   if a feature's formula/version changed between the oldest and newest sample in a dataset,
   the recorded version would be wrong for the older samples. There is currently no way to
   detect or correct for this, because no per-sample version was ever captured.
4. `feature_definition_versions` (the audit-history table) is write-only in production code —
   `FeatureVersionRepositoryPort.list_by_feature` is implemented but never called by any
   application-layer code (`AutomaticModelSelectionService`, `DatasetBuilder`, or anything else
   in `modules/predictions`). It is a dead-read table today.

This is real and correctly scoped: **not a defect introduced by any prior milestone** — Milestone
4's fix (recording *a* version) works exactly as designed; the deeper gap (per-sample historical
versioning) was never in scope until this audit made it explicit.

---

## 13. Dataset Provenance

`Dataset` (`modules/predictions/domain/dataset.py:106-119`) fields: `id`, `market_id`, `version`,
`content_hash`, `samples`, `statistics`, `lineage` (nested: `market_id`, `source_prediction_ids`,
`feature_keys`, `built_at`, `class_labels`), `quality_issues`, `status`, `created_at`,
`approved_by`, `approved_at`. `DatasetBuilder.build()` populates all of these except
`approved_by`/`approved_at` (set later, only in-memory, by `DatasetRegistryService.approve()`).
There is no split-strategy/train-boundary field and no leakage-classification field anywhere on
`Dataset` — split strategy is a transient parameter to `TrainingPipelineService.train()`, never
written back.

**Zero `Dataset` rows have ever been persisted to `dev.db`, and the reason is a deliberate,
documented architectural posture, not a bug**: `apps/api/composition.py:935-941`
(`get_dataset_repo()`) is `@lru_cache`-wired to `InMemoryDatasetRepository()` with an explicit
comment citing "ADR-008 mock-first/adapter-swap posture... a SQL-backed implementation is future
work, added when a real production need for persistence-across-restarts shows up." `DatasetModel`
(the ORM class matching the `datasets` table) exists (`infrastructure/persistence/models.py:172-192`)
but has no mapper and no SQL-backed repository implementation anywhere in the codebase — dead
schema by design, same posture as `PlattScalingCalibrator`. `TrainingRunModel` (`datasets`'
sibling `training_runs` table) is equally unimplemented dead schema — no repository, no mapper,
and `TrainingPipelineService.train()` never even takes a dataset-repository dependency (it
operates on an in-memory `Dataset` object passed as a plain argument).

What **is** captured today for a new training run: `ModelDefinition.training_dataset_ref`,
`dataset_version` (`= dataset.version`), `feature_versions` (§12's caveat applies),
`training_run_ref`, a **real, durably saved** `artifact_ref` (`artifact_store.save()` writes an
actual `.bin` file — confirmed: all 12 non-heuristic champions have a real `.model_artifacts\...`
path). So model *artifacts* are durable; the *dataset that produced them* is not.

---

## 14. Champion Provenance

All 47 `models` rows, all 19 football markets' champions: `provenance_status =
'PROVENANCE_UNVERIFIED'`, `feature_versions = '{}'` (literal empty JSON object), unchanged from
Milestone 17. `training_run_ref` is `NULL` for every row (consistent with §13 — no
`TrainingRun` was ever persisted to reference). This is not touched by this milestone; no
Champion was modified, retrained, or reclassified.

---

## 15. Temporal Validation Status

Unchanged and reconfirmed from Milestone 18: `dataset_splitter.split()` sorts all 4 temporal
strategies (`HOLDOUT`, `ROLLING_WINDOW`, `WALK_FORWARD`, `TIME_SERIES_SPLIT`) ascending by
`TrainingSample.reference_time` before slicing, asserts
`train[-1].reference_time <= test[0].reference_time` on every fold, and raises
`MissingTemporalReferenceError` (fail-closed) if any sample lacks a `reference_time`.
`AutomaticModelSelectionService` defaults to `TIME_SERIES_SPLIT`. **Temporal validation remains
trustworthy** — no code touched this milestone, and this audit confirms nothing since M18
regressed it.

---

## 16. Training Preflight Status

No `TrainingPreflightService` exists today. Applying the 16-point checklist from the master
prompt's §15, by hand, against `football.both_teams_to_score` as a representative case:

| Check | Result |
|---|---|
| Market exists | PASS |
| Sufficient labeled observations | PASS (652) |
| Labels valid | PASS |
| No temporal reference missing | PASS (M18) |
| Temporal split valid | PASS (M18) |
| Feature set explicitly declared | PASS (`feature_market_mappings`) |
| Training feature versions known | PARTIAL (§12 — current-version-only, not per-sample) |
| Inference feature manifest known | PASS |
| **Training/inference feature parity** | **FAIL** (§4–§6) |
| Required feature coverage acceptable | **FAIL** (0% for 4-6 required features) |
| Intelligence provenance valid | PASS (architecture correct; §7 volume is 0) |
| No post-kickoff information | PASS |
| No `UNKNOWN_AVAILABILITY_TIME` feature used | PASS (none reach a feature — §7 point 5) |
| No unresolved historical membership used | PASS |
| Dataset reproducibility verified | PASS (M18 content hash) |
| Dataset content hash generated | PASS |
| Training dataset provenance complete | **FAIL** (§13 — never persisted) |

**Overall: BLOCKED.** Same result for all 14 markets — the two FAIL rows are identical across
every one of them.

---

## 17. Database Verification

Row counts, before and after this audit (read-only throughout — no `INSERT`/`UPDATE`/`DELETE`
issued):

| Table | Count |
|---|---|
| fixtures | 6834 |
| teams | 215 |
| players | 100 |
| prediction_markets | 38 |
| models | 47 |
| predictions | 12436 |
| prediction_outcomes | 11183 |
| feature_values_offline | 68223 |
| feature_definitions | 45 |
| feature_market_mappings | 184 |
| news_events | 68 |
| news_articles | 199 |
| transfers | 308 |
| lineups | 4 |
| provider_ref_index | 7529 |
| datasets | 0 |
| training_runs | 0 |
| model_artifacts | 0 |
| model_evaluations | 0 |
| feature_definition_versions | 0 |

Identical to Milestone 17/18's snapshot except `provider_ref_index` (untouched by this milestone;
value shown reflects current state). No write connection was opened at any point —
`sqlite3.connect("file:dev.db?mode=ro", uri=True)` was used for every query in this audit.

---

## 18. External API Verification

`NEWS_SYNC_ENABLED` / `NEWS_BACKFILL_ENABLED` absent from `.env` (grep confirmed) → both default
to `false` per `news_sync_config.py`/`news_backfill_config.py`. No RSS, Gemini, or Community API
call was made during this audit — every action taken was a local file `Read`/`Grep` or a
read-only `dev.db` query. `intelligence_sync_runs` shows no new rows created during the audit
window.

---

## 19. Model/Training Verification

No `model.fit()` call was made. No `TrainingPipelineService.train()` invocation occurred. No
Challenger was created or registered. No Champion was promoted, retired, or modified. All 47
`models` rows are byte-for-byte the state described in Milestone 17/18.

---

## 20. Remaining Blockers (ranked, smallest first)

1. **Zero `VERIFIED_PRE_MATCH` lineup/transfer/news observations exist in `dev.db`**, for any
   fixture — the identical blocker for all 14 markets. The architecture that would produce them
   (`LIVE_SCHEDULED` Celery Beat sync → `EntityReconciliationService` → the two calculators / news
   pipeline) is confirmed correctly wired end-to-end; it simply has not run for real upcoming
   fixtures yet in this environment (`NEWS_SYNC_ENABLED=false`, `intelligence_sync_runs` shows
   zero `LIVE_SCHEDULED` runs).
2. **No durable Dataset/TrainingRun persistence** — a known, documented (ADR-008) posture, not
   a surprise, but it means today's dataset provenance is only reconstructable within one
   process's lifetime, and there's no audit trail for a hypothetical M20 training run.
3. **Feature-version provenance is per-registration, not per-sample** — correct today (reports a
   real, current version, not a fabricated one) but would silently misattribute an older
   sample's true version if a feature formula changes mid-dataset. Not currently manifesting as
   an error (no feature version has ever been bumped in this `dev.db`), but structurally latent.
4. **No `TrainingPreflightService` exists** — the 16-point checklist in §16 was applied by hand
   this milestone; there's no automated, repeatable gate a future M20 attempt would run against
   before training.

---

## 21. Phase 2 — Implementation Plan (proposal, not executed)

Per RULE 7 and RULE 10, the following is a **plan only**. Nothing below has been implemented.

**Proposed for this milestone, additive and safe (no schema change, no existing behavior
touched):**

- **`TrainingPreflightService`** — a new, pure read-only application service in
  `modules/predictions/application/`, taking a `market_id` and returning a structured
  READY/BLOCKED verdict with itemized reasons, mechanizing the §16 checklist. It would read
  existing state only (`feature_market_mappings`, `feature_values_offline`/recent
  `Prediction.feature_snapshot`, `lineups`/`transfers`/`news_events.availability_classification`,
  and `DatasetSplitter`'s `reference_time` requirement) — no writes, no new tables, no changes to
  `TrainingPipelineService`, `AutomaticModelSelectionService`, or any existing predictor/training
  code path. Would ship with unit tests covering: market not found, insufficient observations,
  invalid labels, missing temporal reference, feature-set not declared, required-feature 0%
  coverage (the case every one of the 14 markets is in today), `UNKNOWN_AVAILABILITY_TIME`
  rejection, and a synthetic all-PASS case.
- A corresponding read-only admin/CLI entry point (mirroring the existing `scripts/`
  pattern) to run the preflight check against any market and print the itemized verdict —
  useful for a future M20 to consult before requesting training authorization.

**Explicitly NOT proposed for this milestone (require a separate, dedicated approval per RULE 7):**

- Any schema change to persist `Dataset`/`TrainingRun` rows (would need a new
  `SqlAlchemyDatasetRepository` + mapper against the already-existing `datasets`/`training_runs`
  tables — no new migration needed since the tables exist, but this is still a durability/behavior
  change large enough to warrant its own explicit go-ahead separate from a read-only preflight
  service).
- Any change to carry a per-sample feature version through
  `resolve_feature_snapshot`→`Prediction.feature_snapshot`→`TrainingSample`→`Dataset` — this
  would very likely require restructuring `feature_snapshot`'s stored shape (today a flat
  `dict[str, float]`) or adding a companion field, which touches a widely-read production column.
- Anything that runs the `LIVE_SCHEDULED` sync for real (would require `NEWS_SYNC_ENABLED=true`
  and live RSS/Gemini calls) — explicitly out of scope per RULE 4, and the only thing that would
  actually resolve blocker #1 in §20. That is an operational/data-accumulation decision for the
  user, not a code change.

---

## 22. M19 Final Decision (Phase 1/2 checkpoint)

MILESTONE 19 STATUS:
PHASE 1/2 COMPLETE — BLOCKED ON APPROVAL FOR PHASE 4

TEMPORAL VALIDATION:
PASS

TRAINING/INFERENCE PARITY:
FAIL (all 14 genuinely-trained markets — 0% historical coverage of required gated features)

NEWS INTELLIGENCE:
PARTIALLY READY (architecture correct and intact; zero real observations yet)

STRUCTURED INTELLIGENCE:
PARTIALLY READY (single-calculator parity confirmed correct; zero real `VERIFIED_PRE_MATCH` observations yet)

FEATURE VERSION PROVENANCE:
PARTIALLY READY (per-registration version recorded correctly; per-sample historical version not captured)

DATASET PROVENANCE:
BLOCKED (documented in-memory-only posture; zero durable rows)

TRAINING PREFLIGHT:
BLOCKED (no automated gate exists; manual check in §16 shows FAIL on 2 of 16 criteria for every market)

FIRST M20 CANDIDATE:
NONE — see §1/§20: "NO MARKET IS READY FOR M20 TRAINING," identical smallest blocker across all 14

MODEL TRAINING PERFORMED:
NO

CHAMPION MODIFIED:
NO

LIVE RSS/GEMINI CALLS:
NO

COMMUNITY INTELLIGENCE:
OUT OF SCOPE

DATABASE MODIFIED:
NO

REGRESSIONS:
N/A — no code changed in Phase 1/2

M19 AUDIT REPORT:
docs/milestone19_preimplementation_audit.md

**STOPPING HERE per RULE 10 PHASE 3. Waiting for explicit approval of the Phase 2 plan (§21)
before any implementation (Phase 4) begins. Do not proceed to Milestone 20 under any
circumstances until Milestone 19 is fully closed.**
