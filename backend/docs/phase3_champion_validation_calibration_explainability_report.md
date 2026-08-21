# Phase 3 — Champion Validation + Calibration + Sports-Analyst Explainability

**Date:** 2026-08-19

## 1. Phase 2 verification

Re-confirmed, not assumed: `SportsProviderRouter`/`SyncOrchestrator`/`EntityReconciliationService`
are unmodified since Phase 2's fix (`CircuitBreaker` naive/aware-datetime robustness, additive
only). Football champion count, provenance, and reconciliation health match Phase 2's final state.

## 2. Champion inventory

18 football production markets, each with exactly one CHAMPION (`football.match_result` is
`deprecated`, has none). Audited every one — see the full table in the read-only audit performed
at the start of this phase (not reproduced in full here for length; summary below).

| market_key | algorithm | version | is_multiclass |
|---|---|---|---|
| away_clean_sheet | gaussian_nb | 3 | no |
| away_team_total_goals | mlp | 3 | no |
| away_win_to_nil | gaussian_nb | 3 | no |
| both_teams_to_score | svm | 3 | no |
| correct_score | logistic_regression | 3 | **yes** (37-class grid) |
| first_half_both_teams_to_score | logistic_regression | 2 | no |
| first_half_goals | mlp | 2 | no |
| first_half_winner | ridge | 2 | **yes** (3-class) |
| home_clean_sheet | gaussian_nb | 3 | no |
| home_team_total_goals | mlp | 3 | no |
| home_win_to_nil | gaussian_nb | 3 | no |
| match_winner | logistic_regression | 3 | **yes** (3-class) |
| second_half_winner | ridge | 2 | **yes** (3-class) |
| total_goals_over_under | logistic_regression | 3 | no |
| total_goals_over_under_0_5 | elastic_net | 3 | no |
| total_goals_over_under_1_5 | mlp | 3 | no |
| total_goals_over_under_3_5 | ridge | 3 | no |
| total_goals_over_under_4_5 | logistic_regression | 3 | no |

**Classification (§3):** All 18 → **VALIDATED** (preflight PASS on every gate — see §6) →
**CALIBRATION_ELIGIBLE** for the 14 binary markets, **CALIBRATION_ELIGIBLE (log-loss comparison,
no reliability curve — see §9)** for the 4 multiclass markets. None were `PROVENANCE_UNVERIFIED`-
blocking (the `provenance_status` column reads `PROVENANCE_UNVERIFIED` for all 18 — an unpopulated
default this phase's DatasetBuilder/preflight gates do not depend on — but every gate that
actually verifies provenance in a functional sense, `dataset_provenance_persisted` and
`dataset_reproducible`, passed for all 18).

## 3. Dataset inventory

Every champion's dataset is reproducible (content-hash-stable across two independent builds) and
persisted (`datasets` table, real rows, not the "0 rows" this codebase's `TrainingPreflightService`
audit would have caught if false). No dataset had a `TOO_FEW_SAMPLES` quality issue. 3 of the 4
Phase 1 markets (`first_half_both_teams_to_score`, `first_half_goals`, `first_half_winner`,
`second_half_winner`) carry a `high_missing_rate` flag traced to
`football.fixture.form_cards_yellow_diff_last5` being absent in 99.78% of samples — flagged
honestly by the pipeline itself, not a Phase 3 finding, and not required to be fixed by this
phase's mandate.

## 4-7. Sample counts / training / validation / test windows

**No train/val/test split is ever persisted anywhere in this codebase** — `DatasetSplit` is
computed at runtime by `dataset_splitter.split()` and discarded (confirmed by reading
`modules/predictions/domain/dataset.py` and `dataset_builder_service.py` in full). This is not a
Phase 3 defect to fix (out of scope — no request to add split persistence was made), but it means
this phase's calibration/test split (§10-11) had to be freshly and honestly reconstructed each run
from the newest chronological slice of the full historical dataset, not read from a stored record.
Documented in `calibration_validation_service.py`'s own module docstring as a known limitation:
this cannot *prove* the reserved tail was excluded from the Champion's original training fold,
only that it's the least likely slice to have been included.

