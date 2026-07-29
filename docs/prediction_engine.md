# TitanIQ — Prediction Engine

Status: **Enterprise Prediction Intelligence Platform, Milestone 9, extended by the Enterprise ML
Platform, Milestone 9.1** — the pipeline that turns engineered features into published,
calibrated, confidence-scored, explainable predictions across Football, Basketball, Baseball, and
Table Tennis. See [prediction_markets.md](prediction_markets.md) for the Market Registry/
Feature-to-Market mapping data model, [feature_catalog.md](feature_catalog.md) for how features
reach the Feature Store this engine reads from, [machine_learning.md](machine_learning.md) for the
real LightGBM/XGBoost/CatBoost/scikit-learn predictors and Automatic Model Selection that now sit
behind `PredictorPort` alongside the weighted fallback, and [decisions.md](decisions.md) ADR-043
through ADR-057 for this platform's key scope calls. **Milestone 9.1's own mandate — "Prediction
Engine interfaces must NEVER change. Only the predictor implementations may change." — is why every
section below still describes the exact same pipeline; only §4's predictor roster and §10's Model
Registry gained content.**

## 1. Purpose

The Prediction Engine is the single place a probability is computed from engineered features —
never from an LLM (`docs/titaniq.md`: "Predictions must never originate from an LLM"). It is
provider-, model-, framework-, database-, and cloud-independent: every dependency reaches
Postgres/Redis/Gemini/knowledge-graph data only through a port, never directly.

## 2. Pipeline

```
Provider Data -> Validation -> Knowledge Graph -> Feature Store -> Feature Selection
    -> Market Selection -> Market Feature Retrieval -> Prediction Model
    -> Probability Calibration -> Confidence Engine -> Explainability Engine -> Prediction API
```

| Stage | Component | Module |
|---|---|---|
| Feature Store / Selection, Market Selection, Market Feature Retrieval | `PredictionContextBuilder` | `modules.predictions.application.prediction_context_builder` |
| Prediction Model | `PredictorRegistry` + `WeightedLogisticPredictor` / `WeightedLinearPredictor` | `modules.predictions.application.predictor_registry`, `modules.predictions.infrastructure.predictors.weighted_scoring` |
| Probability Calibration | `PlattScalingCalibrator` (`CalibratorPort`) | `modules.predictions.infrastructure.calibration.platt_scaling_calibrator` |
| Confidence Engine | `ConfidenceEngine` | `modules.predictions.application.confidence_engine` |
| Explainability Engine | `ExplainabilityEngine` | `modules.predictions.application.explainability_engine` |
| Orchestration | `PredictionEngine.generate()` | `modules.predictions.application.prediction_engine` |
| Cache / Versioning / Audit | `PredictionCacheService` | `modules.predictions.application.prediction_cache_service` |

`PredictionEngine.generate()` is pure with respect to persistence — it returns a `Prediction`
domain object and never writes anywhere. `PredictionCacheService` is the thin wrapper that
caches (reuses a still-fresh prediction within `cache_ttl_seconds`), versions (supersedes the
prior PUBLISHED prediction for the same subject+market), gates publication on the market's own
`confidence_threshold` (ADR-047), and records a `PredictionAudit` row for every generation,
approval, or rejection.

## 3. Market Registry & Feature-to-Market Mapping

Markets are data, not code — see [prediction_markets.md](prediction_markets.md) §1-2 for the
full `MarketDefinition`/`FeatureMarketMapping` model, the `MarketKind` taxonomy (ADR-043), and
the lifecycle (`MarketRegistryService`: Draft → Review → Approved → **Production** → Deprecated →
Archived → Removed). Only a PRODUCTION market can generate predictions; promotion to PRODUCTION
is refused if the market has zero required features mapped
(`MarketNotReadyForProductionError`).

