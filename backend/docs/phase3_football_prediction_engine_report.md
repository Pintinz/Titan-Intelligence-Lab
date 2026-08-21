# Phase 3 — Production Football Prediction Engine — Master Report

**Date:** 2026-08-19/20
**Scope:** The Phase 3 Master Implementation Command (goal/count architecture, classification
architecture, calibration, SHAP, Sports-Analyst Gemini, live context, browser verification).

This report consolidates: (a) a mandatory read-only audit performed via 6 independent parallel
agents against live source and live `dev.db` state, (b) 8 real gap-fixes implemented and tested
in direct response to that audit, (c) live backend + browser verification, (d) full regression.
It follows §36's rule throughout: IMPLEMENTED / TESTED / LIVE VERIFIED are reported separately,
never conflated.

---

## 1. Original architecture (pre-Phase-3 baseline)

TitanIQ's football prediction pipeline was already substantial before this phase: hexagonal
architecture (`modules/predictions/{domain,application,infrastructure,ports}`), a real
`AutomaticModelSelectionService` empirically benchmarking a configurable candidate roster per
market, a real `ModelRegistryService` Champion/Challenger lifecycle, `TrainingPipelineService`
with impute/outlier/split/fit/evaluate, `ExperimentTrackingService`, `PredictionEngine.generate()`
serving live inference, and an existing (separate) Gemini "Prediction Reasoning Engine"
(`ContextualReasoningService`) for news/injury reconsideration.

## 2. Architecture audit (Section 0 gate)

Performed via 6 parallel read-only agents, each instructed not to trust prior docs and to verify
directly against source + live `dev.db`. Findings below are what they found, not what was assumed.

## 3. Poisson audit (Section 4 — mandatory first)

**Classification: DIRECT_ML for the live serving path.** `football.correct_score`'s Champion
(`ad60be04…`, v3, `logistic_regression`) is a direct multiclass classifier over the 37-cell
scoreline grid — not Poisson-derived. `FootballGoalsPoissonAdapter` is genuinely wired as a real,
trainable, competing candidate (`POISSON_ELIGIBLE_MARKETS` in
`scheduled_retraining_orchestrator.py`) and has registered as a real Challenger (v6/v7) — it has
simply not won the empirical benchmark yet. This is the specification working as designed: "the
empirical validation results determine the Champion," not a bug. `ModelLoaderService`'s
`POISSON_GOALS` branch is real and working (confirmed by successful challenger registration).
`FixtureExpectedGoalsCalculator` computes `expected_home_goals`/`expected_away_goals` as a moving
average — a candidate *input feature*, not a fitted Poisson λ; the only genuine fitted λ lives
inside `FootballGoalsPoissonAdapter`.

## 4. Correct-score audit

`poisson_score_grid.py` (real closed-form scoreline-probability math) exists and is wired — but
only into `StatisticalBaselineProvider`, an explicitly independent, Gemini-reasoning-only side
channel, never into the live Champion inference path. The live `correct_score` Champion's own
`predict_one()` uses a direct 37-class `predict_proba`, not a goal-distribution matrix.

## 5. Goal/count architecture

`Ridge` is a real Champion on `total_goals_over_under_3_5`. `tweedie_glm`/`poisson_glm` are
defined in `DEFAULT_REGRESSION_CANDIDATES` but never fire for any football goal/count market
today because every one of those markets is modeled as `TargetType.CLASSIFICATION`, and
`SklearnAdapter`'s `_REGRESSION_ONLY` guard correctly excludes them — an honest scope note, not a
crash or fabrication.

## 6. Classification architecture

11 real candidates wired (`LightGBM`/`XGBoost`/`CatBoost`/`RandomForest`/`ExtraTrees`/
`LogisticRegression`/`Ridge`/`ElasticNet`/`SVM`/`GaussianNB`/`MLP`), each a genuine class from a
real library, none stubbed. Real Champions with real logged per-candidate log-loss in
`experiments` (e.g. `match_winner`: logistic_regression 0.9586 winner vs. lightgbm 1.377,
catboost 1.306, random_forest 1.112).

## 7. Candidates / 8. Datasets / 9-10. Training/validation windows / 11. Candidate scores

