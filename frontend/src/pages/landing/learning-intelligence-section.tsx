import { ArrowRight } from 'lucide-react'
import { Section, SectionHeading } from './section-primitives'
import { LEARNING_STEPS } from './sample-data'

export function LearningIntelligenceSection() {
  return (
    <Section className="border-b border-border-subtle bg-bg-secondary/40">
      <SectionHeading
        eyebrow="Learning Intelligence"
        title="TitanIQ gets smarter after every match"
        description="Nothing here is hidden — this is the real pipeline that runs after every settled result, not a marketing diagram."
      />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-stretch lg:gap-2">
        {LEARNING_STEPS.map((step, i) => (
          <div key={step.title} className="flex items-center gap-2 lg:flex-1 lg:flex-col lg:items-stretch lg:gap-0">
            <div className="flex-1 rounded-lg border border-border-default bg-bg-elevated p-4">
              <p className="font-telemetry text-xs text-text-muted">Step {i + 1}</p>
              <p className="mt-1 font-display text-sm font-semibold text-text-primary">{step.title}</p>
              <p className="mt-1.5 text-xs text-text-secondary">{step.detail}</p>
            </div>
            {i < LEARNING_STEPS.length - 1 && (
              <ArrowRight
                className="size-4 shrink-0 text-text-muted lg:mx-auto lg:my-2 lg:rotate-90"
                aria-hidden="true"
              />
            )}
          </div>
        ))}
      </div>
      <p className="mt-6 text-sm text-text-secondary">
        The result: future predictions improve — not by chance, but by a measured, monitored loop.
      </p>
    </Section>
  )
}
