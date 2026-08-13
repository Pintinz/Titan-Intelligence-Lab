# Milestone 19 — Training/Inference Parity & Intelligence Feature Readiness

## Phase 4-8: Implementation, Testing, Verification, Final Report

Status: **MILESTONE 19 COMPLETE**

This document covers Phases 4–8, continuing directly from
`docs/milestone19_preimplementation_audit.md` (Phases 1–2, approved by the user before this work
began). Read that document first for the full audit findings (§1–§20) and the Phase 2 plan (§21)
this implementation executes.

---

## 17. Implementation Changes

Exactly the scope approved in the Phase 2 plan — nothing else. No schema change, no migration, no
existing service's behavior touched.

**New file**: `modules/predictions/application/training_preflight_service.py`
- `TrainingPreflightService` — a pure read-only service with one public method,
  `check(market_key, now) -> TrainingPreflightReport`. Mechanizes 12 named checks that map onto
  the master prompt's 16-item §15 checklist (module docstring documents the exact mapping,
  including the 3 items intentionally left as cited architectural invariants rather than
  re-derived, since they're per-observation properties, not properties of a bare `market_key` —
  see the docstring for the full rationale).
- Every check is either a plain read (`markets.get_by_key`, `mappings.list_by_market`,
  `feature_definitions.get`, `dataset_repo.list_by_market`) or a call to the already-read-only
  `DatasetBuilder.build()`. No `INSERT`/`UPDATE`/`DELETE` anywhere in the file.
- `PreflightCheck(name, passed, detail)` and `TrainingPreflightReport(market_key, ready, checks)`
  are plain frozen dataclasses; `ready = all(c.passed for c in checks)`.

**New file**: `scripts/run_training_preflight.py` — the read-only CLI entry point from the Phase 2
plan. Takes a `market_key` or `--all-trained-football`, prints each check's PASS/FAIL and detail,
never writes anything.