`FeatureMarketMappingService.resolve_feature_snapshot()` is the single enforcement point for
"no prediction model may consume features outside its registered Feature-to-Market mapping" — it
filters the entity's available feature values down to exactly what the market declares, raising
`MissingRequiredFeatureError` if a required feature is absent.

## 4. Prediction Model — the two generic predictors

`PredictorPort` implementations are written against a `MarketKind`, not a named market (ADR-043).
Two real, deterministic, honestly-scoped-as-v1 classes (ADR-044) serve every market this
milestone registers across all four sports:

- **`WeightedLogisticPredictor`** — classification-shaped kinds (`BINARY`, `SEGMENT_WINNER`).
  `raw_score` is the weighted sum of the resolved feature snapshot; `probability` is its sigmoid
  transform; `value` is the generic two-sided label `"positive"`/`"negative"` (mapping onto a
  market's real outcome labels, e.g. `"home_win"`, is the per-sport market registration's job).
- **`WeightedLinearPredictor`** — regression/threshold-shaped kinds (`SPREAD`, `TOTAL`,
  `TEAM_TOTAL`, `PLAYER_PROP`, `RACE_TO`, `CORRECT_SCORE`). `raw_score` IS the continuous
  predicted value; `probability` assumes the market's own feature engineering has already
  centered inputs around its line/threshold.

Every `PredictorOutput.feature_contributions` entry is signed and directly summable to
`raw_score` — the Explainability Engine ranks these into top-positive/top-negative features and
per-feature importance without re-deriving anything.

`PredictorRegistry` maps `MarketKind → PredictorPort`; composition wiring
(`apps.api.composition.get_predictor_registry`) registers both predictors against every kind
they support, once per process.

**Milestone 9.1**: `PredictorRegistry` additionally resolves by market key
(`register_for_market`/`get(market_kind, market_key)`, ADR-050) — a market whose champion is a
real trained model (LightGBM/XGBoost/CatBoost/scikit-learn, or an ensemble of them) is served via
`TrainedModelPredictor` wrapping that model, registered for its own `market_key`; every market
without one falls back to the weighted predictors above, unchanged. See
[machine_learning.md](machine_learning.md) for the full framework/ensemble/Automatic-Model-Selection
picture — none of it changes `PredictorPort`, `PredictionEngine`, or this pipeline's stage order.

## 5. Probability Calibration

`PlattScalingCalibrator` (`CalibratorPort`) fits a 2-parameter logistic regression —
`calibrated = sigmoid(A * logit(raw) + B)` — per model, from that model's own
`PredictionOutcome` history, via pure-Python batch gradient descent (no ML framework
dependency). Before `fit()` has ever run for a model, `calibrate()` is the identity mapping
(`A=1, B=0`) — an honestly-scoped default, not a faked result. **Milestone 9.1** adds two more
`CalibratorPort` implementations — `IsotonicRegressionCalibrator` (non-parametric, sklearn-backed)
and `TemperatureScalingCalibrator` (single-parameter, pure-Python) — plus `CalibrationReportBuilder`
for reliability curves/Expected Calibration Error/Brier score. See [calibration.md](calibration.md).

## 6. Confidence Engine

`ConfidenceBreakdown` is a fixed 9-factor dataclass with a `composite` property (the plain mean).
`ConfidenceEngine.compute()` does the real aggregation for three per-feature factors
(`feature_quality`, `feature_freshness` — averaged across the resolved snapshot;
`data_completeness` — the presence ratio) and clamps six pass-through factors gathered by
`PredictionEngine` from real signals it composes rather than re-implements:

| Factor | Source |
|---|---|
| `historical_accuracy` | Mean `1 - error` across the market's recent `PredictionOutcome` rows |
| `knowledge_graph_completeness` | Retrieved knowledge-graph fact count vs. an expected-fact baseline (`IntelligenceRetrievalService`) |
| `news_reliability` / `community_reliability` | Mean `IntelligenceRetrievalDocument.confidence` per modality |
| `model_reliability` | The champion model's latest `ModelEvaluation.metrics["reliability"]` |
| `prediction_stability` | `1 - 2·stddev` of the subject+market's most recent published probabilities |

