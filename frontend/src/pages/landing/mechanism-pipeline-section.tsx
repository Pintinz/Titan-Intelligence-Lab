import { Section } from './section-primitives'

// The real, backend-verified pipeline behind every published prediction (Feature Store,
// Model Registry, SHAP-based feature attribution, live news/injury/lineup/transfer ingestion,
// GeminiAdapter narration) — a process description, not a per-card data feed, so it needs no
// loading/empty state. Deliberately more granular than the "How It Works" section further down
// the page: this is the technical proof moment, that one is the plain-language recap.
const STAGES = [
  { title: 'Historical Data', detail: 'Fixtures, results, and statistics synced from real providers per sport.' },
  { title: 'Feature Engineering', detail: 'Form, rates, and matchup signals computed from that history.' },
  { title: 'Statistical / ML Model', detail: 'A trained model per market produces a calibrated probability.' },
  { title: 'Model Output', detail: 'A prediction with its own probability and composite confidence score.' },
  { title: 'Feature Attribution', detail: 'SHAP-based scoring ranks exactly which features moved the number.' },
  { title: 'Verified Context', detail: 'Injuries, lineups, transfers, and news are checked against the fixture.' },
  { title: 'Gemini Sports Analysis', detail: "The evidence is narrated in plain language — never a free-form guess." },
  { title: 'Explained Prediction', detail: 'What ships: a number, its confidence, and the reasoning behind both.' },
]

export function MechanismPipelineSection() {
  return (
    <Section className="border-b border-border-subtle bg-bg-secondary/40">
      <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
        The mechanism
      </p>
      <h2 className="mt-2 max-w-xl font-display text-2xl font-semibold tracking-tight text-text-primary lg:text-3xl">
        How a real card above became a real published prediction
      </h2>

      <ol className="mt-10 space-y-0">
        {STAGES.map((stage, i) => (
          <li key={stage.title} className="flex gap-5 border-l-2 border-border-default py-4 pl-6 last:pb-0">
            <span
              className="relative -ml-[calc(1.5rem+2px)] flex size-8 shrink-0 items-center justify-center rounded-full border-2 border-accent-primary bg-bg-primary font-telemetry text-xs font-semibold text-accent-primary"
              aria-hidden="true"
            >
              {i + 1}
            </span>
            <div className="pt-0.5">
              <p className="font-display text-sm font-semibold text-text-primary">{stage.title}</p>
              <p className="mt-1 text-sm text-text-secondary">{stage.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </Section>
  )
}
