# Phase 3 Master Command — Section 0 Read-Only Audit Report

**Scope:** the mandatory pre-implementation audit required by Section 0 of the "PROJECT TITANIQ — PHASE 3 MASTER IMPLEMENTATION COMMAND" (functional model competition, Poisson/Tweedie, calibration, SHAP attribution, Gemini explanations, live context sync). No code was modified to produce this report. Findings are verified against current source and the live `backend/dev.db` (not against prior docs, which are treated as unverified claims until re-checked here).

**DB snapshot at audit time:** fixtures=7829, teams=243, competitions=7, seasons=22, predictions=28,454, prediction_outcomes=28,401, models=178 (candidate=17, challenger=53, champion=40, retired=68), experiments=109, datasets=155, calibration_reports=108, prediction_football_explanations=4, prediction_context_reviews=9, sync_runs=2028, news_events=80, injuries=30, transfers=308, lineups=4, coaching_staff=5.

---

## 1. Training Pipeline & Model Candidates

| Component | Status | Evidence |
|---|---|---|
| AutomaticModelSelectionService | **FUNCTIONAL** | `model_selection_service.py:134-186` trains every candidate in the roster, no favorites hard-coded. Live DB: champions span 10 distinct algorithms (ridge, svm, gaussian_nb, mlp, catboost_gbm, logistic_regression, elastic_net, lightgbm_gbm, xgboost_gbm, random_forest). |
| TrainingPipelineService | **FUNCTIONAL** (one dead table) | `training_pipeline_service.py:132-223` — real impute→outlier-removal→feature-selection→chronological split→fit→held-out eval. `TrainingRunModel` table is defined (`persistence/models.py:257-274`) but **nothing ever writes to it** — dead table. |
| TrainingPreflightService | **FUNCTIONAL but NOT WIRED into any live path** | Checks are real (`training_preflight_service.py:93-243` — reproducibility, temporal-split validity, sample sufficiency). Composed only for `PredictiveSignalAuditService`, which itself has zero callers anywhere (no router, Celery task, or `ScheduledRetrainingOrchestrator` invokes it). `ScheduledRetrainingOrchestrator._check_and_retrain` trains directly, skipping preflight entirely. |
| DatasetBuilder / splitting | **FUNCTIONAL** | `dataset_splitter.py` enforces real chronological ordering (`_assert_chronological`, raises rather than trusts). Default split strategy is `TIME_SERIES_SPLIT`. Confirmed live: sample date ranges span real multi-month windows. |
| ModelRepository / Champion selection | **FUNCTIONAL** | `ModelRegistryService.promote_to_champion` only promotes from CHALLENGER, retires the prior champion. 40 live champions all have real persisted `artifact_ref` (verified `has_artifact=1`). |
| Poisson | **FUNCTIONAL** | `football_goals_poisson_adapter.py:95-118` — two real `sklearn.linear_model.PoissonRegressor()`, one per team side. Also generic `POISSON_GLM` for regression markets (`sklearn_adapter.py:91-92`). |
| Tweedie | **FUNCTIONAL — exists** | `sklearn_adapter.py:93-97`, real `TweedieRegressor(power=...)`, present in `DEFAULT_REGRESSION_CANDIDATES`. |
| Ridge | **FUNCTIONAL** | `sklearn_adapter.py:77-78`; live champion algorithm on 9 markets. |
| Logistic Regression | **FUNCTIONAL** | `sklearn_adapter.py:75-76`. |
| MLP | **FUNCTIONAL** | `sklearn_adapter.py:89-90`. |
| Candidate registry / target-type gating | **FUNCTIONAL** | `DEFAULT_CLASSIFICATION_CANDIDATES` vs `DEFAULT_REGRESSION_CANDIDATES`, selected by `target_type`; incompatible pairings raise `UnsupportedAlgorithmForTargetTypeError` rather than silently substituting. Poisson-goals candidate only injected for the 12 declared goals/score markets. One nuance: `FootballGoalsPoissonAdapter.fit()` ignores its own `target_type` param — always fits two Poisson regressions regardless — cosmetic field for that one adapter. |
| Market definitions / target types | **FUNCTIONAL** | Only two `TargetType` values exist (CLASSIFICATION, REGRESSION) — no dedicated COUNT type; count-shaped goals markets are declared CLASSIFICATION and served by the dedicated Poisson adapter instead. Confirmed both gates are exercised live (regression markets got regression-family champions). |
| Time-aware validation window persistence | **FUNCTIONAL but not first-class** | Every sample's `reference_time` is persisted inside `datasets.samples` JSON — reconstructable, but there's no dedicated `train_window_start`/`test_window_end` summary column on Dataset/Experiment. Answerable today only by scanning the JSON array. |
| Losing-candidate persistence | **PARTIAL** | Within-roster comparisons (Poisson vs MLP vs Ridge for the same run) ARE durably persisted — `Experiment.metrics` carries a `candidate.<algorithm>` score per candidate, SQL-backed, confirmed live with real differing log-loss values. **But** Challenger-vs-standing-Champion comparisons (`ChallengerEvaluation` — the object that carries `holdout_sample_count`, `decisive_metric`, `evaluated_at`) live only in `InMemoryModelComparisonRepository` — **wiped on every worker restart**. No SQL table backs it. |