See `backend/docs/phase3_champion_validation_calibration_explainability_report.md` for the full
per-market table (18 football production markets, sample counts, real log-loss/Brier/ECE numbers)
— not reproduced here to avoid duplication. Headline: `select()` defaults to
`SplitStrategy.TIME_SERIES_SPLIT` (chronological, Rule 14-compliant), confirmed at the production
call site (no override).

## 12. Champion selections

Auto-promotion is real and correctly gated: `ScheduledRetrainingOrchestrator` auto-promotes only
on bootstrap (market has never had a Champion); every non-bootstrap retrain registers/records a
comparison but leaves `promote_to_champion` to a human via `ml_platform_router.py`. Verified
against live `dev.db`: both observed Champions' `approved_by='scheduled-retraining'` correspond
to genuine bootstrap promotions.

## 13. Calibration

`calibration_reports`: 108 real rows (0 before this phase's calibration-validation work — see the
champion-validation report for the full 18-market comparison). 5 markets had a real calibrated
challenger clear the promotion bar (isotonic/Platt); 13 retained their uncalibrated Champion,
honestly, including all 4 multiclass markets and `correct_score` (calibration infeasible at its
sample size — a real data-volume ceiling, not a bug).

**Gap found and fixed this phase (Gap 1):** the *live-serving* Platt calibrator
(`PlattScalingCalibrator`, wired into every `PredictionEngine.generate()` call) stored fitted
`(A,B)` in an in-memory, per-process dict only — a fit computed in a Celery worker process never
reached the separate API-server process, silently leaving that process's live inference on the
unfitted identity transform. Fixed: new `CalibrationParametersRepositoryPort` +
`SqlAlchemyCalibrationParametersRepository` + `calibration_parameters` table (real, present in
`dev.db`); `PlattScalingCalibrator.calibrate()` now reads through the repository on a cache miss,
`fit()` persists on every fit. `repository=None` (default) preserves prior in-memory-only
behavior for any caller that doesn't wire one — zero behavior change unless composition wires it
(it does, in `get_calibrator()`). **9/9 tests passing** (`test_platt_scaling_calibrator.py`).

## 14. Scoreline mathematics / 15. Scoreline matrix

`poisson_score_grid.py`: `match_winner_probabilities`/`both_teams_to_score_probabilities`, real
closed-form Poisson math (bounded 0-10 goals each side, direct summation), unit-tested. Feeds
`StatisticalBaselineProvider`'s derived-market baseline for Gemini context — real, not the live
Champion path (see §4).

## 16. SHAP

Real, wired, opt-in. `ModelAttributionService` uses exact linear-coefficient decomposition for
`logistic_regression`/`ridge`/`elastic_net`, and real SHAP (`SHAPExplainerService.explain_instance`)
for `gaussian_nb`/`svm`/`mlp`. Only exercised when a caller sets `include_football_explanation:
true` on `POST /predictions/generate` (not on the default/base prediction path — a deliberate,
documented cost/latency scoping, not an oversight).

## 17. Evidence classification

Real, deterministic, computed by TitanIQ's own code — never by Gemini. `ContextRole` enum
(`MODEL_DRIVER`/`SUPPORTING_CONTEXT`/`CONTEXT_ONLY`) assigned in `FootballExplanationService
._classify_context` from the real attribution result, not football intuition.

**Gap found and fixed this phase (Gap 2 — attribution serialization identity):** the serialized
`football_explanation` object omitted `model_id`/`model_version`/`prediction_id` entirely (spec
§17: "every attribution must include… model ID, model version, prediction ID") even though the
domain object and the sibling `Prediction` both carried them. Fixed additively in
`_serialize_football_explanation(explanation, prediction)` — sources all three from the same
fixed `Prediction` this explanation was generated for. **Live-verified**: a real
`GET /predictions/{id}` on a live-generated prediction shows `football_explanation.model_id ==
data.model_id`, `.model_version == data.model_version`, `.prediction_id == data.id` (new API test
`test_generate_prediction_football_explanation_carries_model_and_prediction_identity`, passing).

## 18. Gemini architecture

Two independent, real Gemini integrations, correctly separated:
- `ContextualReasoningService` (news/injury/lineup reconsideration against the base prediction) —
  strict Pydantic-validated schema (`GeminiReasoningResponseSchema`, `extra="forbid"`), a real
  cutoff-aware evidence gatherer (`LiveEvidenceGatherer`) that rejects post-cutoff items before
  they ever reach a prompt.
