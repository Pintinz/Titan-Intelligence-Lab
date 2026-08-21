# Phase 1 — Football Historical Data Recovery + Half-Time Backfill + Training Preflight + Bootstrap Training

**Date:** 2026-08-18
**Scope:** The 4 football half-time markets that were stuck in "Insufficient historical data":
`football.first_half_winner`, `football.second_half_winner`, `football.first_half_goals`,
`football.first_half_both_teams_to_score`.

## 1. Root cause (confirmed, from Phase 0 audit)

`ApiFootballAdapter.fetch_fixtures` never parsed api-football's `score.halftime` field — every
half-time-dependent market resolver (`_first_half_winner`, `_second_half_winner`,
`_first_half_goals_over_under_0_5`, `_first_half_both_teams_to_score`) correctly required a
half-time score and correctly found none, for every football fixture ever synced. Basketball and
baseball's equivalent adapters already parsed their own per-period scores; football's simply never
had the analogous code. Fixed in Phase 0 (`api_sports_adapter.py`, `_extract_half_time_scores`).

## 2. Database snapshot

- Before: `dev.db`, 163,045,376 bytes (Phase 1 start).
- After: `dev.db`, 170,553,344 bytes (+7,507,968 bytes).
- No `.bak-*`/`.snapshot_*` file was created this phase — every write here is additive
  (`period_scores` column fill, new `Prediction`/`PredictionOutcome`/`Model` rows), never a
  destructive rewrite; the project's existing timestamped backups from prior phases remain
  untouched as a rollback point if ever needed.
- Row deltas: `fixtures` unchanged in count (7,829 — only `period_scores`/`version` updated on
  existing rows), `predictions` +3,704 (926 × 4 markets), `prediction_outcomes` +3,704, `models`
  +12 (3 new model rows × 4 markets: backfill-anchor candidate, trained challenger, promoted
  champion).

## 3. API-Football historical fixture resync

Target scope (confirmed via `provider_ref_index`, `provider='api_football'`,
`entity_kind='competition'`): Premier League (`competition_ref="39"`) and DFB-Pokal
(`competition_ref="81"`) — the only two football competitions genuinely api_football-sourced in
`dev.db`. English Football League Two is football_data_org-sourced and out of scope.

| Season fetch | Result |
|---|---|
| PL 2021 | REJECTED — `Free plans do not have access to this season, try from 2022 to 2024` |
| PL 2022 | 380/380 fetched, all updated |
| PL 2023 | 380/380 fetched, all updated |
| PL 2024 | 380/380 fetched, all updated |
| PL 2025 | REJECTED — same free-tier plan restriction |
| PL 2026 | REJECTED — same free-tier plan restriction |
| DFB-Pokal 2023 | 63/63 fetched, all updated |
| DFB-Pokal 2024 | 63/63 fetched, all updated |
| DFB-Pokal 2025 | REJECTED — same free-tier plan restriction |
| DFB-Pokal 2026 | REJECTED — same free-tier plan restriction |

**API calls:** 10 attempted, 5 succeeded, 5 failed with a genuine, honest provider-side rejection
(no retry attempted against a known-blocked season — the rejection message is explicit and
deterministic). **Quota:** no "request limit for the day" response was received this run (that
message exists in `dev.db`'s history from a prior, unrelated session's exhaustion, not today's).
**Fixtures updated:** 1,266/1,266 of every api_football-sourced fixture with a resolvable
half-time score — 100% of the addressable population for the 3 accessible seasons per
competition.

**External data:** not triggered. API-Football backfill fully covered the accessible seasons; no
Kaggle/web source was needed or accessed. **WEB REQUESTS: 0.**

### Implementation note — why a narrower script than the standing `SyncOrchestrator.sync_fixtures` path

The first attempt used `SyncOrchestrator.sync_fixtures` (the standing production sync path) as
directed. It surfaced two real, pre-existing infrastructure issues, both root-caused and resolved
before falling back to a narrower approach:

1. **No local Redis instance.** `SyncOrchestrator` and `SportsProviderRouter` both default to
   Redis-backed distributed lock/cache singletons in production wiring; no `redis-server`,
   Docker, or Windows Redis service was found on this machine. Worked around by substituting the
   in-memory `_InMemoryDistributedLock`/`_InMemorySyncCache` implementations `SportsProviderRouter`
   already falls back to when no Redis singleton is injected (the same objects every unit test
   uses) — a legitimate, already-supported configuration, not a new code path.
2. **SQLite lock contention with the live dev server.** The locally running `uvicorn` dev server
   (a separate process, started earlier in this session) held a competing lock on `dev.db`; two
   killed script attempts also left a stale rollback journal. Both were cleared (server stopped,
   journal recovered via a clean write) before retrying.

With both cleared, `sync_fixtures` still reliably hung — near-zero CPU, un-interruptible by
`asyncio.wait_for` — on the very first `EntityReconciliationService.reconcile_fixture` call for a
real (non-empty) fetch result, confirmed via three independent isolated diagnostics (raw
`fetch_fixtures` alone: succeeds in seconds; `reconcile_fixture` called directly, in complete
isolation, no other process touching the DB: still hangs on record 1). The exact line inside
`reconcile_fixture`'s side-effect chain (KG population, prediction-outcome resolution, form/
transfer/news-impact recomputation) was not further isolated — pursuing it further was out of
this phase's scope once a safe alternative was available.

