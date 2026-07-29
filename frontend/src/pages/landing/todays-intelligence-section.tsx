import { Section, IllustrativeTag } from './section-primitives'
import { FEATURED_MATCHES } from './sample-data'

const STATS = [
  { label: 'Matches under coverage today', value: '47' },
  { label: 'High-confidence picks (≥70%)', value: '18' },
  { label: 'Live right now', value: String(FEATURED_MATCHES.filter((m) => m.rail === 'live').length) },
  { label: 'Sports intelligence centers active', value: '4' },
]

export function TodaysIntelligenceSection() {
  return (
    <Section className="border-b border-border-subtle py-10 lg:py-12">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
            Today's Intelligence
          </p>
          <h2 className="mt-1 font-display text-xl font-semibold text-text-primary">A snapshot of the platform right now</h2>
        </div>
        <IllustrativeTag />
      </div>
      <dl className="mt-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
        {STATS.map((s) => (
          <div key={s.label}>
            <dt className="text-xs text-text-secondary">{s.label}</dt>
            <dd className="mt-1 font-telemetry text-3xl font-medium tabular-nums text-text-primary">{s.value}</dd>
          </div>
        ))}
      </dl>
    </Section>
  )
}