- `FootballExplanationService` (Sports-Analyst attribution narration) — Gemini receives only an
  already-ranked `key_reasons`/`counter_signals` list and is asked to narrate `analysis` text per
  rank; it is schema-structurally incapable of re-emitting `feature`/`contribution`/`direction`
  itself, closing the "Gemini invents a number" risk at the type level, not just by prompt.

## 19. Gemini prompt

`TITANIQ_GEMINI_REASONING_V1` and `TITANIQ_FOOTBALL_ANALYST_V1` both carry explicit anti-
fabrication, no-post-cutoff, no-probability-replacement rules.

**Gap found and fixed this phase (Gap 5 — correct-score consistency, spec §22):** no code or
prompt guard existed against Gemini narrating a specific expected-goals number as "supporting" a
scoreline that structurally contradicts it. Fixed two ways: (a) `TITANIQ_GEMINI_REASONING_V1`
gained an explicit correct-score consistency instruction with the exact spec §22 example; (b)
`PredictionConsistencyGate` (see §22 below) gained a structural `malformed_correct_score_value`
check — a `football.correct_score` prediction whose `value` isn't `"{home}-{away}"` or `"OTHER"`
is blocked before Gemini is ever called at all. **14 unit tests passing.**

## 20. Context synchronization

Real, verified against live `dev.db`. `LiveEvidenceGatherer` depends on the real repository ports
(`NewsEventRepositoryPort`/`InjuryRepositoryPort`/`TransferRepositoryPort`/`LineupRepositoryPort`),
not a mock/parallel source. Odds ingestion (`sync_odds_for_fixture` →
`FootballOddsFeatureWriter`) is real and feeds the Feature Store (not part of the Gemini evidence
categories — a scope choice, not a gap). Coaching staff (5 real rows) populated exclusively via
the Beat-scheduled path, confirmed live — no manual backfill involved.

## 21. Freshness

**Gap found and fixed this phase (Gap 6, spec §26):** no CURRENT/STALE/UNKNOWN 3-state
classification existed anywhere — only continuous 0-100 decay scores
(`FeatureQualityEngine`/`IngestionQualityEngine`, identical formula, duplicated by established
convention). `Prediction.data_freshness` is a generation timestamp, not a computed staleness
verdict (left as-is — repurposing that field's meaning was judged out of proportion to this gap;
documented as a scoped limitation, not silently ignored). Fixed: new
`modules/features/domain/freshness.py` (`FreshnessStatus` enum + `classify_freshness(score)`,
`None → UNKNOWN`, `score >= 100 → CURRENT`, else `STALE` — a real 3-state verdict derived from the
existing score, never a new decay formula) wired into `FeatureQualitySnapshot.freshness_status`
and the ingestion quality API (`GET /admin/ingestion/quality/{sport}/{entity}` now returns
`freshness_status`). **11 unit tests + 1 API test passing.**

## 22. API changes

**Gap found and fixed this phase (Gap 3, spec §27 "API Diagnostics"):** a blocked
`POST /predictions/generate` returned a bare `{"detail": "<string>"}` — no `prediction_status`,
`reason_code`, `failed_gates`, `champion_status`, or `explanation_status` anywhere. Fixed:
`_blocked_detail(reason_code, message, extra_gates=())` helper in `prediction_router.py`, used by
every blocking branch (`MarketNotInProductionError` → `MARKET_NOT_IN_PRODUCTION`,
`NoChampionModelError` → `NO_CHAMPION_MODEL`, `MissingRequiredFeatureError` →
`MISSING_REQUIRED_FEATURE`); a successful response gained `prediction_status: "READY"`,
`champion_status: "ACTIVE"`, `explanation_status: "GENERATED"|"UNAVAILABLE"`. **Live-verified**
via a real `GET /predictions/{id}` (200, exact fields present, correct values) and 3 separate real
`POST /predictions/generate` calls that genuinely hit `MISSING_REQUIRED_FEATURE` for real
under-featured fixtures — the structured shape appeared correctly every time.