---

## 2. Calibration & SHAP Attribution

**Two calibration services exist — only one is wired into production.**

| Component | Status | Evidence |
|---|---|---|
| `CalibrationFittingService` | **FUNCTIONAL, wired into production serving** | Fits `PlattScalingCalibrator` from real outcome history. Runs on Celery beat (`predictions.check_scheduled_calibration`, interval-based). **This is the one that actually changes what a real API call returns**: `PredictionEngine.generate()` line 146 calls `calibrator.calibrate(...)`, and the calibrated value — not raw `predict_proba` — becomes `Prediction.probability` (traced through `_shape_outcome`, lines 174/226-230). |
| `CalibrationValidationService` | **FUNCTIONAL but NOT WIRED into production** | Real sklearn `CalibratedClassifierCV(FrozenEstimator(...))` comparison (Platt vs isotonic vs none), produces the 108 `calibration_reports` rows. Only caller is a manual script (`scripts/phase3_champion_calibration_validation.py`) — zero Celery references. On a win it registers a **Challenger** (never auto-promotes), per its own composition docstring: "this service's decisions are durable model versions + DB rows, not per-process fitted parameters." Intentional design (never auto-promote), but means this session's more rigorous calibration work sits alongside, not inside, the actual serving path. |
| SHAP package/usage | **FUNCTIONAL** | `shap>=0.46` installed, confirmed importable (0.52.0 at audit time). `SHAPExplainerService` genuinely branches explainer type by model family (TreeExplainer for bare tree ensembles, KernelExplainer over real predict_proba for Pipeline-wrapped/GaussianNB) — not blindly one explainer for everything. Background sample pulled from real chronological training data, not synthetic. |
| ModelAttributionService/SHAP production wiring | **NOT WIRED into default path — opt-in only, by design** | `include_football_explanation` must be explicitly `true` on the request; base prediction generation never calls attribution. |
| Gemini narration-only contract | **FUNCTIONAL, schema-enforced** | `FootballExplanationSchema` (`extra="forbid"`) allows Gemini only free-text/rank fields (`verdict`, `key_reason_narration[{rank,analysis}]`, etc.) — zero numeric fields. All numeric attribution (`feature`, `contribution`, `direction`, `team`) is filled in from real computed values *before* Gemini is called; Gemini's response is matched back only by rank. |
| Persistence | **FUNCTIONAL** | `prediction_football_explanations` table, real ORM + repo (select-then-upsert), confirmed 4 live rows with real content (2 `shap`, 2 `heuristic_importance` for multiclass markets). |
| Code cleanliness | Minor | One unreachable duplicate `return` line in `SqlAlchemyFootballExplanationRepository.get_for_prediction` (copy-paste artifact, harmless). No TODO/FIXME/stub markers found anywhere in the calibration or attribution code paths. |

---

## 3. Gemini / Explanation Services / Prediction API

