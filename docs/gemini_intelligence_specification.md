# TitanIQ — Gemini Intelligence Specification

**Status**: Live, and deliberately honest about scope. Gemini's real role in this codebase is
**narration of an already-computed prediction, never scoring** — this document specifies exactly
what goes in, what comes out today, and is explicit about the gap between that and a fuller
structured-explanation vision, rather than describing aspirational behavior as if it were real.

## The one invariant that governs everything below

**Gemini explains. Models predict.** This is enforced by construction, not just by convention:
`GeminiAdapter.explain()` is called from `ExplainabilityEngine`, strictly *after*
`PredictionEngine.generate()` has already produced a calibrated `probability`/`value` from the
model or formula predictor (§ [`ai_intelligence_flow.md`](ai_intelligence_flow.md)). There is no
code path where a Gemini response feeds back into the probability, the predicted label, or the
confidence score. If this invariant is ever broken, it should be treated as a severity-1 defect,
not a feature.

## Real call site

`modules/intelligence/infrastructure/gemini_adapter.py::GeminiAdapter.explain()` — calls the
Gemini REST API directly (`generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`),
invoked from `modules/predictions/application/explainability_engine.py::ExplainabilityEngine.explain()`.

## Real input

A context dictionary built from data that already exists on the `Prediction`/`ExplanationBundle`
by the time Gemini is called:

- The prediction itself: probability, predicted value/label.
- `feature_contributions` → ranked into `top_positive_features`/`top_negative_features` (computed
  independently of Gemini, by ranking real SHAP or formula-weight contributions).
- Knowledge Graph evidence, news contribution, community contribution (already-retrieved context,
  not fetched by Gemini itself).

## Real prompt

`GeminiAdapter.explain()` uses a **hardcoded prompt string**: *"Explain this sports prediction to
a knowledgeable fan in 2-3 sentences... Supporting data (JSON): {context}"* — a single fixed
template, not configurable per market today.

**Known gap**: `MarketDefinition.gemini_prompt_template` is a real, persisted field (a `Text`
column on `prediction_markets`, settable through the Market Registry API — see
[`database_schema.md`](database_schema.md)) that exists specifically to let a market customize its
own explanation prompt. **It is never read.** An admin can set it via the API today and it will be
silently ignored. This is dead data, not a bug in the sense of crashing anything, but it's a
real, closeable gap: either wire `GeminiAdapter.explain()` to read and use it per-market, or remove
the field so it stops implying a capability that doesn't exist.

## Real output

A **single flat narrative string**, assigned to `ExplanationBundle.ai_explanation: str`. That's
the entire Gemini-authored surface area of a prediction response today.

### What the "structured breakdown" vision maps to in real fields (approximated, not Gemini-authored)

| Vision concept | Real equivalent today | Authored by |
|---|---|---|
| Executive Summary | `ai_explanation` (the one Gemini string) | Gemini |
| Reasoning | `ai_explanation` (same string covers this) | Gemini |
| Supporting Factors | `top_positive_features` | Computed ranking, not Gemini |
| Risk Factors | `top_negative_features` | Computed ranking, not Gemini |
| Alternative Outcomes | `probability_distribution` on `Prediction` | Computed by the predictor, not Gemini |
| Confidence Explanation | `ConfidenceBreakdown`'s 9 named factors | Computed by `ConfidenceEngine`, not Gemini |

None of these are separate Gemini output fields — they're independently-computed pieces of the
response that a frontend can present *alongside* the one Gemini sentence to approximate the fuller
picture, without Gemini itself having produced a structured object. Building a genuinely
structured Gemini response (six distinct generated fields instead of one) is real, scoped future
work, not something this document should describe as already shipped.

## Explicit non-goals (by design, not by omission)

- Gemini never sees or influences the raw feature vector before prediction — it only receives
  already-computed outputs.
- Gemini output is never persisted as ground truth for anything (no training label, no calibration
  input) — `CalibrationFittingService` (§ [`calibration.md`](calibration.md)) fits exclusively on
  real `(probability, actual_outcome)` pairs, never on Gemini text.
- There is no retry/fallback chain to a second LLM provider today — a Gemini call failure means
  `ai_explanation` is absent from that response, not a fabricated placeholder string.

## What this document does not cover

The full request pipeline this fits into → [`ai_intelligence_flow.md`](ai_intelligence_flow.md).
SHAP (the actually-structured, non-LLM explanation layer) → [`machine_learning.md`](machine_learning.md).
Confidence factor definitions → [`prediction_engine.md`](prediction_engine.md).
