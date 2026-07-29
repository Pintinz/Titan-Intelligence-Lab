import { PLATFORM_STATS } from '@/pages/landing/sample-data'
import { IllustrativeTag, Section, SectionHeading } from '@/pages/landing/telemetry'

export function PlatformStatisticsSection() {
  return (
    <Section className="pt-0">
      <SectionHeading eyebrow="Platform Intelligence Statistics" title="The intelligence layer, by the numbers" action={<IllustrativeTag />} />

      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {PLATFORM_STATS.map((stat) => (
          <div key={stat.label} className="flex flex-col gap-2 rounded-lg p-5" style={{ background: 'var(--tl-carbon-raised)', border: '1px solid var(--tl-steel-line)' }}>
            <span className="tl-mono text-2xl font-semibold" style={{ color: 'var(--tl-ink)' }}>
              {stat.value}
            </span>
            <span className="tl-eyebrow" style={{ color: 'var(--tl-ink-dim)', fontSize: '0.6rem' }}>
              {stat.label}
            </span>
          </div>
        ))}
      </div>
    </Section>
  )
}
