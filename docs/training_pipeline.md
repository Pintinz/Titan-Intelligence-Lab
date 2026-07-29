# TitanIQ — Dataset & Training Platform

Status: **Milestone 9.1**. See [machine_learning.md](machine_learning.md) for the framework
adapters this platform trains, [decisions.md](decisions.md) ADR-052 for the Dataset Builder's
Feature-Store-only sourcing rule and classification-label convention.

## 1. Dataset Platform

### Building

`DatasetBuilder.build(market_id, now)` sources every `TrainingSample` from real Prediction
Pipeline output only — `Prediction.feature_snapshot` (Milestone 9's Feature-to-Market-Registry-
filtered Feature Store resolution) paired with its realized `PredictionOutcome`. There is no code
path here that reads a `FeatureValue` directly, so "no algorithm may bypass the Feature Store" is
enforced by construction, not convention. Classification labels follow ADR-052's convention
(`actual_value == "positive"/"negative"`); regression labels are `float(actual_value)` directly.

### Statistics, Quality Validation, Drift Detection

`Dataset.statistics` (`DatasetStatistics`): sample/feature count, positive rate (classification
only), per-feature missing rate/mean/std. `_detect_quality_issues()` flags `TOO_FEW_SAMPLES`
(< 30), `SEVERE_CLASS_IMBALANCE` (positive rate outside 10–90%), `HIGH_MISSING_RATE` (≥ 50% for
any feature), `ZERO_VARIANCE_FEATURE`. `DatasetRegistryService.detect_drift()` compares the
latest dataset's per-feature means against a baseline (the second-most-recent version, or an
explicit one) — relative shift ≥ 20% flags a feature as drifted.

### Versioning, Hashing, Reproducibility

Each build is content-hashed (`content_hash`, SHA-256 over the ordered feature matrix + labels) —
identical inputs always reproduce the identical hash. `DatasetLineage` records
`source_prediction_ids`/`feature_keys`/`built_at`.

### Approval Workflow

`DatasetRegistryService`: DRAFT → VALIDATED → APPROVED → ARCHIVED, mirroring `MarketDefinition`'s
lifecycle shape (Milestone 9) rather than inventing a new state machine. `validate()` refuses a
dataset flagged `TOO_FEW_SAMPLES`. Only an APPROVED dataset with no `TOO_FEW_SAMPLES` issue is
`is_usable_for_training()`.

### Split Strategies (6)

`dataset_splitter.split(samples, strategy, **kwargs)` — pure functions, no framework dependency:

| Strategy | Shape |
|---|---|
| `TRAIN_TEST` | Seeded shuffle, `test_ratio` |
| `TRAIN_VAL_TEST` | Seeded shuffle, `val_ratio` + `test_ratio` |
| `HOLDOUT` | Chronological, no shuffle |
| `ROLLING_WINDOW` | Fixed-size chronological train window + test window, sliding forward |
| `WALK_FORWARD` | Growing chronological train window + fixed test window |
| `TIME_SERIES_SPLIT` | `n_splits` chronologically-increasing folds |

`HOLDOUT`/`ROLLING_WINDOW`/`WALK_FORWARD`/`TIME_SERIES_SPLIT` deliberately never shuffle — they
exist specifically to respect chronological order; callers pass samples in ascending time order.

## 2. Training Platform

### Preprocessing (`preprocessing.py`)

Pure functions over `TrainingSample`s, independent of which algorithm trains on the result:

- `impute_missing(samples, feature_order, strategy)` — `"zero"` or `"mean"` fill.
- `detect_outliers(samples, feature_order, z_threshold)` — flags (does not remove) samples with
  any feature's z-score beyond the threshold.
- `select_features(samples, feature_order, top_k, method)` — `"variance"` (unsupervised) or
  `"correlation"` (supervised, ranks by \|Pearson correlation\| against the label).

Scaling/encoding are **not** here — they're inside `SklearnAdapter` itself (a `Pipeline` with a
`StandardScaler` first stage) because a fitted scaler must travel with the model to inference
time, not be a separate preprocessing artifact the serving path would need to re-apply correctly.

### Training Loop (`TrainingPipelineService.train()`)

Wires together, in order: dataset usability check → impute → outlier detection/removal →
optional feature selection → `dataset_splitter.split()` → `model.fit()` (with early stopping
wired through automatically when the split produced a validation set) → evaluation on the held-out
split (`accuracy`/`precision`/`recall`/`f1` for classification, `mae`/`rmse` for regression).
Returns a `TrainingRunResult` — the model, both metric sets, feature order, selected features,
samples used, outliers removed.

### GPU-Readiness

