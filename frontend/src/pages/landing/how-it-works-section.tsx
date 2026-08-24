import { Database, BrainCircuit, LineChart, FileText, ArrowRight } from 'lucide-react'
import { Section, SectionHeading } from './section-primitives'

const STEPS = [
  {
    icon: Database,
    title: 'Collect & Process Data',
    detail: 'Fixtures, results, and statistics are synced from real providers and joined with the Knowledge Graph for context.',
  },
  {
    icon: BrainCircuit,
    title: 'Run Advanced Models',
    detail: 'A trained statistical/ML model per market analyzes the patterns and produces a calibrated probability.',
  },
  {
    icon: LineChart,
    title: 'Generate Predictions',
    detail: 'Every output ships as a probability with a composite confidence score — never a bare guess.',
  },
  {
    icon: FileText,
    title: 'Explain & Deliver',
    detail: 'SHAP-based feature attribution ranks the evidence, and settled results feed back into retraining.',
  },
]

/**
 * "How TitanIQ Works" — the shape brief's Data → Context → Intelligence → Explanation → Learning
 * thesis, consolidated to four real stages (docs/architecture.md, docs/prediction_engine.md). A
 * process description, not a data feed — nothing here is a metric that could go stale or be
 * fabricated, so it needs no loading/empty state.
 */
export function HowItWorksSection() {
  return (
    <Section id="how-it-works" className="border-b border-[var(--li-border)] scroll-mt-20">
      <SectionHeading
        title="From raw data to an explainable output"
        description="The same pipeline runs for every sport, every market, every prediction — nothing skips a step."
      />

      <div className="grid gap-4 lg:grid-cols-4">
        {STEPS.map((step, i) => (
          <div key={step.title} className="relative">
            <div className="h-full rounded-[var(--li-radius-md)] border border-[var(--li-glass-2-border)] bg-[var(--li-glass-2-bg)] p-5 backdrop-blur-[var(--li-glass-2-blur)]">
              <div className="flex items-center gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-[var(--li-radius-sm)] border border-[var(--li-border)] bg-[var(--li-surface-elevated)] text-[var(--li-cyan)]">
                  <step.icon className="size-5" aria-hidden="true" />
                </span>
                <span className="font-mono text-xs font-semibold text-[var(--li-text-muted)]">{String(i + 1).padStart(2, '0')}</span>
              </div>
              <p className="mt-4 text-sm font-semibold text-[var(--li-text-primary)]">{step.title}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-[var(--li-text-secondary)]">{step.detail}</p>
            </div>
            {i < STEPS.length - 1 && (
              <ArrowRight
                className="absolute top-1/2 -right-2 z-10 hidden size-4 -translate-y-1/2 text-[var(--li-text-muted)] lg:block"
                aria-hidden="true"
              />
            )}
          </div>
        ))}
      </div>
    </Section>
  )
}
