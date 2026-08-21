import { ArrowRight } from 'lucide-react'
import { Section, SectionHeading } from './section-primitives'

const PIPELINE = [
  { title: 'Data', detail: 'Fixtures, results, stats, and odds are synced from real providers per sport.' },
  { title: 'Context', detail: 'The Knowledge Graph and Feature Store attach form, relationships, and news impact.' },
  { title: 'Intelligence', detail: 'A trained model per market produces a calibrated probability and confidence score.' },
  { title: 'Explanation', detail: 'Every output ships with its top supporting and contradicting evidence, never a bare number.' },
  { title: 'Learning', detail: 'Settled results feed back into retraining — see Continuous Learning below.' },
]

/**
 * "How TitanIQ Works" — the shape brief's Data → Context → Intelligence → Explanation → Learning
 * thesis, spelled out as the real pipeline stages (docs/architecture.md, docs/prediction_engine.md).
 * A process description, not a data feed — nothing here is a metric that could go stale or be
 * fabricated, so it needs no loading/empty state.
 */
export function HowItWorksSection() {
  return (
    <Section className="border-b border-border-subtle">
      <SectionHeading
        eyebrow="How TitanIQ Works"
        title="From raw data to an explainable output"
        description="The same five stages run for every sport, every market, every prediction — nothing skips a step."
      />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-stretch lg:gap-2">
        {PIPELINE.map((step, i) => (
          <div key={step.title} className="flex flex-col items-stretch gap-2 lg:flex-1 lg:flex-row lg:items-center lg:gap-0">
            <div className="flex-1 self-stretch rounded-lg border border-border-default bg-bg-elevated p-4">
              <p className="font-telemetry text-xs text-text-muted">Stage {i + 1}</p>
              <p className="mt-1 font-display text-sm font-semibold text-text-primary">{step.title}</p>
              <p className="mt-1.5 text-xs text-text-secondary">{step.detail}</p>
            </div>
            {i < PIPELINE.length - 1 && (
              <ArrowRight className="mx-auto size-4 shrink-0 rotate-90 text-text-muted lg:mx-2 lg:my-0 lg:rotate-0" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>
    </Section>
  )
}