Given these fixtures were **already correctly reconciled** (teams, scores, status) by the
pre-fix adapter — the only field genuinely missing was `period_scores` — a narrower script
(`scripts/backfill_football_half_time_scores.py`) was used instead: the exact same real
`SportsProviderRouter.fetch_fixtures` HTTP call and the exact same real
`SqlAlchemyFixtureRepository`/`ProviderRefIndexRepository` persistence layer, updating only
`period_scores` via `dataclasses.replace` + `FixtureRepository.upsert` — the identical merge
semantics `reconcile_fixture` itself already uses for this field, just without redundantly
re-running the rest of that method's side-effect chain for data that hadn't changed. **This is
not a parallel fetch/reconcile architecture** — no new provider integration, no new persistence
path, only a narrower composition of already-existing, unmodified components. The
`reconcile_fixture` hang itself is a real, separate, pre-existing issue and is flagged below as a
follow-up item — it was not fixed this phase.

## 4. Half-time data validation

- **Coverage, before:** 0/1,266 api_football-sourced football fixtures had `period_scores`
  populated (confirmed via a direct `provider_ref_index`-joined query during the Phase 1 audit).
- **Coverage, after:** 1,266/1,266 (100%) for the 3 accessible seasons per competition; genuinely
  0/[2021+2025+2026 fixtures] for the 3 free-tier-blocked seasons (never fabricated).
- **Integrity check:** half-time goals must never exceed full-time goals. Checked all 1,266
  updated fixtures — **0 violations**.

## 5. Entity reconciliation / provenance verification

- **Duplicate `provider_ref_index` fixture entries** (same provider+external_id mapped to >1
  entity): **0**.
- **Duplicate fixture rows** (same season+home+away+kickoff appearing more than once): **0**.
- No new teams, competitions, or fixtures were created this phase — every update targeted an
  already-reconciled `Fixture` row resolved through the existing `provider_ref_index`.

## 6. Label reconstruction for the 4 markets

`DatasetBuilder.build()` reads historical `PredictionOutcome`/`Prediction` rows, not `Fixture`
rows directly — these 4 markets had never had a Champion, so no historical predictions had ever
been generated or evaluated for them, regardless of `period_scores` now being correct. Backfilled
real `Prediction` + `PredictionOutcome` pairs (`scripts/backfill_half_time_market_training_data.py`)
using the exact same real resolvers `OutcomeResolutionService.resolve_for_fixture` uses for live
evaluation (`THREE_WAY_MARKET_RESOLVERS` for the two 3-way markets, `MARKET_OUTCOME_RESOLVERS` +
`MARKET_OUTCOME_LABELS` for the two binary markets) — same idiom as the existing
`backfill_match_winner_training_data.py`. Every `Prediction.value` is the same honest inert
anchor value already used for the 12-market and match_winner backfills (never a fabricated
historical prediction); every `PredictionOutcome.actual_value`/`error` is computed from the real,
now-backfilled half-time score.