| Component | Status | Evidence |
|---|---|---|
| GeminiAdapter | **FUNCTIONAL** | Real `httpx.AsyncClient` POST to `generativelanguage.googleapis.com`, real encrypted-credential-store auth (not a hardcoded key), careful not to leak the key in error messages (key travels as URL query param). All 11 public methods route through one `_generate()` choke point. |
| Fallback/resolution | **FUNCTIONAL** | `MockGeminiAdapter` is a genuine deterministic implementation (not an empty stub). `TextIntelligenceRouter` picks the real adapter only if a usable credentialed provider exists, retries once on failure, then falls back to mock. |
| Multiple Gemini call sites | **FUNCTIONAL, no conflict** | `ExplainabilityEngine.explain()` runs on **every** prediction (always-on, populates `ai_explanation`). `FootballExplanationService`/`ContextualReasoningService` are opt-in only. Three distinct prompts serving three distinct product surfaces — not accidental duplication. |
| Inline blocking call | **Confirmed, not async-offloaded** | `PredictionEngine.generate()` line 164-166 does a plain blocking `await` on the always-on Gemini call before returning — worst case ~60s added latency (one retry × 30s timeout), mitigated only by mock fallback on failure, not by background execution. |
| `/api/v1/predictions/generate` end-to-end | **FUNCTIONAL** | Real Champion resolution via `models.get_champion(market.id)` (not arbitrary/stale). Feature-schema mismatch raises `MissingRequiredFeatureError` → HTTP 409 (never a silently-wrong prediction). Both opt-in flags (`include_football_explanation`, `include_contextual_review`) are independently wrapped in their own `try/except Exception`, and the base numeric prediction is already computed/committed before either runs — a Gemini failure in either cannot break the base response. |
| Frontend components | **FUNCTIONAL, one real gap** | All four files (`football-explanation-panel.tsx`, `contextual-review-panel.tsx`, `prediction-panel.tsx`, `generated-intelligence.tsx`) exist, are non-trivial, and are genuinely mounted from real routes. **Gap**: `match-detail-page.tsx` (the primary, non-admin-gated Match Intelligence page) never sends `include_contextual_review: true` and doesn't even import `ContextualReviewPanel` — that panel is only reachable via the admin-gated Prediction Laboratory route today. Not dead code, just effectively admin-only exposure. |
| Fabricated text | **NONE found** | Only hand-written narration strings exist inside the documented `MockGeminiAdapter` fallback, grounded in real supplied numbers — nothing else. |
| Null-prop safety | **SAFE** | Both explanation panels guard `if (!x) return null` before any property access. |

---

## 4. Live Context Sync & Provider Infrastructure

| Component | Status | Evidence |
|---|---|---|
| Provider abstraction / SportsProviderRouter | **FUNCTIONAL** | 5 real (non-mock) adapters, all genuine `httpx.AsyncClient` calls to real external APIs (API-Football ×3 sports, football-data.org, TheSportsDB). Real circuit breaker + quota engine + Redis-backed cache/lock. `table_tennis` has mock-only coverage — honestly so, not disguised. |
| SyncOrchestrator / SyncTrigger | **FUNCTIONAL** | Full enum: SCHEDULED, MANUAL, RETRY, LIVE, LIVE_SCHEDULED, ADMIN_MANUAL, BACKFILL, RECONCILIATION, SYSTEM. Only `LIVE_SCHEDULED` (fired by the one real Beat entry) can promote to `VERIFIED_PRE_MATCH` — enforced at a single provenance choke point, no over-privileged hardcoding found anywhere. |
| EntityReconciliationService | **FUNCTIONAL** | `reconcile_fixture`/`reconcile_lineup`/`reconcile_injury`/`reconcile_transfer`/`reconcile_coaching_staff` all real, all called from real Celery-reachable orchestrator methods — not test-only. |
| Injury / transfer | **FUNCTIONAL end-to-end** | Entity, model, migration, provider fetch, reconciliation, and public read API all present and connected. |
| Coaching staff / manager | **FUNCTIONAL but unscheduled** | Contrary to an earlier claim this session, a `coaching_staff` table **does exist** (5 real rows) with full entity/repo/provider/reconciliation/public-API wiring. Gap: `sync_coaching_staff` is not in the Celery Beat schedule — reachable only via admin-manual trigger or a one-off backfill script, so it never runs on its own. |
| Lineups | **PARTIAL — real write path, missing read path** | Entity/model/provider-fetch/reconciliation/admin-write-trigger all exist and are wired into the real Celery structured-intel task. **No public or admin GET endpoint for lineups exists anywhere.** Combined with the real, documented scoping (EPL-only, 90-minute pre-kickoff window), this fully explains the low `lineups=4` row count — a genuine timing/scope limitation, not fabricated data, plus a real missing-read-endpoint gap. |
| News infrastructure | **FUNCTIONAL, currently enabled** | `TITANIQ_NEWS_SYNC_ENABLED=true`. Real RSS 2.0/Atom parsing over real HTTP. The 80 live `news_events` trace to a documented one-off backfill script that ran real ingestion but used `MockGeminiAdapter` for extraction (catching up a backlog); going-forward live syncs use the real Gemini adapter when credentialed. |
| Historical context / point-in-time reconstruction | **PARTIAL** | `HistoricalEntityResolutionService` is genuinely live (wired into `NewsMarketImpactEngine`, used by real prediction code). `HistoricalFeatureReconstructionService`/`HistoricalNewsRelevanceEngine` are real, tested code but explicitly self-documented in `composition.py` as "not wired into any live endpoint or Celery task" — used only by a one-off training backfill script. A real, honestly-disclosed gap, not dead code. |
| Provenance system | **FUNCTIONAL, genuinely shared** | Single `classify_availability` choke point, confirmed reused (not duplicated) across injury/transfer/lineup/news reconciliation. No silent over-privileged trigger defaulting found anywhere. |
| Redis/cache | **fakeredis stand-in in dev, by design** | `.env` explicitly documents no real Redis exists on this machine; a documented `fakeredis` TCP stand-in script substitutes. Not a hidden gap — disclosed. |
| Circuit breaker | **FUNCTIONAL, real callers** | Exercised by `provider_router.py`, `feature_store_service.py`, `capability_resolver.py` — not just defined with nobody calling it. |
| Celery Beat schedule | **FUNCTIONAL** | 14 registered tasks. Only the news-sync task is env-gated (currently enabled). Not in Beat at all: `sync_coaching_staff`, and structured-intel/lineup sync for any sport beyond football/EPL (explicitly commented as a known scope limit in the beat schedule file itself). |

