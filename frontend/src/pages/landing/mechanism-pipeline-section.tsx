import { Database, Cpu, BrainCircuit, LineChart, Gauge, ShieldCheck, Sparkles, FileText } from 'lucide-react'
import { Section } from './section-primitives'

// The real, backend-verified pipeline behind every published prediction (Feature Store,
// Model Registry, SHAP-based feature attribution, live news/injury/lineup/transfer ingestion,
// GeminiAdapter narration) — a process description, not a per-card data feed, so it needs no
// loading/empty state. Deliberately more granular than the "How It Works" section further up
// the page: this is the technical proof moment, that one is the plain-language recap.
const STAGES = [
  { icon: Database, title: 'Historical Data', detail: 'Fixtures, results, and statistics synced from real providers per sport.' },
  { icon: Cpu, title: 'Feature Engineering', detail: 'Form, rates, and matchup signals computed from that history.' },
  { icon: BrainCircuit, title: 'Statistical / ML Model', detail: 'A trained model per market produces a calibrated probability.' },
  { icon: LineChart, title: 'Model Output', detail: 'A prediction with its own probability and composite confidence score.' },
  { icon: Gauge, title: 'Feature Attribution', detail: 'SHAP-based scoring ranks exactly which features moved the number.' },
  { icon: ShieldCheck, title: 'Verified Context', detail: 'Injuries, lineups, transfers, and news are checked against the fixture.' },
  { icon: Sparkles, title: 'Gemini Sports Analysis', detail: "The evidence is narrated in plain language — never a free-form guess." },
  { icon: FileText, title: 'Explained Prediction', detail: 'What ships: a number, its confidence, and the reasoning behind both.' },
]

const HALF = Math.ceil(STAGES.length / 2)
const COLUMNS = [STAGES.slice(0, HALF), STAGES.slice(HALF)]

function TimelineColumn({ stages, startIndex }: { stages: typeof STAGES; startIndex: number }) {
  return (
    <div className="relative">
      <div className="absolute top-1 bottom-1 left-[15px] w-px bg-[var(--li-border)]" aria-hidden="true" />
      <div className="space-y-7">
        {stages.map((stage, i) => (
          <div key={stage.title} className="relative flex gap-5">
            <span className="relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full border border-[var(--li-border)] bg-[var(--li-surface)] text-[var(--li-cyan)]">
              <stage.icon className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <p className="font-mono text-[10px] uppercase tracking-wider text-[var(--li-text-muted)]">
                Stage {String(startIndex + i + 1).padStart(2, '0')}
              </p>
              <p className="mt-0.5 text-sm font-semibold text-[var(--li-text-primary)]">{stage.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-[var(--li-text-secondary)]">{stage.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function MechanismPipelineSection() {
  return (
    <Section className="border-b border-[var(--li-border)]">
      <h2 className="max-w-xl text-2xl font-bold tracking-tight text-[var(--li-text-primary)] lg:text-3xl">
        How a real card above became a real published prediction
      </h2>

      <div className="mt-10 grid gap-x-12 gap-y-7 lg:grid-cols-2">
        {COLUMNS.map((stages, i) => (
          <TimelineColumn key={i} stages={stages} startIndex={i * HALF} />
        ))}
      </div>
    </Section>
  )
}
