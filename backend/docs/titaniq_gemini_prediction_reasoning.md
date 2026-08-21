# TitanIQ Gemini Prediction Reasoning & Evidence Engine

## 1. Purpose and architecture

TitanIQ's existing prediction pipeline is: Historical Data → Rolling Features → Champion ML
model (or, where a real statistical family applies, a Poisson baseline) → Base Prediction
(`Prediction.probability`/`value`/`probability_distribution`). That pipeline is authoritative and
unchanged by this feature.

This feature adds a second, independent read on top of that base prediction: a structured Gemini
assessment of whether currently-available, verified pre-cutoff evidence (news, injuries,
transfers, lineups) supports, weakens, or doesn't materially change the base prediction. It is
strictly additive:

- Gemini never outputs a replacement probability. The base prediction's `probability`/`value`
  remain the only authoritative outcome numbers TitanIQ publishes.
- A failure anywhere in this feature (baseline lookup, evidence gathering, cache, Gemini call,
  schema validation) degrades to an honest `INSUFFICIENT_CONTEXT` result and never raises — the
  base prediction response is never put at risk.
- The feature is fully opt-in at the API layer (`include_contextual_review: false` by default) —
  every existing caller of `POST /api/v1/predictions/generate` is unaffected.

```
Prediction (base, unchanged)
        │
        ├── StatisticalBaselineProvider ──> live Poisson baseline (football goals/score markets only)
        ├── LiveEvidenceGatherer ─────────> verified pre-cutoff news/injuries/transfers/lineups
        │
        ▼
ContextualReasoningService.review()
        │
        ├── cache check (Redis, keyed on prediction + evidence hash)
        ├── Gemini call via TextIntelligenceRouter (real/mock, same resolution as ai_explanation)
        ├── GeminiReasoningResponseSchema validation (Pydantic, extra="forbid")
        │
        ▼
ContextualReview  ──>  prediction_context_reviews table  ──>  API `contextual_review` field
```

## 2. Statistical baseline layer

`StatisticalBaselineProvider` (`modules/predictions/application/statistical_baseline_provider.py`)
answers, for a given market and the fixture's already-resolved feature snapshot, whether a real
live statistical baseline exists — never fabricated, never inferred.

- **Directly-eligible markets** (`POISSON_ELIGIBLE_MARKETS` in
  `scheduled_retraining_orchestrator.py`, 12 football goals/score markets: total/team-total
  goals over/under at 4 line variants, `correct_score`, home/away clean sheet, home/away
  win-to-nil): looks up a `poisson_goals_model` model row for the market via
  `ModelRepositoryPort.get_by_market_and_algorithm`. If found, loads it through
  `ModelLoaderService` (fixed in this feature — it previously had no `MLFramework.POISSON_GOALS`
  branch and raised `UnknownModelFrameworkError`) and calls `.predict_one(features)`.
- **Derived markets** (`football.match_winner`, `football.both_teams_to_score`): reuse the
  already-fitted `football.correct_score` Poisson model's `lam_home`/`lam_away` regressors for
  this fixture (via `FootballGoalsPoissonAdapter.predict_lambdas()`) and derive match-winner /
  BTTS probabilities through direct score-grid summation (`domain/poisson_score_grid.py`) — no
  new model, no new training, standard Poisson football math.
- **Every other market**: `applicable=False` — the statistical-baseline family doesn't apply and
  this is never masked as "unavailable data" (a different, distinct state:
  `applicable=True, available=False`).

**Real, verified state of `dev.db` at the time of writing** (queried directly, not assumed): only
3 of the 12 directly-eligible markets have ever had a `poisson_goals_model` row trained and
registered — `football.correct_score`, `football.home_clean_sheet`,
`football.total_goals_over_under` — and all three sit at `challenger` status; Poisson has never
won the Champion race for any football market in this dataset. The other 9 eligible markets have
no Poisson row yet. `StatisticalBaselineProvider` reports this honestly per-market
(`available=False, reason="BASELINE_DATA_INSUFFICIENT"` or similar) rather than fabricating a
result — this is not a bug in the provider, it reflects the real training history.