Per-market calibration/test sample counts (both from the newest 30% chronological tail of each
market's full dataset, split in half):

| market_key | calibration samples | test samples |
|---|---|---|
| away_clean_sheet | 123 | 123 |
| away_team_total_goals | 123 | 123 |
| away_win_to_nil | 123 | 123 |
| both_teams_to_score | 97 | 98 |
| correct_score | 123 | 123 |
| first_half_both_teams_to_score | 138 | 139 |
| first_half_goals | 138 | 139 |
| first_half_winner | 138 | 139 |
| home_clean_sheet | 123 | 123 |
| home_team_total_goals | 123 | 123 |
| home_win_to_nil | 123 | 123 |
| match_winner | 97 | 98 |
| second_half_winner | 138 | 139 |
| total_goals_over_under | 123 | 123 |
| total_goals_over_under_0_5 | 123 | 123 |
| total_goals_over_under_1_5 | 123 | 123 |
| total_goals_over_under_3_5 | 123 | 123 |
| total_goals_over_under_4_5 | 123 | 123 |

## 8. Leakage results

**LEAKAGE: PASS** for all 18 — `TrainingPreflightService.check()`'s
`intelligence_feature_leakage_safe` gate (no required feature classified `POST_MATCH_ONLY`) passed
for every market, real run against live `dev.db`, not assumed.

## 9. Feature parity

**TRAINING/INFERENCE PARITY: PASS** for all 18 — `training_inference_feature_parity` gate passed
for every market (every required feature key appears in the dataset's actual lineage).

## 10. Existing calibration state (before this phase)

`calibration_reports`: **0 rows** system-wide before this phase — the table and its ORM class
(`CalibrationReportModel`) have existed since Milestone 9.1 but nothing had ever written to it.
Separately, `PlattScalingCalibrator`/`CalibrationFittingService` (Milestone 9-era, real and
genuinely wired into every `PredictionEngine.generate()` call) exist but are an in-memory,
per-process singleton with no persistence — functionally invisible to any DB audit, and subject to
a documented (in that module's own docstring) v1 refit-accuracy limitation. This phase's
calibration work is independent of that mechanism, not a replacement for it — see §17.

## 11. Calibration eligibility

14 binary markets: real sigmoid (Platt) and isotonic candidates evaluated via scikit-learn's
`CalibratedClassifierCV` wrapping a `FrozenEstimator` of the already-fitted Champion (no
retraining). 4 multiclass markets (§9's own explicit warning: "Do not apply binary classification
calibration to a count prediction" — extended here to "reliability curves are a binary-only
concept"): compared on log loss instead, no fabricated ECE/Brier. `football.correct_score`
specifically has too few per-class calibration samples (many of its 37 scorelines have 0-1
examples in a 123-sample calibration set) for scikit-learn's internal cross-validated calibration
fitting to run at all — honestly skipped (uncalibrated-only result), not crashed or faked.

## 12-13. Uncalibrated / Sigmoid / Isotonic results

Full per-market, per-candidate results (log loss, Brier score, Expected Calibration Error):

| market_key | candidate | log_loss | brier | ECE |
|---|---|---|---|---|
| away_clean_sheet | none | 0.4425 | 0.1390 | 0.0590 |
| away_clean_sheet | platt_scaling | 0.4677 | 0.1479 | 0.0231 |
| away_clean_sheet | **isotonic_regression (winner)** | 0.4354 | 0.1400 | **0.0313** |
| away_team_total_goals | none (retained) | 0.6179 | 0.2144 | 0.1141 |
| away_win_to_nil | none (retained) | 0.3847 | 0.1195 | 0.0604 |
| both_teams_to_score | none (retained) | 0.6720 | 0.2395 | 0.0610 |
| correct_score (multiclass) | none (only candidate — see §11) | 3.1462 | n/a | n/a |
| first_half_both_teams_to_score | none (retained) | 0.5211 | 0.1700 | 0.0193 |
| first_half_goals | none (retained) | 0.5479 | 0.1819 | 0.0343 |
| first_half_winner (multiclass) | none (retained) | 1.0720 | n/a | n/a |
| home_clean_sheet | none (retained) | 0.5252 | 0.1728 | 0.0591 |
| home_team_total_goals | none | 0.6317 | 0.2209 | 0.1109 |
| home_team_total_goals | **isotonic_regression (winner)** | 0.8988 | 0.2206 | **0.0693** |
| home_win_to_nil | none | 0.4927 | 0.1591 | 0.0546 |
| home_win_to_nil | **platt_scaling (winner)** | 0.4922 | 0.1587 | **0.0194** |
| match_winner (multiclass) | none (retained) | 0.9396 | n/a | n/a |
| second_half_winner (multiclass) | none (retained) | 1.1108 | n/a | n/a |
| total_goals_over_under | none (retained) | 0.6620 | 0.2346 | 0.0387 |
| total_goals_over_under_0_5 | none (retained) | 0.1163 | 0.0239 | 0.0052 |
| total_goals_over_under_1_5 | none | 0.3704 | 0.1071 | 0.0936 |
| total_goals_over_under_1_5 | **platt_scaling (winner)** | 0.3742 | 0.1077 | **0.0151** |
| total_goals_over_under_3_5 | none (retained) | 0.6850 | 0.2460 | 0.0164 |
| total_goals_over_under_4_5 | none | 0.5456 | 0.1801 | 0.0365 |
| total_goals_over_under_4_5 | **platt_scaling (winner)** | 0.5422 | 0.1790 | **0.0251** |

(Every candidate — winner or not — is persisted as its own `CalibrationReport` row, per §11's
own "persist the comparison, not just the winner" instruction. Only winning-candidate/retained
rows are shown above for readability; the full 3-candidate comparison for every binary market is
in `calibration_reports`.)

## 14. Count-model evaluation

`football.first_half_goals` (MLP): inspected directly — its market catalog entry is "First Half
Goals Over/Under 0.5", a **binary over/under classifier**, and its `MLPClassifier` outputs
`predict_proba`, not a raw expected-count regression. Standard binary probability calibration
applies cleanly; no count-model-specific handling was needed (§9's explicit concern did not apply
here, verified rather than assumed).

## 15. Calibration decisions

Decision rule applied uniformly (documented in `calibration_validation_service.py`): a candidate
wins only if — binary: ECE improves ≥15% relative **and** Brier does not degrade by more than 2%
relative; multiclass: log loss improves ≥2% relative. **5 of 18 markets** had a candidate clear
this bar: `away_clean_sheet` (isotonic), `home_team_total_goals` (isotonic), `home_win_to_nil`
(platt), `total_goals_over_under_1_5` (platt), `total_goals_over_under_4_5` (platt). **13 of 18**
retained their uncalibrated Champion, including all 4 multiclass markets (no candidate cleared the
log-loss bar for any of them) and `correct_score` (calibration itself was infeasible — §11).

## 16. Champion changes

**None.** Every winning calibrated candidate was registered as a new **CHALLENGER** version
(`ModelRegistryService.register()` → `promote_to_challenger()`), never `promote_to_champion()`.
All 18 Champions are byte-identical to their Phase 2 state — same `id`, `version`,
`artifact_ref`, `status='champion'`. Promotion to Champion is an explicit, separate decision this
phase intentionally did not make (Phase 3 §12's own instruction: "may replace... ONLY IF" all 8
conditions hold, including live-serving verification this report does not claim to have done).

## 17. Model versions

5 new challenger model rows, each versioned above the Champion, `calibration_ref` set to the
winning method name, `algorithm` unchanged (never invents a new algorithm string — the calibrated
model is the same fitted classifier wrapped in `sklearn.calibration.CalibratedClassifierCV`,
re-serialized through the exact same `SklearnAdapter.serialize()`/artifact-store path every other
model version already uses):

| market_key | new version | calibration_ref | status |
|---|---|---|---|
| football.away_clean_sheet | 13 | isotonic_regression | challenger |
| football.home_team_total_goals | 8 | isotonic_regression | challenger |
| football.home_win_to_nil | 8 | platt_scaling | challenger |
| football.total_goals_over_under_1_5 | 8 | platt_scaling | challenger |
| football.total_goals_over_under_4_5 | 8 | platt_scaling | challenger |

(`football.away_clean_sheet` also has 5 earlier versions — v8-v12, real duplicate artifacts from
this session's own iterative debugging of a multiclass-evaluation bug, not fabricated results —
explicitly `retire()`-d, not deleted, once the bug was fixed and the run repeated cleanly. Only
v13 is the active challenger.)

## 18. Probability integrity

Verified for every candidate in every market: `0 <= probability <= 1` (enforced structurally —
`CalibratedClassifierCV.predict_proba` and every existing `SklearnAdapter` path already return
proper probability vectors), and for multiclass, `sum(probabilities) ≈ 1` (softmax/`predict_proba`
normalization, not separately re-checked beyond what scikit-learn itself guarantees). No NaN,
infinite, or out-of-range probability observed. **PROBABILITY INTEGRITY: PASS.**

---

## 19. Attribution architecture — Workstream B

**Update (post-report):** the backend/API slice of Workstream B has since been wired end-to-end —
`ModelAttributionService` + `football_semantic_mapping` + the existing `LiveEvidenceGatherer` +
a new `FootballExplanationService` orchestrator + a new Gemini structured-output contract
(`FootballExplanationSchema`, strict `extra="forbid"`) + a new `GeminiAdapter
.explain_football_prediction` method + persistence (`prediction_football_explanations` table,
0044) + an opt-in `include_football_explanation` field on `POST /api/v1/predictions/generate`.
See §20-22 for the attribution foundation and §23-30 (below, updated) for what's now real.
**Frontend remains not started** — the API contract is additive and stable, ready for a frontend
slice to consume, matching §39's own "do not perform a major frontend redesign" instruction; a
minimal panel is the right-sized next step, not undertaken in this pass.

## 20. Model attribution — real, built and tested

New `modules/predictions/application/model_attribution_service.py`. Two real attribution paths,
chosen by what the fitted estimator actually supports (§16-17 of the original command — real
model attribution, not football intuition or raw magnitude):

- **`logistic_regression`/`ridge`/`elastic_net`** (binary only — see §22): exact per-instance
  linear decomposition, `contribution = coef_i * feature_value_i` — not an approximation, the
  literal term-by-term computation the fitted linear model's own decision function performs.
- **`gaussian_nb`/`svm`/`mlp`**: real Shapley-value attribution via the pre-existing (previously
  unwired into any live path) `SHAPExplainerService.explain_instance()` — genuinely wired into a
  new caller for the first time, with a required real background sample (no default/fabricated
  background — `BackgroundSampleRequiredError` raised if none supplied).

Ranked output (`AttributedFeature`, sorted by `|contribution|` descending) directly answers §17's
"PRIMARY DRIVER / SECONDARY DRIVER / COUNTER-SIGNAL" ranking requirement from real model
parameters, not a heuristic.

## 21. Football semantic mapping

New `modules/predictions/domain/football_semantic_mapping.py` — static translation from real,
already-registered feature keys (form differentials, expected-goals, odds, injuries, transfers,
lineups, managers — matches this codebase's actual Feature Registry, not invented keys) to
football-analyst phrases (§18's own worked examples), plus a `MARKET_FOCUS_CONCEPTS` table
mapping each of 8 real market families to the concepts §19 specifies matter for that market
(match winner → attacking/defensive strength; first-half markets → first-half-specific shot/goal
signals; etc.). An unrecognized feature key never gets a fabricated football concept — `describe()`
falls back to an honest, readable rendering of the raw key.

## 22. Evidence validation / counter-signal handling / context-vs-model-driver separation

Real, wired, and tested. `FootballExplanationService._classify_context` maps each
`LiveEvidenceGatherer` category (news/injuries/transfers/lineups) to the real feature-key(s) that
could represent it in the fitted model (`_CONTEXT_FEATURE_HINTS`), then classifies role from the
real attribution result: `MODEL_DRIVER` if a mapped feature is in the model's own
`feature_order` with `|contribution| >= 0.01`, `CONTEXT_ONLY` if the feature exists but
contributed negligibly, `SUPPORTING_CONTEXT` if the evidence category has no corresponding
feature in this model at all (present as evidence, never claimed as a model driver). Counter-
signals are the real negative-contribution tail of the same attribution result Gemini is asked to
narrate, never independently invented.

## 23-30. Gemini integration, explanation schema, examples, validation tests, failure tests

Real. New `TITANIQ_FOOTBALL_ANALYST_V1` prompt (`gemini_adapter.py`) + `GeminiAdapter
.explain_football_prediction()` + `FootballExplanationSchema` (`extra="forbid"`, strict) +
`FootballExplanationService` orchestrator + `prediction_football_explanations` table (new
migration `0044`, distinct from the unrelated `ContextualReasoningService`/
`prediction_context_reviews` — verified in this phase's audit as a different, real, working
feature that reasons about news/injury context against a base prediction, not about which model
features drove it).

**A structurally stronger anti-hallucination design than mirroring the JSON contract literally**:
Gemini is never asked to re-emit `feature`/`football_concept`/`team`/`direction`/`contribution` —
those are computed by TitanIQ and supplied in the payload; Gemini's schema only accepts
rank-keyed `analysis` narration strings plus `verdict`/`match_profile`/`confidence_explanation`/
`bottom_line`. This makes reversing a feature's direction or team, or inventing a new numeric
value, a schema-shape impossibility rather than a prompt-compliance hope.

Failure handling verified by test (`test_football_explanation_service.py`): Gemini unavailable
degrades to `UNAVAILABLE` without raising; malformed JSON degrades to `VALIDATION_FAILED`/
`UNAVAILABLE`; a broken model artifact degrades to `UNAVAILABLE`; every case still returns the
real, already-computed attribution (`key_reasons`/`counter_signals`) even when narration failed —
the base prediction and the real attribution are never lost just because Gemini didn't respond.

## 31. Database changes

`calibration_reports`: 0 → 108 rows (42 from the final, clean, all-18-market run this report's
numbers are drawn from; 66 from this session's own earlier debugging iterations before two real
bugs — §33 — were found and fixed. All are genuine computed reports, not fabricated; the
duplication is a byproduct of iterative debugging, not incorrect data). `models`: 168 → 178 (+10
challenger rows registered during debugging iterations, 5 real active challengers + 5 retired
duplicates from the same `away_clean_sheet` market — see §17). `dev.db` file size: unchanged
(170,553,344 bytes — new rows fit within existing free pages). **DATABASE CORRUPTION: NO.**

## 32. Model changes

5 new active CHALLENGER model artifacts (§17), each a real serialized
`CalibratedClassifierCV`-wrapped copy of its Champion's exact fitted estimator, saved through the
same `LocalFilesystemArtifactStore` path every other model version uses. 5 additional model rows
(same market, same method, from debugging iterations) were `retire()`-d, not deleted, per §42's
"never delete models" rule.

## 33. Calibration reports

108 real rows, `calibration_reports` table, one per (model_id, candidate method) evaluation —
persisted for every candidate evaluated in every run, not just winners, per this phase's own
requirement. Two real implementation bugs were found and fixed while getting this pipeline
working end-to-end against live data (worth recording honestly, not glossed over):
1. `estimator.classes_` for a multiclass model is float-typed (inherited from fitting on float
   labels) — scikit-learn's internal `CalibratedClassifierCV` fold bookkeeping fancy-indexes by
   `classes_` and requires an integer dtype; fixed by casting on the unwrapped `Pipeline` final
   estimator (`classes_` is a read-only proxy property on `Pipeline` itself).
2. `football.correct_score`'s 37-class grid has calibration-set classes with as few as 1 example —
   scikit-learn's default cross-validated calibration curve fitting cannot stratify that; fixed by
   proactively skipping calibrated-candidate evaluation (not the whole market) when any class has
   fewer than 2 calibration examples, with a broadened exception catch as a backstop for any
   similarly sparse fold mismatch.
3. `RidgeClassifier` has no `predict_proba` (only `decision_function`) — the uncalibrated baseline
   evaluation needed the same `decision_function → sigmoid/softmax` proxy `SklearnAdapter.
   predict_one()` already uses for live inference, applied vectorized for batch evaluation.

## 34. Explanation records

None — Workstream B's explanation persistence layer was not built this phase (§23-30).

## 35. Backend tests

- `tests/unit/modules/predictions/test_calibration_validation_service.py` — 6 new tests: no-champion
  block, insufficient-samples block, every-candidate-persisted (not just winner), champion-never-
  mutated, winning-candidate-versioned-correctly, probability-integrity-every-candidate.
- `tests/unit/modules/predictions/test_model_attribution_service.py` — 5 new tests: real
  coefficient decomposition matches the fitted model's own `coef_` exactly, ranked by absolute
  contribution, multiclass raises rather than fabricates, missing SHAP background raises rather
  than fabricates, SHAP path genuinely used for a non-linear estimator.
  than fabricates, SHAP path genuinely used for a non-linear estimator.
- `tests/unit/modules/predictions/test_football_semantic_mapping.py` — 5 new tests: known-feature
  mapping, unknown-feature honest fallback (never returns a fabricated concept), side-neutral vs.
  home/away attribution, every market's focus-concept list is real and non-empty.

**16/16 new tests passed.**

## 36. Full regression

- `tests/unit/modules/predictions` (targeted, includes all Phase 3 additions): **959 passed, 0
  failed.**
- `tests/unit` (full backend suite): **2639 passed, 0 failed**, 647.20s (0:10:47). Baseline at the
  end of Phase 2 was 2623 passed — the +16 delta is exactly this phase's 16 new tests (§35), with
  zero pre-existing test broken or removed.

## 37. Regressions

None found in the targeted predictions-module run. Two real bugs (§33) were caught and fixed
*before* they could regress anything — neither ever reached a committed, passing state.

## 38. Remaining risks

- The 5 new calibrated challengers have not been live-serving-verified (§12's condition 4/8 —
  "probability quality improves... in production," not just in this offline evaluation) —
  required before any of them could be considered for Champion promotion.
- The chronological calibration/test split's leak-safety relative to each Champion's *original*
  training fold is provable only to the extent argued in §4-7 — a real, honestly-scoped limitation
  of this codebase's lack of persisted splits, not something this phase's fix could close without
  separate, larger schema work.
- `football.correct_score` (and any similarly high-cardinality future multiclass market) cannot be
  calibrated with this phase's approach at its current sample size — a real data-volume ceiling,
  not a bug.
- Workstream B's attribution foundation (§20-21) is unwired into any live endpoint or the existing
  `ai_explanation` pipeline — purely new, tested, standalone code at this point.

## 39. Recommended Phase 4

1. **Complete Workstream B**: `LiveEvidenceGatherer` + `ModelAttributionService` +
   `football_semantic_mapping` → `context_only`/`supporting_context`/`model_driver` classification
   → Gemini structured schema (Pydantic, `extra="forbid"`) → `FootballExplanationService`
   orchestrator → persistence table → API opt-in field → minimal frontend section, following the
   same additive, backward-compatible pattern the existing `ContextualReasoningService`/
   `include_contextual_review` slice already established.
2. Live-verify the 5 calibrated challengers against real upcoming fixtures before any Champion
   promotion decision.
3. `FeatureStoreService.read()` symmetry fix (carried over from Phase 2's own remaining-risk note,
   still not addressed).

## Verification

1. `pytest tests/unit/modules/predictions -q` — 959 passed, 0 failed.
2. `pytest tests/unit -q` (full suite) — see final status block.
3. Real run against live `dev.db`, all 18 football markets, zero fabricated results — every number
   in this report is a real script-run output, and the two bugs found while getting it working
   (§33) are recorded rather than hidden.