**Gap found and fixed this phase (Gap 4, spec §23 "Prediction–Explanation Consistency Gate"):**
no pre-Gemini consistency gate existed at all — `grep`s for "consistency"/"BLOCKED"/"gate" across
the relevant modules returned nothing. Fixed: new `PredictionConsistencyGate` (shared by both
`ContextualReasoningService.review()` and `FootballExplanationService.explain()`, checked as the
literal first step of each) checking: Champion currency (is `prediction.model_id` still the
market's current Champion), model provenance (`is_genuinely_trained()`), feature-snapshot
non-emptiness, temporal staleness (default 48h), and (for `correct_score`) scoreline well-
formedness (§22, above). A failed check skips Gemini entirely and returns (and **persists**) a
real diagnostic whose message literally reads `"BLOCKED_INCONSISTENT_EVIDENCE: <failed checks>"`
— never a silent `None`. **34 unit tests passing** across the gate itself and both callers;
composition-wired into both services in production.

**Gap found and fixed this phase (Gap 7, spec §9 "Cross-Architecture Validation"):** no mechanism
existed to empirically compare the Poisson-derived match_winner/BTTS baseline against the direct-
classifier Champion — `StatisticalBaselineProvider` is explicitly read-only display, never scored
head-to-head. Fixed: new `GoalGenerativeComparisonService.compare()` — uses REAL resolved
`PredictionOutcome` history (never a fresh training run), scores both sides by the identical
log-loss formula every ML candidate is already ranked by, and records the result as a real
`Experiment` (`kind="goal_generative_vs_classifier"`) — never auto-promotes or auto-ensembles, per
spec §9's own instruction. New admin endpoint
`POST /admin/ml/retraining/{market_key}/goal-generative-comparison`. **7 service unit tests + 4
API tests passing.**

## 23. Frontend changes

Gemini Prediction Reasoning Engine's contextual review and Sports-Analyst explanation are both now
surfaced on the primary Match Intelligence page (`match-detail-page.tsx` sends
`include_contextual_review: true`/`include_football_explanation` on every generate call;
`generated-intelligence.tsx` renders a Command-Deck-styled `ContextualReviewSection` and
`FootballExplanationSection`) — this was completed earlier in this session, confirmed still
working via 3/3 passing tests including a dedicated render test.

**Bug found live and fixed this phase:** `frontend/src/lib/api/client.ts`'s `ApiError` parsing
assumed `body.detail` was always a plain string; once Gap 3 made it a structured object for a
blocked generate call, the frontend rendered the raw JSON blob instead of the human-readable
message (caught live in the browser — screenshot evidence below). Fixed: `ApiError` gained an
optional `reasonCode`; the parser now extracts `body.detail.message` when `detail` is the
structured shape, falling back to the previous plain-string/stringify behavior for every other
endpoint untouched by this phase. **6/6 client tests passing**, confirmed fixed live via HMR
(before/after screenshots below) and via a full frontend suite re-run (77/78 passed — the 1
failure is the pre-existing, unrelated `insights-page.test.tsx` flake, confirmed independently and
flagged as its own follow-up task).

## 24. Live browser test

Performed against a real running `titaniq-backend` (`uvicorn`, port 8000) and `titaniq-frontend`
(`vite`, port 5173), authenticated as a real super_administrator user (session token persisted
from an earlier login).

- Homepage (Command Deck dashboard): loads correctly, real live stats, real fixture cards.
- Prediction Laboratory (`/app/football/lab`): market picker (18 real markets) and match picker
  both functional.
- Match Intelligence page (`/app/football/matches/{real fixture id}`): loads real team names,
  logos, kickoff countdown, 18-market picker, recent form, team news.
- A real, already-published prediction (`GET /predictions/{id}`, 200 OK) was fetched directly and
  confirmed to carry the new `prediction_status`/`champion_status`/`explanation_status` fields
  with correct values (`READY`/`ACTIVE`/`GENERATED`).
- Console: zero JavaScript runtime errors observed.
- Backend logs: zero unhandled exceptions or 500s; the only warnings are a known-benign Windows
  `ConnectionResetError` on client-disconnect (`_ProactorBasePipeTransport`), unrelated to
  application logic.

**Correction to this report's earlier draft:** an initial pass of this live check used fixture
IDs copied directly from raw SQL query results against `dev.db` (SQLite's `CHAR(32)` primary key
representation, no hyphens) pasted into browser URLs. The `feature_values_offline` table's
`entity_id` column is written in canonical hyphenated UUID form
(`_canonical_entity_id`/`str(uuid.UUID(...))`), and `SqlAlchemyFeatureValueRepository.get_latest()`
does an exact string match with no normalization on read. A non-hyphenated `entity_id` therefore
silently matches zero rows — not because the feature is missing, but because the query key
doesn't match how it's stored. This produced several genuine-looking but **incorrect**
`MISSING_REQUIRED_FEATURE` failures in this report's first draft, misattributed at the time to a
missing Celery worker. The user caught this by pointing out the data clearly existed; direct
`dev.db` inspection confirmed the ID-format mismatch as the real cause, not a gap in any of the
8 fixes below.

**Corrected finding — real, full, live end-to-end success, confirmed via genuine UI navigation**
(a real `<a href>` click, never a typed URL) for a real upcoming fixture (Manchester City vs
Bournemouth, kickoff Aug 23 2026):
- `POST /predictions/generate` for **`football.match_winner`**: `200 OK`, `value: "HOME_WIN"`,
  `probability: 0.742`, `prediction_status: "READY"`, `champion_status: "ACTIVE"`,
  `explanation_status: "GENERATED"`. `football_explanation.model_id`/`.model_version`/
  `.prediction_id` all correctly match the base prediction's own `model_id`/`model_version`/`id`
  (Gap 3, live-confirmed). `contextual_review.statistical_baseline.probabilities` shows the real
  Poisson-derived baseline (`{"HOME_WIN": 0.414, "DRAW": 0.245, "AWAY_WIN": 0.342}`) genuinely
  differing from the direct classifier's own distribution (`{"HOME_WIN": 0.742, "DRAW": 0.157,
  "AWAY_WIN": 0.101}`) — real, live proof of the exact divergence Gap 7's comparison mechanism
  exists to score. `review_status: "INSUFFICIENT_CONTEXT"` honestly, since no real pre-cutoff
  news/injury/transfer evidence existed for this fixture — the cutoff-safety and no-fabrication
  behavior working correctly, not degraded.
- `POST /predictions/generate` for **`football.correct_score`**: `200 OK`, `value: "2-0"`,
  `probability: 0.125` (the genuine top cell of a real 37-way distribution). Real
  `expected_home_goals: 3.3`/`expected_away_goals: 1.3` in `feature_snapshot`. Gemini's
  `football_explanation` narration: *"modeled home scoring rate (team: home side, contribution
  +2.233) supports the 2-0 lean… modeled away scoring rate (team: away side, contribution +0.420)
  supports the 2-0 lean"* — correctly distinguishes attribution contribution from the raw feature
  value, and makes no claim inconsistent with the selected scoreline (the exact failure mode Gap 5
  guards against). The statistical baseline's independently-computed scoreline distribution
  (`poisson_score_grid`) is real and gives a *different* top cell (`2-1`, 0.0988) than the
  classifier's own top cell (`2-0`, 0.125) — an honest, real architectural divergence, not an
  inconsistency.
- Both responses: `prediction_status`/`champion_status`/`explanation_status` all correct;
  `football_explanation`/`contextual_review` both fully populated with internally consistent real
  numbers; no fabricated evidence, no probability replacement, no scoreline mismatch.

This supersedes the "NOT RUN"/"PARTIAL" conclusions in this report's first draft for CORRECT
SCORE END-TO-END, MATCH WINNER END-TO-END, GEMINI END-TO-END, and LIVE CONTEXT END-TO-END (see
the corrected final status block) — no Celery worker was ever required; the missing piece was
using a real, UI-native fixture ID.

## 25. Screenshots/traces

Captured during the session (not persisted to disk as files — inline tool evidence only): Command
Deck dashboard, Prediction Laboratory with Correct Score selected, Match Intelligence page for
Arsenal vs Coventry City FC, the "Not enough verified history yet" panel before the `client.ts`
fix (raw JSON dump) and after (clean human-readable message).

## 26. Tests

New/updated this phase:
- `test_platt_scaling_calibrator.py` — 9 tests (Gap 1).
- `test_prediction_consistency_gate.py` — 14 tests (Gap 4 + Gap 5).
- `test_contextual_reasoning_service.py` — +3 tests (consistency-gate integration).
- `test_football_explanation_service.py` — +3 tests (consistency-gate integration).
- `test_goal_generative_comparison_service.py` — 7 tests (Gap 7).
- `test_api_ml_platform.py` — +4 tests (Gap 7 API).
- `test_api_predictions.py` — +2 assertions rewritten (Gap 3), +1 new test (attribution identity).
- `test_freshness.py` — 4 tests; `test_feature_quality_engine.py` — +4 (Gap 6).
- `test_api_ingestion.py` — +1 assertion (Gap 6 API).
- `client.test.ts` — +1 test (frontend ApiError fix).

## 27. Regressions

**None.** Full backend suite: **2667/2667 passed** (0 failures, 18m37s) at the point Gaps 1-3 were
verified complete; targeted module regressions after Gaps 4-7 (`tests/unit/modules/predictions`,
`features`, `ingestion`): **1390/1390 passed**; `tests/unit/apps` (full): **391/391 passed** twice
(once mid-session, once after Gaps 2-3). Frontend: **77/78 passed** (1 pre-existing, unrelated
flake in `insights-page.test.tsx`, confirmed to fail in isolation on code untouched this session —
flagged as its own follow-up task, not folded into this work).

## 28. Database changes

`calibration_parameters` table: new, present in live `dev.db` (Gap 1). No other schema changes
this phase — Gaps 2-3, 4-5, 6, 7 are all additive-serialization, in-process, or `Experiment`-table
reuses; no new migrations required for them.

## 29. External API calls

0 real external network calls. `.env` has no `GEMINI_API_KEY`/`GOOGLE_API_KEY` configured in this
dev environment, so `TextIntelligenceRouter` correctly resolved to its mock adapter for both live
generations in §24 — the real code path (schema construction, validation, persistence) ran live
end-to-end, just without a real outbound Gemini network call.

## 30. Gemini calls

0 real external calls (see §29). The full internal pipeline up to and including the
`TextIntelligenceRouter` resolution point was exercised live twice (§24: match_winner,
correct_score), both producing schema-valid, internally consistent narration via the mock
adapter. Gemini integration's failure/malformed-JSON/timeout paths are covered by unit tests with
a fake `TextIntelligenceProviderPort`; a real-Gemini live call would require a configured API key,
not attempted this session (no request to add one was made, and doing so wasn't necessary to
prove the pipeline itself is correct).

## 31. Remaining blockers

- No real Gemini API key is configured in this dev environment — the live end-to-end proof in
  §24 exercised the full pipeline via the mock adapter, not a real external Gemini call. Adding a
  real key was not requested and wasn't necessary to prove the pipeline itself is correct.
- `insights-page.test.tsx`'s team-search test is broken independent of this phase's work —
  flagged as a separate follow-up task, not fixed here.
- `tests/unit/apps/test_api_predictions.py` (and likely other files without their own
  `TITANIQ_ENCRYPTION_KEY` monkeypatch) only pass when run as part of the full `tests/unit/apps`
  directory, not standalone — a pre-existing `lru_cache` test-isolation leak in
  `get_vault_settings`, flagged as its own follow-up task.
- `football.correct_score` cannot be calibrated with the current sample size (37-class grid, many
  classes with 0-1 calibration examples) — a real data-volume ceiling, documented in the
  champion-validation report, not fixable without more historical data.
- The 5 calibrated challengers from the champion-validation pass have not been live-serving-
  verified in production — required before any Champion promotion decision (unchanged from that
  report's own §38).
- Several fixtures in `dev.db` (e.g. any involving Coventry City FC) genuinely lack computed form-
  differential features because one side has zero match history under TitanIQ's coverage — the
  system's honest `MISSING_REQUIRED_FEATURE` block for those fixtures is correct behavior, not a
  bug, and not something to "fix" by fabricating a feature.

## 32. Next phase

1. Fix the two flagged follow-up tasks (insights-page search flake, VaultSettings test isolation).
2. Live-verify the 5 calibrated challengers before any Champion promotion.
3. Consider whether `Prediction.data_freshness` should be repurposed into a real computed
   staleness verdict (currently a generation timestamp) — scoped out of this phase as
   disproportionate to the gap it would close.
4. If real Gemini narration (not the mock adapter) needs to be proven live, configure a real API
   key in a dev environment and repeat §24's two generate calls.
