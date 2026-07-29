import { FEATURED_MATCHES, SPORTS } from '@/pages/landing/sample-data'
import { IllustrativeTag, Section, SectionHeading } from '@/pages/landing/telemetry'

/**
 * Today's Intelligence — a Bloomberg-style instrument strip: what the platform has analyzed
 * today, at a glance, per sport. Compact by design; the Featured Match section above already
 * carries the full-detail cards.
 */
export function TodaysIntelligenceSection() {
  const peakCount = FEATURED_MATCHES.filter((m) => m.seed.composite >= 0.85).length
  const avgComposite = FEATURED_MATCHES.reduce((sum, m) => sum + m.seed.composite, 0) / FEATURED_MATCHES.length

  return (
    <Section className="pt-0">
      <SectionHeading eyebrow="Today's Intelligence" title="The slate, at a glance" action={<IllustrativeTag />} />

      <div className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-lg sm:grid-cols-4" style={{ background: 'var(--tl-steel-line)' }}>
        <StatCell label="Matches analyzed" value={String(FEATURED_MATCHES.length * 9)} />
        <StatCell label="Peak-intelligence picks" value={String(peakCount)} accent="var(--tl-violet)" />
        <StatCell label="Average confidence" value={`${Math.round(avgComposite * 100)}%`} accent="var(--tl-signal)" />
        <StatCell label="Sports live today" value={String(SPORTS.length)} />
      </div>
    </Section>
  )
}

function StatCell({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="flex flex-col gap-2 p-6" style={{ background: 'var(--tl-carbon)' }}>
      <span className="tl-mono text-3xl font-semibold" style={{ color: accent ?? 'var(--tl-ink)' }}>
        {value}
      </span>
      <span className="tl-eyebrow" style={{ color: 'var(--tl-ink-dim)', fontSize: '0.65rem' }}>
        {label}
      </span>
    </div>
  )
}
