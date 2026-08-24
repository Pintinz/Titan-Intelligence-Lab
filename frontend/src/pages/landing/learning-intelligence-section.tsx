import { CircleCheck, Scale, FileBarChart, Network, Gauge, ListRestart, CornerLeftUp } from 'lucide-react'
import { Section } from './section-primitives'

// Real retraining-loop stages (ChallengerEvaluationService, CalibrationFittingService,
// ScheduledRetrainingOrchestrator) — process description, not a data feed to fetch.
const LEARNING_STEPS = [
  { icon: CircleCheck, title: 'Prediction Validation', detail: 'Every settled market is compared against the official result.' },
  { icon: Scale, title: 'Model Evaluation', detail: 'Champion and challenger models are scored on the same outcome.' },
  { icon: FileBarChart, title: 'Learning Report', detail: 'Error signal is attributed back to specific features and markets.' },
  { icon: Network, title: 'Knowledge Graph Update', detail: 'New relationships and context are written back into the graph.' },
  { icon: Gauge, title: 'Confidence Recalibration', detail: 'Probability calibration is re-fit against the latest outcomes.' },
  { icon: ListRestart, title: 'Retraining Queue', detail: 'Markets crossing a drift threshold are queued for retraining.' },
]

export function LearningIntelligenceSection() {
  return (
    <Section className="border-b border-[var(--li-border)]">
      <h2 className="max-w-xl text-2xl font-bold tracking-tight text-[var(--li-text-primary)] lg:text-3xl">
        TitanIQ gets smarter after every match
      </h2>
      <p className="mt-3 max-w-xl text-base text-[var(--li-text-secondary)]">
        Nothing here is hidden — this is the real pipeline that runs after every settled result,
        not a marketing diagram.
      </p>

      <div className="relative mt-10 max-w-2xl">
        <div className="absolute top-1 bottom-1 left-[15px] w-px bg-[var(--li-border)]" aria-hidden="true" />
        <div className="space-y-7">
          {LEARNING_STEPS.map((step, i) => (
            <div key={step.title} className="relative flex gap-5">
              <span className="relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full border border-[var(--li-border)] bg-[var(--li-surface)] text-[var(--li-purple)]">
                <step.icon className="size-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                <p className="font-mono text-[10px] uppercase tracking-wider text-[var(--li-text-muted)]">Step {i + 1}</p>
                <p className="mt-0.5 text-sm font-semibold text-[var(--li-text-primary)]">{step.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-[var(--li-text-secondary)]">{step.detail}</p>
              </div>
            </div>
          ))}

          <div className="relative flex gap-5">
            <span className="relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full border border-dashed border-[var(--li-border-strong)] text-[var(--li-text-muted)]">
              <CornerLeftUp className="size-4" aria-hidden="true" />
            </span>
            <p className="pt-1.5 text-sm text-[var(--li-text-muted)]">
              Feeds back into <span className="text-[var(--li-text-secondary)]">Prediction Validation</span> — a
              measured, monitored loop, not a one-time run.
            </p>
          </div>
        </div>
      </div>
    </Section>
  )
}
