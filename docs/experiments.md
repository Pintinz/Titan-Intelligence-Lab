# TitanIQ — Experiment Tracking

Status: **Milestone 9.1**, extending Milestone 9's `Experiment` entity/`ExperimentRepositoryPort`
additively — no new entity, no schema change. `ExperimentTrackingService` is a new way of
*populating* `Experiment.config`/`Experiment.metrics`, reusing exactly the fields Milestone 9
already defined for `predictions.experiments`
([prediction_markets.md](prediction_markets.md) §5: "No market's production model changes
without one of these existing first").

## 1. What gets recorded

| Recorder | `config["kind"]` | Populates `metrics` with |
|---|---|---|
| `record_validation(market_id, CrossValidationResult, now)` | `"validation"` | `mean_metric`, `std_metric`, plus `strategy`/`fold_count` in `config` |
| `record_hpo(market_id, HPOResult, now)` | `"hpo"` | `best_metric_value`, `param.<name>` for every numeric best-param, plus `strategy`/`trial_count` in `config` |
| `record_model_selection(market_id, ModelSelectionResult, now)` | `"model_selection"` | `ranking.<metric_name>`, plus `candidates_considered`/`candidates_skipped`/`winning_algorithm`/`winning_framework` in `config` |

Every recorder sets `decision="pending"` — a human (or the Champion/Challenger promotion
workflow) calls `decide(experiment_id, decision)` to record `"promoted"`/`"rejected"`/`"pending"`,
raising `InvalidExperimentDecisionError` for anything else.

## 2. Model Comparison

`compare(market_id, limit=50)` returns every recorded experiment for a market — validation runs,
HPO runs, and model-selection benchmarks side by side, in whatever order
`ExperimentRepositoryPort.list_by_market` returns them. This is the "Model Comparison" surface
named in the Milestone 9.1 spec: nothing new to build, since `Experiment.metrics` already carries
everything needed to compare candidates once enough of them have been recorded.

## 3. Reproducibility

`Experiment.config` records the validation `strategy`/HPO `strategy`/model-selection candidate
roster that produced a given result — combined with `Dataset.content_hash`
([training_pipeline.md](training_pipeline.md) §1) and `ModelDefinition.dataset_version`
([model_registry.md](model_registry.md) §1), a recorded experiment is fully traceable back to the
exact data and configuration that produced it.

## 4. Why this is auditable, not just true at the moment it ran

Automatic Model Selection's own mandate — "never hardcode algorithm selection" (ADR-054) — is
only a real claim if it's checkable after the fact. `record_model_selection()` writes
`candidates_considered` (every algorithm in the roster), `candidates_skipped` (which ones
`InsufficientTrainingDataError`/`UnsupportedAlgorithmForTargetTypeError` ruled out, and why), and
`winning_algorithm`/`winning_framework` — so a reviewer can confirm the winner was actually
ranked against real alternatives, not asserted.

## 5. Persistence

No schema change — `predictions.experiments` (Milestone 9). `config`/`metrics` are JSON columns;
the shapes above are a convention `ExperimentTrackingService` establishes, not a stricter schema.

## 6. APIs

`GET /api/v1/admin/ml/experiments/{market_key}`, `POST /api/v1/admin/ml/experiments/{experiment_id}/decide`
(`apps.api.routers.ml_platform_router`, `Role.ADMINISTRATOR`-gated).

## 7. Testing & Coverage

`experiment_tracking_service.py` 100% — measured with `pytest-cov`
(`test_experiment_tracking_service.py`, plus the `record_model_selection`/`compare` paths
exercised in `test_model_selection_service.py`).