## 3. Evidence gathering and the cutoff rule

`LiveEvidenceGatherer` (`modules/predictions/application/live_evidence_gatherer.py`) collects
context per sport-appropriate category (`domain/context_categories.py` —
`SPORT_CONTEXT_CATEGORIES`, deliberately conservative: a category only appears if TitanIQ has a
real repository for it today) by reusing the exact repositories `ExplainabilityEngine`/
`EntityReconciliationService` already depend on — no new provider, no new fetch path.

The absolute cutoff rule, reusing Milestone 5's existing provenance mechanism unchanged: every
`NewsEvent`/`Injury`/`Transfer`/`Lineup` already carries `information_available_at` and
`availability_classification` (`VERIFIED_PRE_MATCH` | `VERIFIED_POST_MATCH` |
`UNKNOWN_AVAILABILITY_TIME`, never auto-classified). An item is accepted only if:

1. It is `VERIFIED_PRE_MATCH` (news additionally requires `NewsEvent.is_feature_eligible()` —
   every affected entity resolved, not just the timestamp verified), **and**
2. `information_available_at` is set and `<= prediction_cutoff`.

Anything else is rejected — including an item with a plausible-looking but unverified timestamp,
and including a missing `information_available_at` (never silently treated as "available now").
Rejection reasons are counted (`GatheredEvidence.rejection_reasons`), and an empty category is
reported as `missing_context`, never fabricated as "confirmed nothing happened."

`prediction_cutoff` defaults to the review's own `now` for a live request — the honest default
stated by the API's intent, not a fabricated timestamp.

## 4. Gemini contract

`TITANIQ_GEMINI_REASONING_V1` (prompt constant in
`modules/intelligence/infrastructure/gemini_adapter.py`) instructs Gemini explicitly:

- It is not the primary model; the base prediction and (where present) statistical baseline are
  both already authoritative — never output a replacement probability or an `official_probability`
  field.
- Evaluate only the evidence supplied in the payload; never use outside knowledge, even about
  well-known teams/players.
- Never use anything dated after `prediction_cutoff` — every item has already been filtered, so an
  empty category means genuinely unknown, not "nothing happened."
- Never fabricate sources, injuries, transfers, lineups, news, or statistics; cite only the
  `source_id` values supplied.
- Return one JSON object matching the schema — no prose, no markdown fences.

`GeminiReasoningResponseSchema` (`modules/predictions/infrastructure/gemini_reasoning_schema.py`)
is the first Pydantic validation of any LLM output in this codebase. Every nested model uses
`ConfigDict(extra="forbid")` — a hallucinated extra field (the exact `official_probability`
failure mode the prompt prohibits) fails validation outright rather than silently passing through.
On a schema-invalid or non-JSON response, `ContextualReasoningService` retries once with the
validation error appended to the payload; if the retry also fails, the review degrades to
`INSUFFICIENT_CONTEXT` — it never raises.

`MockGeminiAdapter.assess_prediction_context()` provides the deterministic mock path (used
whenever no credentialed Gemini provider is configured, via the same `TextIntelligenceRouter`
real/mock resolution every other Gemini-backed feature already uses): zero accepted evidence →
`INSUFFICIENT_CONTEXT`; real evidence present → a `NEUTRAL` read reporting counts only — the mock
never claims a directional judgment it has no way to make honestly.

## 5. Confidence semantics — read this before wiring anything to `probability`

`ContextualReview.confidence_score`/`confidence_level` are Gemini's confidence **in this
contextual assessment itself** — never an outcome probability, and never rendered next to or
instead of `Prediction.probability`. The frontend (`ContextualReviewPanel`) labels this
explicitly ("Assessment confidence") and keeps it visually and structurally separate from the base
prediction's own confidence gauge.

## 6. Persistence

