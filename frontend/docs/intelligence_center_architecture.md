# Football Intelligence Center — Phase A Architecture

Status: Phase A implemented and verified. Phase B (see §8) is scoped but not built.

## Scope

Phase A exposes intelligence TitanIQ's backend already computes but the UI previously discarded
or flattened — no new prediction logic, no frontend-computed probabilities, no new real-time
transport. It extends two existing pages rather than introducing a parallel "Intelligence Center"
hub:

- `pages/sports/match-list-page.tsx` — Discovery/Priority Intelligence for browsing many fixtures.
- `pages/sports/match-detail-page.tsx` — full per-fixture intelligence depth, once a market has
  been generated.

This decision (over a new standalone hub route) was made explicitly to avoid two competing "front
doors" for football — `match-list-page.tsx` already carried Discovery, Live Rail, Trending, and
Recently Completed sections before this phase.

## Page architecture

### Match list / Priority Intelligence (`match-list-page.tsx`)

`TrendingIntelligence` (`components/command-deck/discovery/trending-intelligence.tsx`) — renders
as "Priority intelligence" in the UI. Sourced from `GET /predictions/picks` (`PredictionPickDto[]`,
already confidence-ranked, PUBLISHED-only) plus one fixture lookup per pick
(`GET /sports/fixtures/{id}`). No new backend endpoint.

Every other card-level "intelligence signal" the original brief described (freshness + coverage +
model stability + probability separation + prediction availability, combined into one score) does
not exist in the backend today — see §8, Phase B.

### Match detail (`match-detail-page.tsx` → `GeneratedIntelligencePanel`)

Unchanged structural flow: `PredictionLaboratory` (market picker) → `Generate Intelligence` →
`GeneratedIntelligencePanel` (`components/command-deck/generated-intelligence.tsx`), mounted only
after generation, never as an idle placeholder.

New sections added to the panel, all reading `PredictionDto` fields verbatim:

1. **Expected goals** (`feature_snapshot['football.fixture.expected_home_goals'/'…away_goals']`)
   — shown only when both values are present as numbers. Includes a tooltip clarifying expected
   goals are a modeled rate, not an exact-score guarantee.
2. **Score distribution matrix** — replaces the flat "Alternative outcomes" list specifically when
   `probability_distribution`'s keys are score-shaped (`\d+-\d+` plus optionally `OTHER`, detected
   by `parseScoreGrid`, ≥4 real score keys required so a coincidental single score-like key on
   some other market is never misread as a grid). Every cell's probability and the selected-cell
   highlight come straight from `probability_distribution` — the matrix never computes a
   probability itself, only lays real ones out on two axes. An explanatory sentence appears only
   when the selected scoreline's goal counts differ from the rounded expected-goals values.
3. **Model Intelligence** — the panel footer now reads `prediction.model_algorithm ??
   prediction.model_framework` (humanized via `humanizeModelAlgorithm`) instead of a bare version
   number. Same humanization applied to `contextual_review.statistical_baseline.algorithm` (was
   rendering the raw backend value, e.g. `"via poisson_goals_model"`).

Everything else on this panel — key reasons/counter-signals with real contributions, the
`model_driver`/`context_only` classification (`FootballExplanationDto.context[].role`), the
Contextual Review section (statistical baseline, supporting/risk factors, missing-context list,
assessment confidence kept visually distinct from outcome probability) — was already built in an
earlier phase and is unchanged by this one.

## Backend change

`apps/api/routers/prediction_router.py` — `PredictionDto` gained two additive fields:

```
model_algorithm: string | null
model_framework: string | null
```

Resolved via `_resolve_model_metadata()`, a plain `SqlAlchemyModelRepository.get(prediction.model_id)`
lookup — never re-resolves Champion, never re-runs model selection. Degrades to `(null, null)` on
any failure (including model lookup errors) so this display-only concern can never block or corrupt
a prediction response that already succeeded. Applied at all three `_serialize_prediction` call
sites (`generate`, `get_prediction`, `list_predictions_for_market`); the list endpoint dedupes the
lookup per distinct `model_id` rather than doing one lookup per row.

