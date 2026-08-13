# Milestone 18 Verification Report — Dataset Split-Direction & Validation Integrity

## 1. Executive Summary

The Milestone 17 split-direction defect is fixed. `TrainingSample` now carries an optional
`reference_time` field; `DatasetBuilder` populates it from `PredictionOutcome.evaluated_at` (the
real-world moment each sample's label became knowable — the authoritative timestamp already used,
incorrectly, for positional ordering before this milestone); and `dataset_splitter.split()` now
explicitly sorts every order-sensitive strategy (`HOLDOUT`/`ROLLING_WINDOW`/`WALK_FORWARD`/
`TIME_SERIES_SPLIT`) ascending by that field before slicing, **failing closed** (raising
`MissingTemporalReferenceError`) if any sample lacks it, rather than trusting caller-supplied
order. `TRAIN_TEST`/`TRAIN_VAL_TEST` (random, non-temporal) are unaffected. No model was trained,
no Champion was touched, no `dev.db` row changed, no external API was contacted.
`AutomaticModelSelectionService`'s production default (`TIME_SERIES_SPLIT`) was not changed — it
was already correct; only the sample ordering beneath it was wrong, and that is what this
milestone fixes.

## 2. M17 Finding Being Addressed

`docs/milestone17_training_data_readiness_audit.md` §5/§15/§18: "`TIME_SERIES_SPLIT`/
`WALK_FORWARD`/`ROLLING_WINDOW`/`HOLDOUT` all silently assume ascending-chronological sample
order, and the real order is descending" — a platform-wide `DatasetBuilder`/`dataset_splitter`
structural defect, not specific to any one market, blocking trustworthy validation for every
market that would ever train through the real production path.

## 3. Root Cause

Verified directly against current source (not assumed from the M17 report):

1. **Actual split direction, pre-fix:** whatever order `samples` arrived in. `dataset_splitter.py`'s
   own 4 order-sensitive functions built `train = samples[:k]`, `test = samples[k:k+step]` — a pure
   positional slice with zero verification of chronological order.
2. **Intended direction:** ascending — train on the past, evaluate on the future. Documented in the
   module's own pre-existing docstring ("callers are expected to pass samples in ascending
   chronological order") but never enforced.
3. **Real date ordering:** `SqlAlchemyPredictionOutcomeRepository.list_by_market`
   (`repositories.py:236`) — `.order_by(PredictionOutcomeModel.evaluated_at.desc())` — **descending**.
4. **Which observations became "training":** `DatasetBuilder.build()` iterates outcomes in that
   exact DESC order with no re-sort; `samples[0]` was always the newest-evaluated observation.
5. **Which became "validation/test":** the tail of the list — the oldest observations.
6. **Could future observations enter training?** Yes, structurally, every time — every train fold
   was drawn from the newest end of the list.
7. **Could earlier observations enter "future" validation?** Yes — every test fold was drawn from
   the oldest end, the reverse of a real deployment scenario.
8. **Strategies affected:** `TIME_SERIES_SPLIT`, `WALK_FORWARD`, `ROLLING_WINDOW`, `HOLDOUT` — all
   four order-sensitive strategies, confirmed by reading each of their pre-fix implementations.
   `TRAIN_TEST`/`TRAIN_VAL_TEST` are unaffected (already randomized, order-independent by design).
9. **Layer:** the defect was structural to the **contract between `DatasetBuilder` and
   `dataset_splitter`** — `DatasetBuilder` never claimed a chronological guarantee, and
   `dataset_splitter` never verified one; neither module alone was "buggy" in isolation, the gap
   was the unvalidated hand-off between them.
10. **Champion reliance:** confirmed (`docs/milestone17_training_data_readiness_audit.md` §14) —
    every one of the 14 genuinely-trained football Champions was bootstrap-promoted through
    `AutomaticModelSelectionService`'s default `TIME_SERIES_SPLIT` path, meaning every existing
    Champion's held-out metric was measured under the reversed-direction defect. This milestone
    does not retroactively invalidate or retrain them (out of scope, explicitly forbidden) — see
    §20 Remaining Blockers.

