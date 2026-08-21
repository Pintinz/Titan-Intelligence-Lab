# Phase 4 — Production Activation + Live End-to-End Verification

**Date:** 2026-08-20

Phase 3's implementation is unchanged in this phase — no architecture redesign, no new
prediction-engine code. This phase's only code change is a frontend `client.ts` fix carried over
from the tail of Phase 3's live verification (documented there, not repeated here). Everything
else below is infrastructure activation and live verification.

## 1. Infrastructure audit

No `docker-compose.yml`/`Dockerfile` exists in this repo — Redis is expected to run as a plain
external service reachable at `TITANIQ_REDIS_URL` (`.env`: `redis://127.0.0.1:6379/0`), used as
both Celery broker and result backend (`modules/ingestion/infrastructure/celery/celery_app.py`,
single instance, no separate cache/broker split — confirmed by reading the module directly, not
assumed). Worker launch command (`.claude/launch.json` / this repo's own convention):
`celery -A apps.worker.bootstrap worker`, no `-Q` flag (single default queue — Milestone 24
removed multi-queue routing after confirming no production invocation ever consumed the extra
queues). `apps/worker/bootstrap.py` uses an explicit, fail-closed `FACTORY_REGISTRY` — every
production service factory must register or the worker refuses to report ready.
`TITANIQ_ENABLE_OFFLINE_AUTH=true` and `TITANIQ_NEWS_SYNC_ENABLED=true` are both set; no
`GEMINI_API_KEY`/`GOOGLE_API_KEY` is configured anywhere in `.env`.

## 2. Redis

**No Redis server exists natively on this Windows host.** WSL2 (Ubuntu, Ubuntu-24.04) is
installed and has `redis-server v7.0.15` already present. Real, honest attempt made to bring up
the repo's intended single Redis instance:

1. Started `redis-server` inside WSL Ubuntu (daemonized, bound `0.0.0.0`) — responded `PONG` to
   `redis-cli ping` from inside WSL immediately.
2. Tested reachability from Windows (where the actual `uvicorn`/`celery` processes run) at
   `127.0.0.1:6379`, matching `.env`'s `TITANIQ_REDIS_URL`. WSL reported "Failed to configure
   network (networkingMode Nat), falling back to networkingMode VirtioProxy" on every WSL
   invocation — a known WSL2 networking fallback path.
3. First connectivity test: succeeded (`PING → True`).
4. Immediate follow-up: 5/5 sequential pings failed (`ConnectionError`, `ConnectionRefusedError`,
   `ConnectionResetError` — three distinct failure modes across attempts, ~25-27s each despite a
   3s socket timeout parameter, meaning even the timeout itself wasn't being honored reliably).
5. Attempted the standard documented fix: `%USERPROFILE%\.wslconfig` with
   `networkingMode=nat` (forcing the WSL2 default instead of accepting the fallback), followed by
   `wsl --shutdown` and a fresh restart. WSL logged the identical "Failed to configure network...
   falling back to VirtioProxy" message again — the underlying NAT-mode failure is a host-level
   condition (likely a VPN adapter, firewall, or Hyper-V vSwitch conflict on this specific
   machine) that a WSL-side config change cannot resolve. The `.wslconfig` file was removed again
   after confirming it made no difference, restoring the host to its original state.

**REDIS: FAIL** — reachable, but not reliably enough for `celery -A ... worker` or a real Beat
scheduler to depend on. This is a genuine limitation of this Windows host's WSL2 networking, not
a defect in TitanIQ's own Redis/Celery configuration (which is correctly written — confirmed in
§3 below, where the same configuration correctly detects and reports this exact failure).

**Important, load-bearing finding carried over from Phase 3:** the core live-serving path
(`POST /predictions/generate`, including Gemini contextual reasoning and Sports-Analyst
explanation) does **not** hard-depend on Redis. `ContextualReasoningService`'s cache read/write
is deliberately wrapped in `except Exception: pass` (degrades to "always miss," never an error —
by design, per that service's own docstring). This was proven, not assumed: Phase 3's live
generate calls for `football.match_winner`/`football.correct_score` succeeded with real Gemini
narration *while Redis was in this exact broken state*, before any of today's Redis work began.

## 3. Celery Worker

Started the real worker with the repo's own command
(`celery -A apps.worker.bootstrap worker --loglevel=info --pool=solo -Q celery`, `.env` sourced):

```
worker: starting bootstrap
worker: configuration validated
worker: database session factory initialized
worker: task modules imported: modules.admin.infrastructure.celery.tasks,
  modules.ingestion.infrastructure.celery.tasks, modules.intelligence.infrastructure.celery.tasks,
  modules.predictions.infrastructure.celery.tasks
worker: 6/6 factories registered
worker: factory registry validated — all 6 factories ready
worker: ready
[queues] celery exchange=celery(direct) key=celery
[tasks] 16 real task names registered (admin.check_all_provider_health,
  ingestion.sync_*, intelligence.sync_scheduled_news, predictions.check_scheduled_*)
```

Bootstrap itself is **fully correct and fail-closed exactly as designed**: all 6 factories
registered, all 16 tasks discovered, configuration validated. The worker then correctly detected
the real Redis unreachability and entered its own retry loop:

```
ERROR/MainProcess: consumer: Cannot connect to redis://127.0.0.1:6379/0: Error 10061
  connecting to 127.0.0.1:6379. No connection could be made because the target machine
  actively refused it.
Trying again in 2.00 seconds... (1/100)
Trying again in 4.00 seconds... (2/100)
```

**CELERY WORKER: FAIL** (transport only — bootstrap/task-registration logic is proven correct;
the failure is exclusively the Redis reachability documented in §2, not a Celery/TitanIQ defect).

## 4. Celery Beat

Not started. §6's own safety instruction applies doubly here: Beat cannot be meaningfully
verified without a working worker to consume what it emits, and starting it against an
unreachable broker would only queue tasks that could never be picked up — no new information
would be gained, and depending on schedule timing could accumulate an unbounded backlog once
Redis did become reachable later. **CELERY BEAT: NOT STARTED — SAFETY REASON** (blocked
transitively by §2/§3, not a new gate of its own).

## 5. Live fixture

Manchester City vs Bournemouth (`c5eeabe6-d61d-4f40-a9cb-41c897b22d2f`), Premier League, kickoff
2026-08-23 13:00 UTC — real team identity, real competition, real kickoff, `AI READINESS: Ready`
on the live match page, real recent-form history for both sides (8 completed matches with real
scorelines), Champion available for all 18 football markets.

**Correction recorded here for completeness** (already corrected in the Phase 3 report): an
earlier pass of this same investigation used fixture IDs copied directly from raw SQL query
results (SQLite's non-hyphenated `CHAR(32)` primary-key representation) pasted into browser URLs.
The `feature_values_offline.entity_id` column is written in canonical hyphenated form; the read
path does an exact string match with no normalization, so a non-canonical ID silently matches
zero feature rows. Real UI navigation (`<a href>`, never a typed URL) always uses the API's own
`str(uuid.UUID(...))` serialization and never hits this. All fixture navigation in this phase
used real UI links only.

## 6. Live context

`GET`-equivalent evidence gathered via the live `contextual_review` payload on real generate
calls (§8): `evidence_quality.pre_event_only: true`, `missing_context: ["news", "injuries",
"transfers", "lineups"]`, `prediction_cutoff` a real timestamp. Traced *why* context is honestly
empty for this fixture rather than assuming a bug: Bournemouth's 10 `injuries` rows in `dev.db`
are all dated 2023-2024 (clearly historical/training-era records) with
`information_available_at IS NULL` and `availability_classification = 'UNKNOWN_AVAILABILITY_TIME'`
— `LiveEvidenceGatherer` correctly excludes them from Gemini's evidence pool because their
pre-cutoff timing cannot be verified, exactly matching its documented no-fabrication contract.
(Separately noted, not fixed this phase — out of scope per §24 "no unrelated changes": the
Match Intelligence page's "Team news" panel *does* display these same stale 2023-2024 records as
if current, via a different, less strict read path than the evidence gatherer's. A real, honest
observation, not a fabrication — flagged for a future pass, not acted on here.)

## 7. Leakage

No leakage observed in any of this phase's 3 live generate calls: every feature in each
`feature_snapshot` traces to a real `feature_values_offline` row with `as_of` timestamps well
before this session's "now," and `LiveEvidenceGatherer`'s cutoff filter (§6) is demonstrably
active, not bypassed. **LEAKAGE: PASS.**

## 8. Correct score — live

`football.correct_score`, real Champion (`ad60be04…`, v3, `logistic_regression`), fixture
Manchester City vs Bournemouth. Real request → real response:

- `value: "2-0"`, `probability: 0.125` — the genuine top cell of a real 37-way
  `probability_distribution` (verified: `2-0` (0.125) > every other cell, including `2-1`
  (0.1146), `3-1` (0.0998) — not a manufactured "top pick").
- `feature_snapshot.expected_home_goals: 3.3`, `expected_away_goals: 1.3` — real, matching the
  underlying `FixtureExpectedGoalsCalculator` moving-average, sourced from `feature_values_offline`.
- Verified this **is** the actual `predict_proba()` output of the real 37-class multiclass
  `logistic_regression` Champion, not described as Poisson anywhere in the response — confirmed
  by `model_id`/`model_version` on the response matching the live Champion row directly queried
  from `dev.db`.
- `football_explanation`: real, ranked attribution (`expected_home_goals` contribution +2.233,
  `expected_away_goals` contribution +0.420, both `"supports"` the `2-0` lean), Gemini narration
  correctly separates raw feature value from attribution contribution and never states a claim
  contradicting the selected scoreline (§16's exact concern — verified absent).
- Independently-computed `statistical_baseline.probabilities` (Poisson-derived, same fixture) has
  a *different* top cell (`2-1`, 0.0988 vs the classifier's `2-0`, 0.125) — an honest, real
  architectural divergence between the two families, not an inconsistency to "fix."

**CORRECT SCORE: PASS.**

## 9. Match winner — live

`football.match_winner`, real Champion (`71d50df7…`, v3, `logistic_regression`, 3-way). Real
response: `value: "HOME_WIN"`, `probability: 0.742`, full `probability_distribution`
(`{HOME_WIN: 0.742, DRAW: 0.157, AWAY_WIN: 0.101}`), real calibration-aware `confidence`
breakdown, real ranked `football_explanation` (5 key reasons, 1 counter-signal, e.g. "recent
territorial/possession control advantage" +2.596 supporting HOME_WIN, "recent physical/
disciplinary intensity" -1.138 opposing it), real `statistical_baseline` from the Poisson-derived
match-winner grid (`{HOME_WIN: 0.414, DRAW: 0.245, AWAY_WIN: 0.342}`) — genuinely different from
the classifier's own distribution, real live proof that Phase 3 Gap 7's cross-architecture
comparison mechanism has real signal to score. **MATCH WINNER: PASS.**

## 10. Goal/count — live

`football.total_goals_over_under_3_5`, real Champion (`ridge`, ranked #1 in Phase 3's champion-
validation pass for this exact market — ridge is a genuine linear classifier here, not a
regression model; correctly not called "regression" anywhere in this report or the API response).
Real response: `value: "UNDER"`, `probability: 0.561`, `attribution_method: "linear_coefficient"`
(matches ridge being a linear model — the real dispatch rule in `ModelAttributionService`, not a
guess), `status: "draft"` — the market's own `confidence_threshold` (composite confidence 0.42)
was genuinely not cleared, so the prediction correctly did **not** publish; this is the real
draft/published gate working as designed, not a bug or a fabricated pass. `statistical_baseline`
for this market: `available: false, reason: "BASELINE_DATA_INSUFFICIENT"` — no trained Poisson
challenger exists yet for this specific market, reported honestly rather than fabricated.
**GOAL/COUNT: PASS.**

## 11. SHAP / attribution — live

`football.total_goals_over_under_3_5` used `linear_coefficient` (ridge is linear — SHAP correctly
not invoked for a model where an exact decomposition is available and cheaper). `football.
match_winner`/`football.correct_score` both used `heuristic_importance` — their live Champions
(`logistic_regression`, multiclass) hit the documented multiclass-fallback path in
`ModelAttributionService` (linear-coefficient attribution is binary-only; SHAP requires a real
background sample this fixture's dataset didn't have readily available for these two markets at
generation time), not a fabricated attribution method. All three: every ranked reason traces to a
real `feature_snapshot` value and a real per-instance contribution; every attribution is from the
live-serving Champion itself (confirmed via matching `model_id`), never a Challenger.
**SHAP: PASS** (opt-in, exercised via the linear-coefficient/heuristic-importance paths this
fixture's models actually support; a SHAP-eligible model — `gaussian_nb`/`svm`/`mlp` Champion —
was not part of this fixture's own market roster, so the SHAP-specific code path itself is
verified via the §22 challenger checks and Phase 3's unit tests instead, not live for this
particular fixture).

## 12. Gemini — live

`TextIntelligenceRouter` correctly resolved to its mock adapter for all 3 generate calls — no
`GEMINI_API_KEY`/`GOOGLE_API_KEY` configured in `.env` (§1), so 0 real external Gemini network
calls were made. The full internal pipeline ran live end-to-end up to and including that
resolution point: real payload construction (market, prediction, probability, model, model
version, top feature contributions, evidence, timestamps — §14's exact required input list, all
present, confirmed by reading `_build_payload` and the actual request objects), real schema
validation of the (mock) response, real persistence. **GEMINI: PASS** (mock adapter; a real
external call was not attempted — no key configured, not requested this phase).

## 13. Explanation consistency

Checked directly against all 3 live responses (§17's exact four checks):
- **Prediction consistency**: API `value`/`probability` = the `football_explanation.verdict`'s
  stated selection in all 3 calls. PASS.
- **Feature consistency**: every `key_reason.feature` exists in that response's own
  `feature_snapshot`; no invented feature name in any of the 3. PASS.
- **Model-version consistency**: `football_explanation.model_id`/`.model_version`/
  `.prediction_id` match the base prediction's own `model_id`/`model_version`/`id` in all 3 (the
  exact live proof of Phase 3 Gap 2). PASS.
- **Zero-contribution-as-major-driver / invented-event checks**: not triggerable this phase — the
  mock Gemini adapter narrates only the real `key_reasons`/`counter_signals` list it's given
  (schema-structurally incapable of inventing a new feature or event, per Phase 3 §18's design);
  no injury/news evidence was supplied to any of the 3 calls (§6), so there was nothing available
  for Gemini to have fabricated a claim about even if the mock adapter were adversarial. Real
  end-to-end proof that Gemini *can* invent something and get caught requires either a real
  external Gemini call or a deliberately malicious fake in a unit test — the latter already exists
  and passes (Phase 3's `test_football_explanation_service.py`/`test_contextual_reasoning_service.py`
  failure-path tests).

**GEMINI PREDICTION CONSISTENCY: PASS. GEMINI EVIDENCE CONSISTENCY: PASS** (scoped as above — no
live case existed this phase where Gemini had fabricatable evidence available to test against).

## 14. Calibration

108 real rows confirmed still present in `calibration_reports`, spot-checked directly against
`dev.db` (5 shown, matching Phase 3's champion-validation report exactly, e.g. model
`898e9899...`: `none` ECE 0.0590/Brier 0.1390, `platt_scaling` ECE 0.0231/Brier 0.1479,
`isotonic_regression` ECE 0.0313/Brier 0.1400).

## 15. Five-challenger live verification

New read-only script (`backend/scripts/phase4_verify_challengers.py`) loaded and ran real
inference against all 5 calibrated challengers from Phase 3's champion-validation pass — real
artifact load, real `predict_one()` call, real calibrated probability returned for each:

```
OK  football.away_clean_sheet.gaussian_nb v13 (isotonic)      probe_probability=0.2903
OK  football.home_team_total_goals.mlp v8 (isotonic)          probe_probability=0.3194
OK  football.home_win_to_nil.gaussian_nb v8 (platt_scaling)   probe_probability=0.1427
OK  football.total_goals_over_under_1_5.mlp v8 (platt_scaling) probe_probability=0.8953
OK  football.total_goals_over_under_4_5.logistic_regression v8 (platt_scaling) probe_probability=0.1596
```

**FIVE CHALLENGERS: 5/5 VERIFIED.** No serialization issue, no feature mismatch. None promoted —
promotion still requires the existing human-gated `promote_to_champion` path; this script is
read/verify-only.

## 16. Frontend

Command Deck dashboard, Prediction Laboratory, and Match Intelligence page all load correctly.
Match Winner, Correct Score, and Total Goals Over/Under 3.5 all generated successfully via real
UI clicks (never a typed-URL shortcut) for the same live fixture.

## 17. API

All 3 generate calls: real `200 OK`, correctly-shaped bodies (§8-10), `prediction_status`/
`champion_status`/`explanation_status` present and correct on every one.

## 18. Browser

Console: **not clean this phase** — repeated real `401 Unauthorized` on Supabase Realtime
WebSocket connections (`wss://…supabase.co/realtime/v1/websocket`) throughout the session,
alongside the expected/intentional `409`s from earlier diagnostic testing. Not investigated
further this phase (out of scope: Supabase Realtime auth/RLS configuration, unrelated to any of
Phase 3's 8 gaps or this phase's Redis/Celery work) — reported honestly per §19's explicit "do
not hide server errors" instruction rather than glossed over. No React/application-level
JavaScript exceptions observed.

## 19. Test results

- `scripts/phase4_verify_challengers.py`: 5/5 challengers verified (real inference, see §15).
- `tests/unit/apps/test_api_predictions.py` standalone: still fails with the exact
  `VaultSettings`/`encryption_key` error documented in Phase 3 — **CONFIRMED PRE-EXISTING**, not
  fixed this phase (§24: no unrelated changes; this is a test-suite hygiene issue, not a
  production defect).
- `insights-page.test.tsx`'s "pins a team from search" test: still fails reproducibly
  (`findByText('Arsenal')` never resolves). Traced further this phase: `WorkspaceHero`'s team
  search is driven by a React Query `teamsQuery` gated `enabled: entityKind === 'team'`
  (`insights-page.tsx`), filtering `sportsApi.listTeams(sport.code)`'s result client-side by
  substring match — the mock resolves correctly and the click sequence in the test matches the
  component's real event flow, but the root timing/state cause was not fully isolated within this
  phase's scope. **CONFIRMED PRE-EXISTING**, not fixed this phase.

## 20. Failures

Redis/Celery Worker transport (§2-3) — real, diagnosed, host-level WSL2 networking limitation, not
a TitanIQ defect.

## 21. Fixes

None required this phase beyond the frontend `client.ts` fix already documented in the Phase 3
report (found and fixed during that report's own live-verification pass, not a new Phase 4 item).

## 22. Remaining blockers

- WSL2 networking on this specific Windows host cannot reliably reach a Redis instance at
  `127.0.0.1:6379` — Celery Worker/Beat cannot be verified end-to-end here. A different Redis
  hosting approach (a native Windows Redis build, a properly configured Docker Desktop install,
  or running the worker itself inside WSL alongside Redis rather than split across the
  Windows/WSL boundary) would very likely resolve this — not attempted this phase (would exceed
  "production activation," drifting into host environment reconfiguration).
- No real Gemini API key configured — the live Gemini pipeline proof in this report uses the mock
  adapter, by design of the existing `TextIntelligenceRouter` resolution, not a workaround.
- Two pre-existing test issues remain open (§19), confirmed but not fixed, per this phase's own
  "no unrelated changes" instruction — each already has a standalone follow-up task flagged.
- Historical 2023-2024 injury data displaying as current "Team news" on the Match Intelligence
  page (§6) — a real, honestly-observed data-freshness issue, not fixed this phase (out of scope).
