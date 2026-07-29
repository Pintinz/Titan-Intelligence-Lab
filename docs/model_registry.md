# TitanIQ — Extended Model Registry & Model Monitoring

Status: **Milestone 9.1**, extending Milestone 9's `ModelRegistryService`/`ModelDefinition`
additively (ADR-053) — every field below defaults to `None`/empty, so every existing `register()`
call site keeps working unchanged.

## 1. `ModelDefinition` fields

| Field (Milestone 9) | Field (Milestone 9.1, additive) |
|---|---|
| `id`, `market_id`, `model_key`, `version`, `algorithm`, `status` | `framework` — e.g. `"lightgbm"` |
| `training_dataset_ref`, `calibration_ref` | `dataset_version` — the `Dataset.version` trained against |
| `approved_by`, `approved_at`, `promoted_at`, `retired_at`, `created_at` | `feature_versions` — `{feature_key: FeatureDefinition.version}` at training time |
| | `training_run_ref` — pointer to the `TrainingRunResult`/experiment that produced this model |
| | `calibration_report_ref` — pointer to a persisted `CalibrationReport` |
| | `feature_importance_ref` — pointer to persisted SHAP/importance artifacts |
| | `artifact_ref` — `ModelArtifactStorePort` ref for the serialized `PredictionModelPort` payload |
| | `deployment_mode` — `"shadow"` \| `"canary"` \| `"live"` \| `None` |
| | `trained_at` — when `fit()` actually ran, distinct from `created_at` (registration time) |

"Rollback History" and "Audit History" (named in the Milestone 9.1 spec) are **not** new fields —
`PredictionAudit` (Milestone 9, keyed by `model_id`) already records every registry mutation
including rollbacks (`AuditAction.ROLLED_BACK`); duplicating that here would just create a second
source of truth for the same facts.

## 2. Champion/Challenger — unchanged lifecycle, new deployment tracking

`ModelStatus` (CANDIDATE → CHALLENGER → CHAMPION → RETIRED) and the single-champion-per-market
invariant are exactly as Milestone 9 left them. `set_deployment_mode(model_id, mode)` is new and
orthogonal: a CHALLENGER can be in shadow deployment or canary rollout — a *how it's being
exercised* question the lifecycle status doesn't answer. `InvalidDeploymentModeError` rejects
anything outside `{"shadow", "canary", "live", None}`.

## 3. Automatic Model Selection → Registry

`AutomaticModelSelectionService.select_and_register_challenger()`
([machine_learning.md](machine_learning.md) §4) registers the winning candidate with `framework`,
`algorithm`, `dataset_version`, and `trained_at` populated from the benchmark that just ran —
the only code path in this milestone that writes those fields for a real trained model.

## 4. Model Version Resolver

`ModelVersionResolver.resolve(market_id, model_key=None, pinned_version=None)` — the current
CHAMPION by default (same resolution `PredictionContextBuilder` performs at prediction time), or
a specific pinned version (requires `model_key`) for reproducibility/shadow-comparison/debugging.
`ModelVersionNotFoundError` covers both "no champion" and "pinned version doesn't exist."

## 5. Model Loader & Cache

`ModelLoaderService.load(model_id, framework, algorithm, target_type, artifact_ref)` reconstructs
a fitted `PredictionModelPort` from `ModelArtifactStorePort` bytes, dispatching to the right
adapter class via `MLFramework`/`MLAlgorithm`. Loaded instances are cached by `ModelId`;
`invalidate()` is called on rollback/re-promotion so a stale cached model never keeps serving
after its `ModelDefinition` changed.

## 6. Model Monitoring

`ModelMonitoringService` extends `PredictionAdminService` (Milestone 9) with the dimensions it
didn't cover — composing, not duplicating, where Milestone 9/9.1 already compute correctly:

| Dimension | Method | Composes |
|---|---|---|
| Latency | `record_latency()` / `latency_stats()` | New — `LatencySampleRepositoryPort` (in-memory default) |
| Volume | `volume(market_id, now, window_hours)` | New — counts `Prediction`s in a time window |
| Probability Drift | `probability_drift()` | Reuses `PredictionAdminService.prediction_drift()` verbatim |
| Concept Drift | `concept_drift()` | New — recent-window vs. prior-window `PredictionOutcome` accuracy; a drop means the feature→outcome relationship has shifted, distinct from probability drift (which only tracks the model's own output distribution) |
| Confidence Drift | `confidence_drift()` | New — same before/after shape, applied to `Prediction.confidence.composite` |
| Feature Drift | `feature_drift()` | Reuses `DatasetRegistryService.detect_drift()` verbatim |
| Calibration Drift | `calibration_drift()` | New — compares two `CalibrationReport.expected_calibration_error` values |
| Model Health | `model_health()` | Aggregates every dimension above + `PredictionAdminService.alerts()` into `"critical"`/`"degraded"`/`"healthy"` |

## 7. Persistence

Migration `0023_ml_platform_schema`: `calibration_reports`, `feature_importance_reports`,
`latency_samples`, `model_artifacts` (artifact *registry* metadata only — the serialized bytes
live wherever `ModelArtifactStorePort` put them, not in this row), plus the 9 additive `models`
columns. RLS (migration `0024`): all analyst+, matching `models`'/`experiments`' existing tier
(none of these are read directly by an app user).

## 8. Testing & Coverage

`model_registry_service.py` 99%, `model_version_resolver.py` 100%, `model_selection_service.py`
91%, `model_monitoring_service.py` 97%, `model_loader.py` 93% — measured with `pytest-cov`
(`test_model_registry_service.py`, `test_model_version_resolver.py`,
`test_model_selection_service.py`, `test_model_monitoring_service.py`,
`test_model_loader_service.py`).