**One additional, second confirmed caller** found during implementation, not mentioned in the M17
report: `BacktestService.run()` (`backtest_service.py`) also calls `dataset_splitter.split(...,
SplitStrategy.WALK_FORWARD, ...)`. Unlike `DatasetBuilder`, `BacktestService` was **already
correct** — it takes an explicitly-named `samples_newest_first` parameter and reverses it
(`list(reversed(samples_newest_first))`) before splitting, matching the real DESC query order by a
disciplined, self-documenting convention. It required no logic change, only a test-data update (§14).

## 4. Existing Split Architecture

`dataset_splitter.split()` remains the single implementation for all 6 named strategies.
`validation_service.py`'s `ValidationStrategy.HOLDOUT`/`TIME_SERIES_SPLIT`/`ROLLING_WINDOW`/
`WALK_FORWARD` were confirmed to be thin wrappers delegating directly to `dataset_splitter.split()`
with the corresponding `SplitStrategy` — the fix propagates to `cross_validate()` automatically,
with zero source changes needed in `validation_service.py` itself.

## 5. Implemented Fix

**Files modified:**

- `modules/predictions/ports/ml_model.py` — `TrainingSample` gains `reference_time: datetime |
  None = None` (additive; every existing non-temporal call site is unaffected).
- `modules/predictions/application/dataset_builder_service.py` — `TrainingSample` construction now
  passes `reference_time=outcome.evaluated_at`; `_content_hash` now includes `reference_time` in
  its payload (two datasets with identical features/labels but different reference times can now
  split differently, so the hash must reflect that).
- `modules/predictions/application/preprocessing.py` — `impute_missing`'s `TrainingSample`
  reconstruction now threads `reference_time` through (previously silently dropped it).
- `modules/predictions/application/training_pipeline_service.py` — the feature-selection
  `TrainingSample` reconstruction now threads `reference_time` through (same silent-drop issue).
- `modules/predictions/application/dataset_splitter.py` — the core fix: a new `_chronological()`
  helper sorts ascending by `reference_time` and raises `MissingTemporalReferenceError` if any
  sample lacks one; called once, centrally, for all 4 order-sensitive strategies. A new
  `_assert_chronological()` helper adds the fail-closed invariant check
  (`train[-1].reference_time <= test[0].reference_time`) to every fold of every temporal strategy.

**No changes** to `AutomaticModelSelectionService`, `ScheduledRetrainingOrchestrator`,
`BacktestService`, or `validation_service.py` — the fix is fully centralized in
`dataset_splitter.py`, and every caller inherits correctness automatically because it already
receives `TrainingSample`s carrying a real `reference_time` (via `DatasetBuilder`, in real usage).

## 6. Temporal Invariants

The required invariant (`max(train.reference_time) <= min(validation/test.reference_time)`) is now
enforced two ways: (1) constructively — `_chronological()` sorts ascending, then every fold is a
contiguous slice, so the invariant holds by construction; (2) defensively —
`_assert_chronological()` asserts it explicitly on every fold produced, a fail-closed check that
is never weakened. Sort key: `TrainingSample.reference_time`, sourced exclusively from
`PredictionOutcome.evaluated_at` — never ingestion timestamp, database insertion timestamp,
current wall-clock time, or model-training timestamp, none of which this codebase's domain model
defines as the observation reference time.

## 7. `TIME_SERIES_SPLIT` Verification

Verified via `test_time_series_split_sorts_shuffled_input_chronologically` (shuffled 30-sample
input still produces 5 correctly-ordered expanding folds) and
`test_split_result_identical_across_many_random_shuffles` (8 independent shuffles of the same 12
chronological samples produce byte-identical fold output). `test_time_series_split_produces_expanding_folds`
(pre-existing, updated to supply `reference_time`) confirms fold count/non-empty behavior
unchanged.

## 8. `WALK_FORWARD` Verification

Verified via `test_walk_forward_sorts_shuffled_input_chronologically` (expanding-window sizes and
chronological fold boundaries hold under shuffled input) and the same 8-shuffle property test.
`test_walk_forward_expands_training_window_each_fold` (pre-existing, updated) confirms the
strictly-non-decreasing training-window-size property is unchanged.

## 9. `ROLLING_WINDOW` Verification