| Market | Fixtures resolvable | Created | Skipped (no HT score) | Skipped (missing required feature) |
|---|---|---|---|---|
| first_half_winner | 1,818 completed w/ period_scores | 926 | 552 | 340 |
| second_half_winner | 1,818 | 926 | 552 | 340 |
| first_half_goals | 1,818 | 926 | 552 | 340 |
| first_half_both_teams_to_score | 1,818 | 926 | 552 | 340 |

1,818 = 1,266 (api_football, now with real half-time data) + 552 (historical
`football_data_co_uk` web import, genuinely no half-time data available — correctly skipped, not
guessed). 340 skipped for missing `football.fixture.form_shots_on_target_diff_last5` (older
fixtures predating that feature calculator).

## 7. Leakage audit

- Every resolver requires `home_score_ht`/`away_score_ht` (or full-time score for the label
  itself, which is definitionally what's being labeled) — never a feature.
- Feature snapshot for every backfilled sample is built from `feature_values_offline`, the same
  point-in-time feature store every live prediction reads from — no post-kickoff/post-match field
  is included in any `feature_snapshot`.
- `TrainingPreflightService`'s `intelligence_feature_leakage_safe` check: **PASS** for all 4
  markets — no required feature is classified `POST_MATCH_ONLY`.

## 8. Training preflight (`TrainingPreflightService.check`)

All 4 markets: **ready=True**, every individual check PASS — `sufficient_labeled_observations`
(926 ≥ 30 minimum), `labels_valid`, `temporal_reference_present`, `temporal_split_valid`
(chronological `TIME_SERIES_SPLIT` dry run), `feature_versions_known`,
`training_inference_feature_parity`, `required_feature_coverage_acceptable`,
`intelligence_feature_leakage_safe`, `dataset_reproducible` (stable content_hash across two
independent builds), `dataset_provenance_persisted`.

## 9. Training, empirical Champion selection, calibration status

`ScheduledRetrainingOrchestrator.run()` triggered for all 4 markets — every candidate (statistical
baseline and ML) trained and empirically compared, no forced/preferred winner:

| Market | Champion algorithm | Notes |
|---|---|---|
| first_half_winner | `ridge` | Linear/statistical baseline won empirically |
| second_half_winner | `ridge` | Linear/statistical baseline won empirically |
| first_half_goals | `mlp` | Neural net won empirically |
| first_half_both_teams_to_score | `logistic_regression` | Logistic regression won empirically |

All 4 previously-existing `heuristic_logistic_v1` placeholder rows (for `first_half_goals` and
`first_half_both_teams_to_score`) are correctly `retired`, not serving. `bootstrapped=True` for
all 4 (never-trained market — auto-promotion path, matching the existing consolidation rule).
**`calibration_ref`/`calibration_report_ref`: `NULL` for all 4 new Champions — no calibration
fitting was run this phase**, per the explicit Phase 1 scope boundary.

The existing 14 football Champions were **not retrained or touched** this phase. Their
`PROVENANCE_UNVERIFIED` status is the known, pre-existing Milestone 4 gap and was left exactly as
found.

## 10. Tests

`pytest tests/unit/modules/predictions tests/unit/modules/ingestion tests/unit/modules/sports -q`
→ **1,480 passed, 0 failed** (matches the pre-Phase-1 baseline — no regressions).

## 11. Follow-up item (not fixed this phase)

`EntityReconciliationService.reconcile_fixture` hangs indefinitely (near-zero CPU,
un-interruptible by `asyncio.wait_for`) when invoked directly against real fixture data in this
`dev.db`, independent of Redis/SQLite lock contention (both ruled out via isolated testing). This
blocks the standing `SyncOrchestrator.sync_fixtures` path for any future football fixture resync
until root-caused. Worth a dedicated investigation — likely candidates based on what the method's
call chain touches per record: `_resolve_prediction_outcomes` (evaluates every published
prediction on the fixture across every market), `kg.populate_fixture`, or the
form-differential/transfer-activity/news-market-impact recomputation calls.

## 12. Not started this phase (per explicit scope)

- SHAP / Gemini explainability.
- Live context synchronization pipeline.
- Celery Beat (untouched — no schedule changes).
- Calibration fitting for the 4 new Champions.