**Modified**: `apps/api/composition.py`
- Added import: `from modules.predictions.application.training_preflight_service import TrainingPreflightService`
- Added `build_training_preflight_service(session)`, wired exactly like the adjacent
  `build_dataset_builder`/`build_dataset_registry_service` factories — `SqlAlchemyMarketRepository`,
  `SqlAlchemyFeatureMarketMappingRepository`, `SqlAlchemyFeatureDefinitionRepository`,
  `build_dataset_builder(session)`, and the existing `get_dataset_repo()` singleton (still the
  same in-memory implementation — this milestone did not touch dataset persistence, per the
  Phase 2 plan's explicit exclusion).

**New file**: `tests/unit/modules/predictions/test_training_preflight_service.py` — 11 tests (§18).

No other file was modified. `git status` before/after this implementation shows only these 4
files as new/changed relative to the Phase 1/2 audit commit.

---

## 18. Tests

11 new tests in `test_training_preflight_service.py`, reusing existing in-memory fixture
infrastructure from `tests/unit/modules/predictions/conftest.py` (`market_repo`,
`feature_mapping_repo`, `feature_definition_repo`, `prediction_repo`, `prediction_outcome_repo`,
`dataset_repo` — no new fixtures needed):

1. `TestMarketNotFound::test_reports_single_blocking_check` — unknown market_key short-circuits
   to a single `market_exists=False` check.
2. `TestFullyReadyMarket::test_every_check_passes` — a market with a required + optional feature
   both present in every sample, real reference times, and a Dataset explicitly persisted into
   the (test) `dataset_repo` reports `ready=True` with zero failing checks — proves the service
   correctly reports READY once every real-world blocker is absent, not just BLOCKED-always.
3. `TestInsufficientObservations::test_blocks_readiness` — 5 samples (below `MIN_TRAINING_SAMPLES=30`).
4. `TestMissingTemporalReference::test_blocks_readiness` — `reference_time=None` fails both
   `temporal_reference_present` and `temporal_split_valid` (the latter via
   `MissingTemporalReferenceError`, exactly Milestone 18's fail-closed exception).
5. `TestTrainingInferenceFeatureParity::test_required_feature_never_present_in_training_data_blocks_readiness`
   — reproduces the exact M19 audit finding in miniature: a feature `is_required=True` for
   inference that has never appeared in a training sample.
6. `TestRequiredFeatureCoverage::test_low_coverage_blocks_readiness` — a required feature present
   in only 25% of samples (below the 50% missing-rate threshold).
7. `TestLeakageSafety::test_post_match_only_required_feature_blocks_readiness` — a required
   feature classified `POST_MATCH_ONLY`.
8. `TestFeatureVersionsKnown::test_unregistered_feature_definition_blocks_readiness` — a mapped
   feature key with no corresponding `FeatureDefinition`.
9. `TestFeatureManifestDeclared::test_no_mappings_blocks_readiness` — a market with zero
   `feature_market_mappings`.
10. `TestDatasetProvenancePersisted::test_reports_blocked_when_dataset_never_persisted` — confirms
    the honest "in-memory-only by design" detail message cites the audit.
11. `TestDatasetReproducibility::test_content_hash_stable_across_builds` — confirms two independent
    `DatasetBuilder.build()` calls against identical seed data produce an identical `content_hash`.

All 11 pass. No existing test was modified or weakened.

**Live verification against real `dev.db`** (read-only, via `scripts/run_training_preflight.py`):
ran the preflight gate against all 14 genuinely-trained football markets. Result: **0/14 READY**,
every one blocked on exactly `training_inference_feature_parity`,
`required_feature_coverage_acceptable`, and `dataset_provenance_persisted` — reproducing the
Phase 1 audit's findings verbatim, market for market, feature for feature (e.g.
`football.both_teams_to_score` failed on precisely `football.fixture.away_lineup_continuity`,
`away_transfer_activity`, `home_lineup_continuity`, `home_transfer_activity`,
`news.football.away_btts_impact`, `news.football.home_btts_impact` — the identical 6 features
the audit's §4/§6 identified for that market). This is strong independent confirmation that the
new service's logic is correct: it wasn't tuned to produce this answer, it derived it from live
data using the same primitives (`DatasetBuilder`, `feature_market_mappings`,
`dataset_repo.list_by_market`) the rest of the platform already uses.

---

## 19. Regression Results

**Full suite: 2222 passed, 58 skipped, 0 failed** (1320.45s / 22:00), against the Milestone 18
baseline of 2211 passed/58 skipped/0 failed — a net **+11**, exactly the 11 new tests added in
`test_training_preflight_service.py`, with zero pre-existing test broken, altered, or skipped
differently.

Targeted (`tests/unit/modules/predictions/test_training_preflight_service.py`): 11 passed, 0 failed.

---

## 20. Database Verification

Row counts, identical before implementation, after implementation, and after the full regression
suite (three independent checks, all read-only `sqlite3.connect("file:dev.db?mode=ro", uri=True)`
queries):

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

Every value is byte-identical to §17 of the Phase 1/2 audit. No migration was written. No
`Base.metadata.create_all` or Alembic command was run against `dev.db`.

---

## 21. External API Verification

No RSS, Gemini, or Community API call was made at any point in Phase 4–8.
`NEWS_SYNC_ENABLED`/`NEWS_BACKFILL_ENABLED` remain unset (default `false`), unchanged from the
Phase 1/2 audit. The new service and script never call `modules.intelligence` at all — they only
read `modules.predictions`/`modules.features` repositories.

---

## 22. Model/Training Verification

No `model.fit()` call was made. No `TrainingPipelineService.train()` invocation occurred. No
Challenger was created or registered. No Champion was promoted, retired, or modified. All 47
`models` rows are unchanged. The new `TrainingPreflightService` has no code path capable of
training or persisting a model — it has no dependency on `TrainingPipelineService`,
`ModelRegistryService`, or `AutomaticModelSelectionService` at all.

---

## 23. Remaining Blockers

Unchanged from the Phase 1/2 audit's §20 — this milestone built the *diagnostic instrument*, not
a fix for what it measures:

1. Zero `VERIFIED_PRE_MATCH` lineup/transfer/news observations exist in `dev.db`, for any fixture
   — confirmed still true, live, via `run_training_preflight.py`'s 0/14 result.
2. No durable Dataset/TrainingRun persistence (ADR-008 posture) — confirmed still true via the
   `dataset_provenance_persisted` check failing on all 14 markets.
3. Feature-version provenance is per-registration, not per-sample — unaffected by this milestone.

The training preflight gate does not and cannot fix any of these; it exists so a future Milestone
20 attempt has a single, mechanized, honest answer to "is this market ready?" instead of having to
re-derive the same 12-point analysis by hand each time.

---

## 24. M20 Recommendation

Unchanged: **NO MARKET IS READY FOR M20 TRAINING.** The training preflight gate built this
milestone now makes that determination mechanically and repeatably — any future readiness change
(e.g., once the `LIVE_SCHEDULED` sync has run long enough to accumulate real `VERIFIED_PRE_MATCH`
lineup/transfer observations) will be verifiable by re-running
`python scripts/run_training_preflight.py --all-trained-football` rather than re-auditing by hand.

---

## 25. STOP Declaration

MILESTONE 19 STATUS:
COMPLETE

TEMPORAL VALIDATION:
PASS

TRAINING/INFERENCE PARITY:
FAIL (all 14 genuinely-trained markets — reconfirmed live via the new preflight gate)

NEWS INTELLIGENCE:
PARTIALLY READY (architecture correct and intact; zero real observations yet)

STRUCTURED INTELLIGENCE:
PARTIALLY READY (single-calculator parity confirmed correct; zero real observations yet)

FEATURE VERSION PROVENANCE:
PARTIALLY READY (per-registration version recorded correctly; per-sample historical version not captured)

DATASET PROVENANCE:
BLOCKED (documented in-memory-only posture; zero durable rows)

TRAINING PREFLIGHT:
READY (the gate itself is now built, tested, and live-verified — it correctly reports BLOCKED for
every current market, which is the honest answer)

FIRST M20 CANDIDATE:
NONE — identical smallest blocker across all 14 markets

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
0

M19 VERIFICATION REPORT:
docs/milestone19_verification_report.md

STOPPING AFTER MILESTONE 19.
DO NOT BEGIN MILESTONE 20 WITHOUT EXPLICIT APPROVAL.
