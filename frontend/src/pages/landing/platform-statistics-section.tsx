import { Section } from './section-primitives'

// Capability facts, not usage/business metrics — no fabricated user or prediction counts here.
const CAPABILITIES = [
  { value: '4', label: 'Sports covered — Football, Basketball, Baseball, Table Tennis' },
  { value: '9', label: 'Confidence factors scored on every prediction' },
  { value: '100%', label: 'Predictions shipped with a full explanation bundle' },
  { value: '6', label: 'Stages in the continuous learning loop' },
]

export function PlatformStatisticsSection() {
  return (
    <Section className="border-b border-border-subtle">
      <dl className="grid grid-cols-2 gap-8 lg:grid-cols-4">
        {CAPABILITIES.map((c) => (
          <div key={c.label} className="border-t-2 border-accent-primary pt-4">
            <dt>
              <span className="font-telemetry text-4xl font-medium tabular-nums text-text-primary">{c.value}</span>
            </dt>
            <dd className="mt-2 text-sm text-text-secondary">{c.label}</dd>
          </div>
        ))}
      </dl>
    </Section>
  )
}
