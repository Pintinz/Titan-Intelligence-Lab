import { LEARNING_PIPELINE } from '@/pages/landing/sample-data'
import { Section, SectionHeading } from '@/pages/landing/telemetry'

/**
 * Learning Intelligence — the one section in this page where numbered steps are earned: this is
 * a real, ordered pipeline (docs/titaniq.md §4), not a decorative 01/02/03 treatment. A traveling
 * pulse along the connecting line makes the "compounding" idea visible rather than asserted.
 */
export function LearningIntelligenceSection() {
  return (
    <Section id="learning-intelligence" className="pt-0">
      <SectionHeading
        eyebrow="Learning Intelligence"
        title="TitanIQ gets smarter after every match"
        description="Nothing here is hidden. Every completed match runs this exact pipeline before the next prediction on the same subject."
      />

      <div className="relative mt-12">
        <div className="absolute left-0 right-0 top-4 hidden h-px overflow-hidden lg:block" style={{ background: 'var(--tl-steel-line)' }}>
          <div className="tl-pulse-travel h-full w-1/4" style={{ background: 'linear-gradient(90deg, transparent, var(--tl-signal), transparent)' }} />
        </div>

        <div className="grid gap-6 lg:grid-cols-7 lg:gap-4">
          {LEARNING_PIPELINE.map((step) => (
            <div key={step.step} className="flex flex-col gap-3 lg:items-start">
              <div className="flex items-center gap-2 lg:flex-col lg:items-start">
                <span
                  className="tl-mono flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
                  style={{ background: 'var(--tl-carbon-raised)', border: '1px solid var(--tl-signal)', color: 'var(--tl-signal)' }}
                >
                  {step.step}
                </span>
              </div>
              <div>
                <h3 className="text-sm font-semibold" style={{ color: 'var(--tl-ink)' }}>
                  {step.title}
                </h3>
                <p className="mt-1 text-xs leading-relaxed" style={{ color: 'var(--tl-ink-dim)' }}>
                  {step.detail}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Section>
  )
}