Verified via `test_rolling_window_sorts_shuffled_input_chronologically` and the property test.
`test_rolling_window_produces_sliding_folds`/`test_rolling_window_raises_when_not_enough_samples`
(pre-existing, updated) confirm fixed-window sliding behavior and the insufficient-samples error
path are unchanged.

## 10. `TRAIN_TEST` Compatibility

`test_train_test_split_is_reproducible_with_same_seed`,
`test_train_test_split_different_seeds_can_differ`, and the new
`test_train_test_does_not_require_reference_time` (samples with `reference_time=None` throughout)
confirm `TRAIN_TEST`/`TRAIN_VAL_TEST` behavior is byte-for-byte unchanged — not silently removed,
not weakened, exactly as required.

## 11. `DatasetBuilder` Verification

Real `DatasetBuilder` tests (`test_dataset_builder_service.py`, unmodified — every sample they
construct already carries a real `PredictionOutcome.evaluated_at=T0`) pass unchanged, including
`test_content_hash_is_reproducible_for_identical_data`, confirming the content-hash change did not
break reproducibility (two builds of the same underlying data still hash identically). Determinism:
`outcomes.list_by_market`'s query is deterministic given fixed DB state, so `DatasetBuilder`'s own
output order (still DESC, deliberately unchanged — see §13) and therefore its `content_hash` remain
reproducible run-to-run.

## 12. `AutomaticModelSelectionService` Verification

Traced again in this milestone (not merely re-cited from M16/M17): `select()`/
`select_and_register_challenger()` both default `split_strategy=SplitStrategy.TIME_SERIES_SPLIT`
and forward it unchanged to `TrainingPipelineService.train()`. **No production default was
changed** — it was already the correct choice; only the sample ordering it operated on was wrong,
and that is fixed centrally in `dataset_splitter.py`. All 26 tests in
`test_model_selection_service.py` pass with real `reference_time` values now supplied by its
dataset-builder helpers, confirming the real production selection path is temporally correct
end-to-end without any change to the service itself.

## 13. Backtest Compatibility

`BacktestService.run()` required no source change (§3, §5) — it was already correct. Its own
`samples_newest_first` → `list(reversed(...))` convention is untouched; only its test file's
hand-built samples needed a `reference_time` addition to satisfy the splitter's new requirement,
matching real production usage exactly (`ml_platform_router.run_backtest` passes `DatasetBuilder`'s
own `dataset.samples`, which — after this milestone — already carry real `reference_time`).
Backtest date windows, feature snapshots, market outcomes, and fixture ordering are all unchanged.

## 14. Training-Script Compatibility

`scripts/backfill_*_training_data.py` (all 4) were inspected: none imports or calls
`dataset_splitter`/`TrainingSample` directly — each constructs real `Prediction`/`PredictionOutcome`
rows and stops there; `DatasetBuilder`/the splitter run later, elsewhere, unmodified by these
scripts. **No changes were made to any backfill script.** Milestone 15's historical feature
reconstruction integration remains untouched and authoritative.

## 15. Test Coverage

New/updated tests, all read-only, synthetic data, no external APIs, no real model training:

- `tests/unit/modules/predictions/test_dataset_splitter.py` — rewritten: 4 pre-existing tests
  updated to supply `reference_time`; **10 new tests** covering: fail-closed behavior for all 4
  temporal strategies without `reference_time`; shuffled-input correctness for
  `HOLDOUT`/`ROLLING_WINDOW`/`WALK_FORWARD`/`TIME_SERIES_SPLIT`; an 8-shuffle property test proving
  split output depends only on `reference_time`, never input position; duplicate-timestamp
  determinism; `TRAIN_TEST`'s no-reference-time-required regression guard.
- `tests/unit/modules/predictions/test_model_selection_service.py` — `_classification_dataset`/
  `_multiclass_dataset` and 2 sample-reconstruction call sites updated to supply `reference_time`
  (no new tests — this file's job is `AutomaticModelSelectionService` behavior, already covered;
  the update proves the real production path now requires and correctly uses `reference_time`).
- `tests/unit/modules/predictions/test_validation_service.py` — `_classification_samples`/
  `_regression_samples` updated to supply `reference_time`.
- `tests/unit/modules/predictions/test_backtest_service.py` — `_drifting_samples` and one inline
  sample list updated to supply `reference_time`.

