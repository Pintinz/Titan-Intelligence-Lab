# TitanIQ — Enterprise Machine Learning Platform

Status: **Milestone 9.1**. Real, framework-native ML models now sit behind the exact same
`PredictorPort` the weighted predictors already implement (Milestone 9) — see
[prediction_engine.md](prediction_engine.md) §4 and [decisions.md](decisions.md) ADR-050/051 for
why the Prediction Engine pipeline itself never changed. This doc covers the ML-specific layer:
framework adapters, ensembles, and Automatic Model Selection. [training_pipeline.md](training_pipeline.md)
covers the Dataset/Training Platform that feeds them, [model_registry.md](model_registry.md) the
extended registry, [experiments.md](experiments.md) tracking, [calibration.md](calibration.md)
probability calibration.

## 1. `PredictionModelPort` — the framework-independence seam

A *lower*-level port than `PredictorPort` (ADR-051): it knows only feature vectors and a scalar
label, never `MarketKind` or mapping weights.

```python
class PredictionModelPort(Protocol):
    target_type: TargetType
    feature_order: list[str]
    async def fit(self, samples: list[TrainingSample], validation_samples=None) -> TrainingMetrics: ...
    def predict_one(self, features: dict[str, float]) -> ModelPrediction: ...
    def feature_importance(self) -> dict[str, float]: ...
    def is_fitted(self) -> bool: ...
    def underlying_estimator(self): ...   # raw fitted framework object, for SHAP
    def serialize(self) -> bytes: ...
    def deserialize(self, payload: bytes) -> None: ...
```

`fit()` raises `InsufficientTrainingDataError` below `MIN_TRAINING_SAMPLES` (30) — an honest
refusal, not a fabricated fit (ADR-044/052 posture). `validation_samples`, when supplied, enables
native early stopping on the three gradient-boosting adapters.

`TrainedModelPredictor` (`infrastructure/predictors/ml_predictor.py`) is the one `PredictorPort`
implementation that wraps a fitted `PredictionModelPort` — every other class in this document is
reached through it, never through `PredictorPort` directly.

## 2. Frameworks & Algorithms

| Family | Algorithm | Framework | Adapter |
|---|---|---|---|
| Gradient Boosting | LightGBM | `lightgbm` | `LightGBMAdapter` |
| Gradient Boosting | XGBoost | `xgboost` | `XGBoostAdapter` |
| Gradient Boosting | CatBoost | `catboost` | `CatBoostAdapter` |
| Tree Models | Random Forest, Extra Trees | scikit-learn | `SklearnAdapter` |
| Linear Models | Logistic Regression, Ridge, Elastic Net | scikit-learn | `SklearnAdapter` |
| Kernel | SVM | scikit-learn | `SklearnAdapter` |
| Probabilistic | Gaussian Naive Bayes | scikit-learn | `SklearnAdapter` |
| Neural | MLP | scikit-learn | `SklearnAdapter` |