"No data yet" defaults are deliberately asymmetric by what kind of unknown each factor
represents — see [decisions.md](decisions.md) ADR-045.

## 7. Explainability Engine

`ExplainabilityEngine.explain()` composes rather than reimplements:

- **Top Positive/Negative Features, Feature Importance** — ranking `PredictorOutput.feature_contributions`
  (this engine's own real work).
- **Knowledge Graph Evidence, News Contribution, Community Contribution** — one call to
  Milestone 8's `IntelligenceRetrievalService.retrieve_all()` (itself composing Milestone 7's
  Knowledge Graph retrieval), split by `IntelligenceRetrievalDocument.modality`.
- **AI Explanation** — Gemini's `TextIntelligenceProviderPort.explain()`, given the already-ranked
  feature importances as context. The LLM narrates; it never decides the ranking or the
  probability (constitution: "Predictions must never originate from an LLM").

**Milestone 9.1**: `ExplainabilityEngine.explain_with_shap()` composes the same `explain()` above
and additionally enriches the returned `ExplanationBundle.shap_explanation` with real Shapley
values (`SHAPExplainerService`) when the predictor behind a prediction is a fitted ML model — see
[machine_learning.md](machine_learning.md) §SHAP Explainability. `explain()` itself, and every
existing caller of it, is unchanged.

## 8. Windowed & Single-Record Feature Engineering

Two distinct mechanisms feed the Feature Store this engine reads from:

- **Single-record** (`modules.ingestion.infrastructure.feature_calculators`, via Milestone 5's
  `FeaturePipeline`) — features computable from one `clean_record` dict with no repository
  lookup: `ImpliedProbabilityCalculator`, `OddsOverroundCalculator`, `HoursUntilKickoffCalculator`,
  `AttendanceRatioCalculator`.
- **Windowed** (`modules.predictions.application.windowed_feature_engineering_service`) —
  features needing a rolling window of past matches, computed directly against
  `TeamStatisticsRepositoryPort.list_recent_by_team()` and written straight to the Feature Store
  (the same direct-compute-then-write shape Milestone 8's `FeatureStoreEnrichmentService`
  established). `RollingTeamStatAverageCalculator` is one generic engine parametrized by
  `stat_key`, reading each sport's own declared `TeamStatistics` schema field rather than an
  invented universal scoring field (ADR-046): football's `shots_on_target`, basketball's
  `points`, baseball's `runs`, table tennis's `points_won`.

## 9. Per-Sport Market Seeding

`modules.predictions.{football,basketball,baseball,table_tennis}.market_seeding` each register a
representative (not literally exhaustive) set of markets covering every `MarketKind` relevant to
that sport, promoted through the full lifecycle to PRODUCTION, each backed by real registered
features (ADR-048):

| Sport | Markets seeded | `MarketKind`s covered |
|---|---|---|
| Football | Both Teams To Score, Total Goals O/U, Home Team Total Goals, Correct Score, First Half Winner | BINARY, TOTAL, TEAM_TOTAL, CORRECT_SCORE, SEGMENT_WINNER |
| Basketball | Moneyline, Point Spread, Game Total Points, Team Total Points, First Half Winner, Race To 20, Player Points Prop | BINARY, SPREAD, TOTAL, TEAM_TOTAL, SEGMENT_WINNER, RACE_TO, PLAYER_PROP |
| Baseball | Moneyline, Run Line, Total Runs, Team Total Runs, First Five Innings Winner, Pitcher Strikeouts Prop | BINARY, SPREAD, TOTAL, TEAM_TOTAL, SEGMENT_WINNER, PLAYER_PROP |
| Table Tennis | Match Winner, Match Handicap, Total Points, Correct Score, Race To 11, Set Winner | BINARY, SPREAD, TOTAL, CORRECT_SCORE, RACE_TO, SEGMENT_WINNER |