New table `prediction_context_reviews` (migration `alembic/versions/0043_gemini_contextual_review.py`,
applied to `dev.db` via `backend/scripts/init_local_sqlite_db.py` — the SQLite dev path, since real
Alembic CLI cannot run Postgres-flavored multi-schema DDL against SQLite). Unique on
`prediction_id`: `record()` overwrites the existing row for a prediction rather than accumulating a
growing history (unlike `PredictionAuditModel`) — a fresh review supersedes the prior one for the
same prediction. `SqlAlchemyContextReviewRepository` (`infrastructure/persistence/repositories.py`)
+ `context_review_mapper.py` handle serialize/deserialize, including flattening every nested enum
to its `.value` for JSON storage.

## 7. Cache

`ContextualReasoningService` checks `SyncCachePort` (the existing generic Redis-backed cache port,
`get_redis_sync_cache()`) before calling Gemini, keyed on
`gemini_reasoning:{subject_ref}:{market_key}:{model_version}:{context_hash}:{cutoff.isoformat()}`,
TTL 6 hours. `context_hash` is a stable hash of the accepted evidence's own `source_id`s — a
genuinely new accepted item (fresh injury, fresh confirmed lineup) changes the hash and forces a
fresh Gemini call rather than serving a stale cached read. A cache backend failure (unreachable
Redis, missing `TITANIQ_REDIS_URL`) degrades to "always miss" — it is never treated as an error.

## 8. Failure behavior (absolute rule, enforced at every layer)

| Failure | Result |
|---|---|
| Baseline lookup raises | `StatisticalBaseline(applicable=False, available=False)` |
| Evidence gathering raises | Empty `GatheredEvidence()` — every category reported missing |
| Cache read/write raises | Treated as a miss / write silently dropped |
| Gemini call raises (network, quota, bad key) | Falls back through `TextIntelligenceRouter` to the mock adapter, same as `ai_explanation` |
| Gemini returns non-JSON or schema-invalid JSON | One retry with the validation error appended; still-invalid → `INSUFFICIENT_CONTEXT` |
| Persistence (`record()`) raises | Review is still returned to the caller; only the DB write is lost |
| Anything else unexpected | The router-level `try/except` around the whole review call in `prediction_router.py` sets `contextual_review = None`; the base prediction response is unaffected |

The base prediction is generated and committed **before** any contextual-reasoning code runs.

## 9. Leakage protection

- The cutoff rule (§3) is the primary guard — a post-cutoff item is rejected before it ever
  reaches the evidence payload Gemini sees.
- The prompt (§4) explicitly forbids using knowledge outside the supplied payload.
- `test_live_evidence_gatherer.py` includes an explicit rejection test for a future-timestamped
  item and for an item with `UNKNOWN_AVAILABILITY_TIME`/no `information_available_at` at all —
  covering both "obviously too late" and "plausible-looking but unverified."

## 10. API

`POST /api/v1/predictions/generate` — new optional field, default `False`:

```json
{ "market_key": "...", "entity_type": "fixture", "entity_id": "...", "subject_ref": "...",
  "include_contextual_review": true }
```

`_serialize_prediction()` gains one new key, `contextual_review`, always present (additive to
every existing key) and `null` unless the flag was `true` **and** the review pipeline produced a
result:

```json
{
  "review_status": "SUPPORTED | WEAKLY_SUPPORTED | NEUTRAL | CHALLENGED | STRONGLY_CHALLENGED | INSUFFICIENT_CONTEXT",
  "overall_assessment": "...",
  "confidence_level": "VERY_LOW | LOW | MEDIUM | HIGH | VERY_HIGH",
  "confidence_score": 0.0,
  "statistical_baseline": { "applicable": false, "available": false, "algorithm": null, "probabilities": null, "reason": null },
  "contextual_assessment": { "lineups": { "impact": "POSITIVE", "strength": "MEDIUM", "score": 0.6, "reason": "..." } },
  "supporting_factors": [ { "factor": "...", "impact": "...", "strength": "...", "evidence": "...", "source_ids": ["..."] } ],
  "risk_factors": [ ],
  "missing_context": ["news"],
  "reconsideration": { "direction": "SUPPORTS_BASE_PREDICTION", "material_change": false, "reason": "..." },
  "evidence_quality": { "overall": "MEDIUM", "source_count": 1, "timestamp_valid": true, "pre_event_only": true, "conflicting_information": false },
  "source_ids": ["..."],
  "prediction_cutoff": "2026-08-18T00:00:00+00:00",
  "prompt_version": "TITANIQ_GEMINI_REASONING_V1",
  "generated_at": "2026-08-18T00:00:00+00:00"
}
```