No other backend change. No training/Champion-selection logic touched.

## Contracts

### Probability vs. confidence vs. context coverage

Enforced as three separate, separately-labeled values everywhere they co-occur — this was already
a `PRODUCT.md` rule before this phase, but the "Priority intelligence" card was found to violate it
(showed only `confidence_composite` as a bare percentage, with the actual predicted outcome/
probability never displayed at all) and was fixed as part of this work:

- **Probability** — `prediction.probability` / `pick.probability`, labeled "probability," always
  paired with the real outcome (`resolveVerdict`), never shown as a bare percentage alone.
- **Confidence** — `confidence.composite`, labeled "Confidence," never "Intelligence Signal" (that
  name is reserved for the Phase B score below).
- **Context coverage** — `missing_context` (binary per-category presence), rendered as "No verified
  evidence yet for: X, Y" — never a fabricated fine-grained percentage.

### Model architecture labeling

`humanizeModelAlgorithm` (`components/infinity/evidence-explorer.tsx`) maps the real, closed
`MLAlgorithm` vocabulary (`backend/modules/predictions/domain/ml_value_objects.py`) to a display
name (e.g. `poisson_goals_model` → "Poisson Goal Distribution", `xgboost_gbm` → "XGBoost
Classifier"). An algorithm value outside that map falls back to a plain title-cased read of the raw
string, never a guess and never inferred from the market name.

### Expected goals vs. exact score

Expected goals and the selected scoreline are always rendered as visually distinct sections; the
score-matrix caption only claims "expected goals ≠ exact score" when the selected scoreline's goal
counts actually diverge from the rounded expected values, never unconditionally.

## Error and insufficient-data states

Unchanged from the existing panel: a 409 (`MISSING_REQUIRED_FEATURE`/insufficient history) renders
"Not enough verified history yet" with the real backend message, never a fabricated prediction. A
`contextual_review.review_status === 'INSUFFICIENT_CONTEXT'` renders "Contextual analysis
unavailable" and lists only the real missing categories — the Statistical Baseline sub-section
(and its own algorithm label) only renders once contextual review has real content, which is why it
won't appear on every generation (Gemini has no verified pre-cutoff evidence for most fixtures in
this dev environment).

## Responsive behavior

The score matrix scrolls horizontally on narrow viewports (`overflow-x-auto` wrapper) rather than
shrinking cells below a legible size; every other new section reuses the panel's existing
single-column mobile layout.

## Verification performed

- `tsc --noEmit` clean (frontend).
- New unit tests: `generated-intelligence.test.ts` (`parseScoreGrid` — real grid detection, false-
  positive rejection, honest zero-mass reporting) and `evidence-explorer.test.ts`
  (`humanizeModelAlgorithm`, `resolveVerdict`/`resolveOutcomeLabel` regression coverage) — 10/10
  passing.
- Backend: full `pytest tests/unit` suite re-run after the `prediction_router.py` change.
- Live-verified in-browser: Priority Intelligence card shows real verdict + probability + confidence
  + evidence count, separately labeled; Correct Score generation on a real fixture renders a real
  6×6 heatmap-shaded matrix with the selected cell highlighted, real Expected Goals, and
  "Logistic Regression v3" (previously a bare "Model v3") in the footer.

## Known gaps — Phase B (not built)

Named explicitly rather than silently faked, per the approved Phase A brief:

- **Intelligence Signal score** — no composite backend score exists combining freshness, context
  coverage, model stability, probability separation, and prediction availability. "Priority
  intelligence" ranks by the real `confidence.composite` today, labeled honestly as "Confidence."
- **Per-fixture Intelligence Feed** — no probability-change history is persisted anywhere in the
  backend; a real feed needs a new persisted concept before any UI for it would be honest.
- **Expanded Model Intelligence metadata** — training-window date range, test/validation sample
  count, and a stability rating don't exist on `ModelDefinition` today.
- **True live in-play events** — no pipeline exists beyond periodic fixture score sync;
  `FixtureStatus.LIVE` and score updates are real, minute-by-minute events are not.