No separate "GPU code path" exists to fabricate. Every framework adapter's `params` dict passes
straight through to the underlying estimator constructor — `LGBMClassifier(device="gpu")`,
`XGBClassifier(tree_method="gpu_hist")`, `CatBoostClassifier(task_type="GPU")` all work today via
that passthrough. This is the honest, minimal-but-real form the requirement takes until a
dedicated GPU worker pool exists.

### Parallel Training

"Train N algorithms for a market concurrently" is `asyncio.gather` over multiple `train()` calls
at the call site (`AutomaticModelSelectionService`, [machine_learning.md](machine_learning.md)
§4) — `TrainingPipelineService` itself trains exactly one model per call, consistent with
`PredictionModelPort.fit()` being a per-model contract.

### Retraining Scheduler

`RetrainingScheduler.should_retrain(market_id, now)` — a market needs retraining if its dataset
has drifted (`DatasetRegistryService.detect_drift()`) or is older than `max_dataset_age` (default
7 days). Decision logic only; actually invoking retraining on a schedule is Celery periodic-task
wiring (reusing Milestone 5's scheduler infrastructure), added alongside the Retraining API.

## 3. Validation Strategies (9)

`validation_service.cross_validate(model_factory, samples, strategy, **kwargs)` — builds folds per
`ValidationStrategy`, fits/evaluates, returns per-fold + aggregate metrics
(`CrossValidationResult`).

| Strategy | Fold construction |
|---|---|
| `HOLDOUT` | Reuses `dataset_splitter`'s `HOLDOUT` split |
| `K_FOLD` | Seeded shuffle, `k` equal folds |
| `STRATIFIED_K_FOLD` | Per-label shuffle, `k` folds preserving label proportions |
| `TIME_SERIES_SPLIT` | Reuses `dataset_splitter`'s time-series folds |
| `ROLLING_WINDOW` | Reuses `dataset_splitter`'s rolling-window folds |
| `WALK_FORWARD` | Reuses `dataset_splitter`'s walk-forward folds |
| `LEAVE_ONE_OUT` | One fold per sample |
| `REPEATED_K_FOLD` | `K_FOLD` repeated `n_repeats` times with different seeds |
| `NESTED_CV` | Outer `K_FOLD`; `caller_fits_model=True` lets `model_factory` run its own inner search (e.g. HPO) against only that outer fold's training data |

Chronological strategies share fold-generation logic with `dataset_splitter` rather than
reimplementing the same windowing math twice.

## 4. Hyperparameter Optimization (5)

`hpo_service.optimize(param_space, objective, strategy, n_trials, seed, **kwargs)` — every
strategy drives an algorithm-agnostic `async def objective(params, budget_fraction) -> float`
callable; this module never imports `PredictionModelPort` or any framework adapter directly.

| Strategy | Shape |
|---|---|
| `GRID_SEARCH` | Exhaustive over discrete-list param spaces only |
| `RANDOM_SEARCH` | Seeded uniform/randint sampling, `n_trials` draws |
| `SUCCESSIVE_HALVING` | Starts `n_candidates` at `1/reduction_factor` budget, keeps the top fraction each rung, doubles budget, repeats to full budget |
| `BAYESIAN_OPTIMIZATION` | Optuna `TPESampler`, the fixed opinionated recipe |
| `OPTUNA` | Generic escape hatch — accepts any `optuna.samplers.BaseSampler` ("Optuna-ready": every other strategy is hand-rolled, this door is open to any Optuna sampler with no new code) |

Every run — every trial, every param set, the winner — is tracked via
[experiments.md](experiments.md)'s `ExperimentTrackingService.record_hpo()`.

## 5. Persistence

Migration `0023_ml_platform_schema` (`predictions` schema): `datasets` (Dataset Platform),
`training_runs` (one row per `TrainingPipelineService.train()` call), `retraining_jobs`. Currently
backed by `InMemoryDatasetRepository` (process-wide, ADR-008 mock-first posture) — a SQL-backed
`DatasetRepositoryPort` implementation is future work for when persistence-across-restarts has a
real production need, matching `PlattScalingCalibrator`'s same posture.

## 6. Testing & Coverage

`dataset_builder_service.py` 92%, `dataset_registry_service.py` 97%, `dataset_splitter.py` 95%,
`preprocessing.py` 95%, `training_pipeline_service.py` 94%, `validation_service.py` 97%,
`hpo_service.py` 93% — measured with `pytest-cov`
(`backend/tests/unit/modules/predictions/test_dataset_*.py`, `test_preprocessing.py`,
`test_training_pipeline_service.py`, `test_validation_service.py`, `test_hpo_service.py`).