## 11. Frontend

- `ContextualReviewDto` (`frontend/src/lib/api/types.ts`) mirrors the shape above.
- `ContextualReviewPanel` (`frontend/src/components/domain/contextual-review-panel.tsx`), composed
  into `PredictionPanel` — renders nothing when `contextual_review` is `null`. Shows: review-status
  badge + assessment, the statistical baseline (when applicable), per-category impact, supporting
  and risk factors, missing-context categories, and a footer with "Assessment confidence" kept
  visually distinct from the base prediction's own confidence gauge above it.
- Wired opt-in (`include_contextual_review: true`) at the one page built specifically as a
  prediction-generation workbench, Prediction Laboratory (`prediction-lab-page.tsx`) — every other
  caller of `predictionsApi.generate` is unaffected and keeps its existing zero-latency-change
  behavior.

## 12. Test coverage

- `test_gemini_reasoning_schema.py` — valid/missing-field/invalid-enum/hallucinated-field(rejected)
  /capped-list/insufficient-context-still-valid.
- `test_live_evidence_gatherer.py` — cutoff acceptance/rejection, unverified-classification
  rejection, missing-timestamp rejection, per-sport category honesty (basketball never claims
  transfers/lineups), non-UUID `subject_ref` degrades to missing rather than raising.
- `test_contextual_reasoning_service.py` — full orchestration: valid response → persisted review;
  Gemini-unavailable/malformed-JSON/schema-violating → `INSUFFICIENT_CONTEXT`; retry-then-succeed;
  every individual dependency failure (baseline, evidence, cache, persistence) isolated and shown
  not to break the review; cache hit avoids a second Gemini call; a genuinely different evidence
  set invalidates the cache; never raises even when every dependency fails simultaneously.
- `test_gemini_adapter.py` / `test_mock_gemini_adapter.py` / `test_text_intelligence_router.py` —
  `assess_prediction_context()` passthrough, request-body shape, mock's insufficient/neutral
  branches, real/mock resolution reused for the new method.
- `test_api_predictions.py` — `contextual_review: null` by default (backward compatibility);
  `include_contextual_review: true` returns a fully-shaped review; a hard failure inside the
  contextual-reasoning wiring still returns the base prediction with `contextual_review: null`.
- Full backend suite (`pytest backend/tests/unit`) — **2619 passed, 0 failed** — confirms no
  regression to any existing module.

## 13. Known limitations (stated honestly)

- Only 3 of the 12 Poisson-eligible football markets currently have a trained baseline model, and
  Poisson has not won any Champion race in this dataset to date (see §2) — this is real training
  history, not a defect in the wiring.
- No dedicated circuit breaker exists for repeated Gemini failures; the existing
  real→mock fallback in `TextIntelligenceRouter` is the only resilience layer, matching every
  other Gemini-backed feature in this codebase.
- Non-football sports get an honest `applicable=False` statistical baseline for every market —
  no Poisson-equivalent baseline exists for basketball/baseball/table_tennis today.
- `include_contextual_review` is wired into exactly one frontend call site (Prediction
  Laboratory); other prediction-generation call sites (e.g. `match-detail-page.tsx`'s Command Deck
  flow) were intentionally left unchanged, per the approved plan's scope boundary against modifying
  unrelated prediction architecture.