---

## Consolidated Gap List (real, verified, prioritized by how directly they touch the Phase 3 spec)

1. **`ChallengerEvaluation` (Challenger-vs-standing-Champion comparison) is in-memory only** — wiped on every restart. This directly blocks Section 10's requirement ("did Poisson beat MLP, by what metric, on what test period, with how many observations" for the *promotion* decision specifically, as opposed to within-roster candidate scoring which is already durable).
2. **`TrainingPreflightService` is fully built and correct but never called from any live path.** Real leakage/reproducibility/sufficiency checks exist and are simply orphaned.
3. **`CalibrationValidationService` (this session's sklearn-based Platt/isotonic comparison) never touches production inference** — only `CalibrationFittingService`'s simpler Platt-only calibrator does. The more rigorous calibration work and the live-serving calibration are two different code paths today.
4. **Lineups have a real write path but no read API** — data goes in, nothing reads it back out via any endpoint.
5. **`sync_coaching_staff` isn't scheduled** — real end-to-end feature, but only runs when manually triggered.
6. **`ContextualReviewPanel` is effectively admin-only** — the primary Match Intelligence page never requests contextual review, only the admin-gated Prediction Laboratory does.
7. **`HistoricalFeatureReconstructionService` is real but only reachable from a one-off training script**, not any live/scheduled path — an honestly-disclosed limitation already, not new information, but confirmed still true.
8. **Two dead artifacts**: `TrainingRunModel` table (nothing writes to it), and one unreachable duplicate `return` line in the football-explanation repository.
9. **`FootballGoalsPoissonAdapter.fit()` ignores its own `target_type` parameter** — cosmetic today (only ever called for goals-shaped markets), but worth knowing if it's ever reused elsewhere.

## What's already genuinely solid (no action needed)

Every declared candidate algorithm (Poisson, Tweedie, Ridge, Logistic Regression, MLP, plus the boosting/tree family) is real and empirically competes — confirmed by 10 different algorithms winning across different live markets, not one favorite. Chronological, leakage-safe dataset splitting is enforced at runtime, not just by convention. SHAP attribution uses family-appropriate explainers with real background samples. Gemini is schema-locked out of ever supplying a numeric attribution value. The production prediction path correctly isolates both opt-in Gemini calls so neither can break the base response. Provenance trigger-gating is centralized and consistently enforced everywhere it's used. No fabricated data, faked scores, or hard-coded confidence values were found anywhere in scope.
