import { SAMPLE_MOMENTUM, SAMPLE_TOPICS } from '@/pages/landing/sample-data'
import { IllustrativeTag, Section, SectionHeading } from '@/pages/landing/telemetry'

/**
 * TitanIQ Pulse — Community Intelligence distilled to momentum, not a raw social feed.
 */
export function PulseSection() {
  const max = Math.max(...SAMPLE_MOMENTUM)
  return (
    <Section className="pt-0">
      <SectionHeading eyebrow="TitanIQ Pulse" title="What the crowd is watching" action={<IllustrativeTag />} />

      <div className="mt-8 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <div className="rounded-lg p-6" style={{ background: 'var(--tl-carbon-raised)', border: '1px solid var(--tl-steel-line)' }}>
          <span className="tl-eyebrow" style={{ color: 'var(--tl-ink-dim)', fontSize: '0.65rem' }}>
            Community momentum · last 24h
          </span>
          <div className="mt-4 flex h-24 items-end gap-1" role="img" aria-label="Community engagement momentum over the last 24 hours">
            {SAMPLE_MOMENTUM.map((v, i) => (
              <span
                key={i}
                className="flex-1 rounded-t-[2px]"
                style={{ height: `${(v / max) * 100}%`, background: i === SAMPLE_MOMENTUM.length - 1 ? 'var(--tl-violet)' : 'var(--tl-signal)', opacity: 0.25 + (v / max) * 0.75 }}
              />
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-3 rounded-lg p-6" style={{ background: 'var(--tl-carbon)', border: '1px solid var(--tl-steel-line)' }}>
          <span className="tl-eyebrow" style={{ color: 'var(--tl-ink-dim)', fontSize: '0.65rem' }}>
            Trending topics
          </span>
          {SAMPLE_TOPICS.map((topic) => (
            <div key={topic.id} className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm" style={{ color: 'var(--tl-ink)' }}>
                  {topic.topic_label}
                </p>
                <p className="tl-mono text-[0.7rem]" style={{ color: 'var(--tl-ink-faint)' }}>
                  {topic.post_count.toLocaleString()} posts
                </p>
              </div>
              <span
                className="tl-mono shrink-0 text-xs font-semibold"
                style={{ color: topic.momentum >= 0 ? 'var(--tl-signal)' : 'var(--tl-ink-faint)' }}
              >
                {topic.momentum >= 0 ? '+' : ''}
                {Math.round(topic.momentum * 100)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Section>
  )
}
