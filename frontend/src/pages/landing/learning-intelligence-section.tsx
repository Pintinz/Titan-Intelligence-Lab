import { ArrowRight } from 'lucide-react'
import { Section, SectionHeading } from './section-primitives'

// Real retraining-loop stages (ChallengerEvaluationService, CalibrationFittingService,
// ScheduledRetrainingOrchestrator) — process description, not a data feed to fetch.
const LEARNING_STEPS = [
  { title: 'Prediction Validation', detail: 'Every settled market is compared against the official result.' },
  { title: 'Model Evaluation', detail: 'Champion and challenger models are scored on the same outcome.' },
  { title: 'Learning Report', detail: 'Error signal is attributed back to specific features and markets.' },
  { title: 'Knowledge Graph Update', detail: 'New relationships and context are written back into the graph.' },
  { title: 'Confidence Recalibration', detail: 'Probability calibration is re-fit against the latest outcomes.' },
  { title: 'Retraining Queue', detail: 'Markets crossing a drift threshold are queued for retraining.' },
]

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
          <div key={step.title} className="flex flex-col items-stretch gap-2 lg:flex-1 lg:flex-row lg:items-center lg:gap-0">
            <div className="flex-1 self-stretch rounded-lg border border-border-default bg-bg-elevated p-4">
              <p className="font-telemetry text-xs text-text-muted">Step {i + 1}</p>
              <p className="mt-1 font-display text-sm font-semibold text-text-primary">{step.title}</p>
              <p className="mt-1.5 text-xs text-text-secondary">{step.detail}</p>
            </div>
            {i < LEARNING_STEPS.length - 1 && (
              <ArrowRight
                className="mx-auto size-4 shrink-0 rotate-90 text-text-muted lg:mx-2 lg:my-0 lg:rotate-0"
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