Targeted run (`tests/unit/modules/predictions/`): **683 passed, 0 failed.**

## 16. Database Safety

No migration created — no schema gap existed (`reference_time` lives on the in-memory
`TrainingSample` port object, never persisted to `dev.db`). No `dev.db` write occurred during
implementation or testing (all new/updated tests run against in-memory synthetic data or isolated
test DBs). Row counts, captured before and after implementation:

| Table | Before | After |
|---|---|---|
| `datasets` | 0 | 0 |
| `models` | 47 | 47 |
| `predictions` | 12,436 | 12,436 |
| `feature_values_offline` | 68,223 | 68,223 |
| `news_events` | 68 | 68 |

Unchanged, byte-for-byte.

## 17. External API Safety

Zero live calls. `NEWS_SYNC_ENABLED`/`NEWS_BACKFILL_ENABLED` remain `false`, untouched. No
scheduled news sync, news backfill, structured-intelligence sync, sports-provider sync, or
community ingestion was executed.

## 18. Champion Safety

No Champion was retrained, recalibrated, promoted, or had its metadata modified. No model artifact
was replaced. No `.fit()` call occurred outside the synthetic-data test suite (and even there, only
tiny in-memory test-double models, never a real framework adapter against real data). Production
prediction behavior is unchanged — `dataset_splitter.split()`'s signature and return shape
(`DatasetSplit`) are identical; only its *internal* ordering of an already order-sensitive
computation changed, and every real caller already supplies (or, via `DatasetBuilder`, now
supplies) the `reference_time` the new contract requires.

## 19. Regression Results

**Full suite: 2211 passed, 58 skipped, 0 failed** (914.00s), against the Milestone 17 baseline of
2197 passed/58 skipped/0 failed — a net +14, exactly the 14 new tests added to
`test_dataset_splitter.py` (§15), with zero pre-existing test broken or altered.

Targeted (`tests/unit/modules/predictions/`): 683 passed, 0 failed, 0 skipped.

## 20. Remaining Blockers

- **Existing Champions remain unverified against the corrected split direction.** This milestone
  fixes the mechanism going forward; it does not retroactively re-validate or retrain any of the
  14 existing football Champions (explicitly out of scope — no retraining occurred). Their
  `provenance_status='PROVENANCE_UNVERIFIED'` classification (Milestone 17 §14) is unchanged and
  remains accurate.
- **The other Milestone 17 findings are untouched**, per this milestone's explicit scope: 13 of 14
  real football markets still cannot serve a live prediction (Milestone 16/17 finding, unrelated to
  split direction); zero `feature_versions`/`Dataset` rows exist for any Champion; gated
  news/lineup/transfer features remain at 0% coverage; basketball/baseball/table tennis remain
  untrainable.
- **A genuine Challenger has never been trained against the corrected split.** This milestone
  proves the mechanism is now trustworthy; it deliberately does not exercise it against real data,
  per its own STOP condition.

## 21. M19 Readiness Assessment

**A. Is temporal validation now trustworthy?** YES — for the mechanism itself
(`dataset_splitter.split()`'s 4 temporal strategies), proven by construction, assertion, and a
property test across shuffled input. NOT YET demonstrated against any *existing* Champion's actual
training run, since none were retrained.

**B. Can TitanIQ construct a reproducible chronological training dataset?** YES —
`DatasetBuilder.build()` remains deterministic (§11), and every sample it produces now carries a
real `reference_time` that `dataset_splitter.split()` can correctly and reproducibly order.

**C. Can TitanIQ safely train a Challenger model?** Mechanically, the split-direction blocker
identified in Milestone 17 is removed. This is **not** interpreted as authorization to train — per
this milestone's own governing instruction, fixing the split defect is not automatic clearance;
the Milestone 17 findings in §20 above (live-serving breakage for 13/14 markets, zero feature
versioning, zero persisted datasets) remain open and unaddressed by this milestone.

---

**No `dev.db` row changed. No model was trained. No Champion was modified or promoted. No live
RSS/Gemini/provider call was made. `NEWS_SYNC_ENABLED`/`NEWS_BACKFILL_ENABLED` remain false.**

MILESTONE 18 COMPLETE — WAITING FOR APPROVAL
