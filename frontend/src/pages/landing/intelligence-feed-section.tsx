import { Newspaper, TrendingUp, Zap } from 'lucide-react'
import { FEATURED_MATCHES, SAMPLE_NEWS, SAMPLE_TOPICS } from '@/pages/landing/sample-data'
import { ConfidenceTelemetry, IllustrativeTag, Section, SectionHeading } from '@/pages/landing/telemetry'

type FeedRow = {
  key: string
  kind: 'prediction' | 'news' | 'pulse'
  label: string
  detail: string
  composite?: number
}

/**
 * Intelligence Feed — a dense, terminal-style scroll of what TitanIQ is actively reasoning about
 * right now, mixing predictions, news events, and community pulse into one curated stream rather
 * than three separate lists. Curated, not a fixture dump: capped, ordered, and every row explains
 * itself in one line.
 */
export function IntelligenceFeedSection() {
  const rows: FeedRow[] = [
    ...FEATURED_MATCHES.map(({ seed, fixture }) => ({
      key: `pred-${fixture.id}`,
      kind: 'prediction' as const,
      label: `${fixture.home_team.short_name} vs ${fixture.away_team.short_name}`,
      detail: seed.narrative,
      composite: seed.composite,
    })),
    ...SAMPLE_NEWS.map((n) => ({ key: `news-${n.title}`, kind: 'news' as const, label: n.title, detail: n.summary })),
    ...SAMPLE_TOPICS.slice(0, 2).map((t) => ({
      key: `pulse-${t.id}`,
      kind: 'pulse' as const,
      label: t.topic_label,
      detail: `${t.post_count.toLocaleString()} posts tracked · momentum ${t.momentum > 0 ? '+' : ''}${Math.round(t.momentum * 100)}`,
    })),
  ]

  return (
    <Section className="pt-0">
      <SectionHeading
        eyebrow="Intelligence Feed"
        title="What TitanIQ is reasoning about right now"
        description="Predictions, news events, and community pulse — curated into a single stream, not dumped fixture-by-fixture."
        action={<IllustrativeTag />}
      />

      <div className="mt-8 divide-y" style={{ borderColor: 'var(--tl-steel-line)' }}>
        {rows.map((row) => (
          <div key={row.key} className="flex items-start gap-4 py-4" style={{ borderColor: 'var(--tl-steel-line)' }}>
            <FeedIcon kind={row.kind} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium" style={{ color: 'var(--tl-ink)' }}>
                {row.label}
              </p>
              <p className="mt-0.5 truncate text-xs" style={{ color: 'var(--tl-ink-dim)' }}>
                {row.detail}
              </p>
            </div>
            {row.composite !== undefined && <ConfidenceTelemetry composite={row.composite} size="sm" />}
          </div>
        ))}
      </div>
    </Section>
  )
}

function FeedIcon({ kind }: { kind: FeedRow['kind'] }) {
  const style = { color: kind === 'prediction' ? 'var(--tl-signal)' : kind === 'news' ? 'var(--tl-amber)' : 'var(--tl-violet)' }
  const Icon = kind === 'prediction' ? Zap : kind === 'news' ? Newspaper : TrendingUp
  return (
    <div
      className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md"
      style={{ background: 'var(--tl-carbon-raised)', border: '1px solid var(--tl-steel-line)' }}
    >
      <Icon className="h-4 w-4" style={style} aria-hidden="true" />
    </div>
  )
}