## 10. Model Registry — Champion/Challenger

`ModelRegistryService` enforces the Champion/Challenger lifecycle
(`ModelStatus`: CANDIDATE → CHALLENGER → CHAMPION → RETIRED) and the single-champion-per-market
invariant — promoting a new CHAMPION automatically retires the previous one. `rollback()` retires
the current champion and reinstates the most-recently-retired model, the Admin Action a
regression in a newly-promoted model triggers.

**Milestone 9.1** extends `ModelDefinition` additively (ADR-053) with `framework`,
`dataset_version`, `feature_versions`, `training_run_ref`, `calibration_report_ref`,
`feature_importance_ref`, `artifact_ref`, `deployment_mode`, `trained_at` — every existing
`register()` call keeps working unchanged. `set_deployment_mode()` tracks shadow/canary/live
independently of the CANDIDATE/CHALLENGER/CHAMPION/RETIRED lifecycle. See
[model_registry.md](model_registry.md) for the full picture, and
[machine_learning.md](machine_learning.md) for Automatic Model Selection, the service that now
populates these fields when it registers a challenger.

## 11. APIs

See [api_specification.md](api_specification.md) §Prediction Intelligence Platform for the full
route list: `/api/v1/predictions` (resource + confidence/explanation/history/monitoring/statistics/
comparison), `/api/v1/markets` (registry + feature-to-market mapping), `/api/v1/admin/predictions`
(operator dashboards + Recompute/Rollback Admin Actions), and `/api/v1/admin/ml` (Milestone 9.1 —
training/experiment/registry/champion/calibration/benchmark/monitoring/retraining/evaluation,
§Enterprise ML Platform API).

## 12. Persistence

Schema `predictions` (migration `0018_prediction_intelligence_platform_schema`):
`prediction_markets`, `feature_market_mappings`, `models`, `predictions`, `prediction_outcomes`,
`model_evaluations`, `experiments`, `prediction_audits`. `predictions.confidence`/`explanation`/
`feature_snapshot` are JSON columns — the full `ConfidenceBreakdown`/`ExplanationBundle` round-
trips through them losslessly (`modules.predictions.infrastructure.persistence.mappers`).
Realtime is enabled on `predictions`, `prediction_markets`, and `prediction_audits`
(migration `0019_prediction_realtime_publication`) for Live Predictions/Confidence Changes/
Market Updates/Prediction Status, plus `features.feature_values_offline` for Feature Updates — a gap
left open since Milestone 6's realtime spec first named it, closed here.

**Milestone 9.1** (migration `0023_ml_platform_schema`) adds `datasets`, `training_runs`,
`calibration_reports`, `feature_importance_reports`, `latency_samples`, `retraining_jobs`,
`model_artifacts`, plus the 9 additive columns on `models` above; RLS for all 7 new tables
(analyst+, matching the existing Model Registry tier) lands in migration `0024_ml_platform_rls`.

## 13. Testing & Coverage

98% statement coverage across `modules.predictions` (domain/application/infrastructure) plus
`modules.ingestion.infrastructure.feature_calculators`, measured with `pytest-cov`; every
application service, all four sport market seeders, every SQLAlchemy repository, and every API
route's success/404/409/422 paths have dedicated tests (`backend/tests/unit/modules/predictions/`,
`backend/tests/unit/apps/test_api_predictions.py`, `test_api_markets.py`,
`test_api_prediction_analytics.py`, `test_api_prediction_admin.py`).

**Milestone 9.1** adds 97% statement coverage across every new ML module (framework adapters,
ensembles, Dataset/Training Platform, validation/HPO, calibration, SHAP, monitoring, serving) —
1300+ total unit tests pass across the whole backend suite (`test_api_ml_platform.py` covers the
new `/api/v1/admin/ml` routes).