`SklearnAdapter` is one parametrized class serving 8 algorithms (the same "handful of real
classes, not one per market" posture as the weighted predictors) — `algorithm: MLAlgorithm`
selects the concrete estimator via `_build_estimator()`. Scale-sensitive algorithms (Logistic
Regression, Ridge, Elastic Net, SVM, MLP) are wrapped in an `sklearn.pipeline.Pipeline` with a
`StandardScaler` first stage; tree ensembles and Gaussian NB skip scaling (invariant to it, or
would violate its own distributional assumptions respectively). `LOGISTIC_REGRESSION`/
`GAUSSIAN_NB` have no regression form — requesting one raises
`UnsupportedAlgorithmForTargetTypeError`, never a silent substitution.

Not every framework's estimator exposes classifier `predict_proba` the same way — `SklearnAdapter`
falls back to a sigmoid-squashed `decision_function` for RidgeClassifier/some SGDClassifier
losses, the same shape `WeightedLogisticPredictor` already uses.

Every adapter is framework-GPU-ready without a separate code path: `params` passes straight
through to the underlying constructor (`device="gpu"`, `tree_method="gpu_hist"`,
`task_type="GPU"` all work today) — see [training_pipeline.md](training_pipeline.md) §GPU.

## 3. Ensemble Learning

Every ensemble is itself a `PredictorPort` implementation combining other `PredictorPort` members
(ADR-055) — so members may mix trained models across frameworks with the weighted predictors,
uniformly, and an ensemble slots into `PredictorRegistry` exactly like any single predictor.

| Method | Class | Shape |
|---|---|---|
| Soft/Hard/Weighted Voting | `VotingEnsemblePredictor` | Combines member outputs directly, no fitting |
| Stacking / Blending | `StackedEnsemblePredictor` | A fitted meta-`PredictionModelPort` learns to combine member probabilities — inference-time identical; differ only in how the meta-model was fit (out-of-fold vs. holdout) |
| Dynamic | `DynamicEnsemblePredictor` | Dynamic Ensemble Selection — routes to whichever member currently has the best tracked reliability, rather than combining every member every time |

"Sport-specific"/"market-specific" ensembles aren't distinct classes — which members compose one,
and for which market, is decided by composition wiring (`PredictorRegistry.register_for_market`).

## 4. Automatic Model Selection

`AutomaticModelSelectionService` — "never hardcode algorithm selection" (ADR-054) means literally
that: `select()` trains every candidate in a configurable roster
(`DEFAULT_CLASSIFICATION_CANDIDATES`/`DEFAULT_REGRESSION_CANDIDATES`, 11/9 entries) via the
identical `TrainingPipelineService.train()` path, ranks by held-out `accuracy`/`mae`, and returns
the real winner — never a fixed favorite. `select_and_register_challenger()` registers the
winner as CANDIDATE, immediately promotes it to CHALLENGER (the benchmark just ran), and records
the full benchmark — every candidate considered, every one skipped and why — as an `Experiment`
via `ExperimentTrackingService.record_model_selection()`. Promotion to CHAMPION stays a separate,
human-gated call to `ModelRegistryService.promote_to_champion()`.

## 5. Probability Calibration

See [calibration.md](calibration.md) — Platt Scaling (Milestone 9), Isotonic Regression,
Temperature Scaling, reliability curves, `CalibrationReportBuilder`.

## 6. SHAP Explainability

`SHAPExplainerService` (`infrastructure/ml/shap_explainer_service.py`) computes real Shapley-value
attributions for a fitted `PredictionModelPort`, layered on top of (never replacing) the existing
`PredictorOutput.feature_contributions` approximation.

Explainer selection is duck-typed on the fitted estimator, never framework-isinstance-checked
(ADR-056): a bare tree ensemble (`hasattr(estimator, "feature_importances_")`, not wrapped in a
`Pipeline`) gets `shap.TreeExplainer` — fast, exact, supports interaction values. Everything else
(scale-sensitive sklearn algorithms wrapped in a `Pipeline`, plus bare GaussianNB) gets
`shap.KernelExplainer` over the estimator's own `predict_proba`/`predict` — model-agnostic, and
correctly handles the `Pipeline`'s internal scaling since it only ever calls it as a black box.

| Capability | Method | Notes |
|---|---|---|
| Local/Global Importance, SHAP Values, Base Value | `explain_instance()` | Returns a `ShapExplanation` |
| Interaction Values | `explain_instance()` | Tree models only (`shap.TreeExplainer.shap_interaction_values`) |
| Decision Paths | `ShapExplanation.decision_path` | Top-3 SHAP-ranked features as plain-language sentences — an honest reinterpretation for ensembles, where no single literal tree-traversal path exists (ADR-056) |
| Counterfactual Explanations | `counterfactual()` | A real, bounded greedy search — perturbs the top SHAP-ranked feature(s) toward the opposite end of the background data's observed range until the prediction flips, or the budget is exhausted (`found=False`, never fabricated) |
| Dependence Plots | `dependence_data()` | Varies one feature across its observed range, holding others fixed, recording (feature_value, shap_value) pairs |

`ExplainabilityEngine.explain_with_shap()` (Milestone 9.1) composes the existing `explain()`
unchanged and enriches the returned bundle's `shap_explanation` field only when both a
`shap_explainer` was configured and a fitted model is supplied — `model=None` (the weighted
predictors have no model to introspect) degrades cleanly to plain `explain()`.

## 7. Model Serving

`ModelLoaderService` reconstructs a fitted `PredictionModelPort` from a `ModelDefinition`'s
`framework`/`algorithm` + a `ModelArtifactStorePort` ref, caching loaded instances by `ModelId`
(`invalidate()` on rollback/re-promotion). `ModelVersionResolver` resolves a market's CHAMPION by
default, or a specific pinned version for reproducibility/shadow comparison.
`BatchPredictionService` fans out `PredictionCacheService.get_or_generate()` over many subjects
via `asyncio.gather`. `AsyncPredictionQueueService` is a Prediction Queue —
`enqueue()`/`process_next()`/`poll()` — deliberately holding no database session itself
(ADR-057): `process_next()` takes a freshly-built `PredictionCacheService` per call, so the
queue's own pending/results state outlives any single request while the session does not.
`ModelExportPort` (ONNX) is an interface-only seam, matching the spec's own "architecture"/
"future" framing for cross-runtime export and distributed serving (same posture as Milestone 7's
RAG-foundation retrieval port).

## 8. Model Monitoring

See [model_registry.md](model_registry.md) §Model Monitoring for `ModelMonitoringService`
(latency, volume, concept/confidence/probability/feature drift, model health).

## 9. APIs

`/api/v1/admin/ml/*` (`apps.api.routers.ml_platform_router`, `Role.ADMINISTRATOR`-gated):
training (dataset build/validate/approve, select-champion), experiments (list, decide), model
registry (list, deployment-mode), champion (resolve, promote), feature-importance, calibration
(reports), benchmark (single-candidate ranking), monitoring (health, latency), retraining
(check), evaluation (list). `prediction_admin_router.py` (Milestone 9) is untouched — every route
here is new.

## 10. Testing & Coverage

97% statement coverage across every module named above (framework adapters, ensembles, model
selection, SHAP, serving), measured with `pytest-cov`; 25 dedicated API-route tests in
`test_api_ml_platform.py`. See [training_pipeline.md](training_pipeline.md),
[model_registry.md](model_registry.md), [experiments.md](experiments.md), and
[calibration.md](calibration.md) for their own coverage figures.
