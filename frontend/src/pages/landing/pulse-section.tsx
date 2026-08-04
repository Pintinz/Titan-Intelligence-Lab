import { Section, SectionHeading, IllustrativeTag } from './section-primitives'
import { COMMUNITY_TOPICS } from './sample-data'

function momentumLabel(momentum: number | null) {
  if (momentum === null) return 'No signal'
  if (momentum > 0.2) return 'Positive'
  if (momentum < -0.2) return 'Negative'
  return 'Mixed'
}

export function PulseSection() {
  const maxVolume = Math.max(...COMMUNITY_TOPICS.map((t) => t.post_count))

  return (
    <Section className="border-b border-border-subtle">
      <div className="flex items-end justify-between gap-4">
        <SectionHeading
          eyebrow="TitanIQ Pulse"
          title="Community signal, never the deciding vote"
          description="Community sentiment and volume are tracked as supporting context — filtered for spam and bots, and never treated as evidence on their own."
        />
        <IllustrativeTag />
      </div>

      <div className="space-y-4">
        {COMMUNITY_TOPICS.map((topic) => (
          <div key={topic.id} className="flex items-center gap-4">
            <span className="w-40 shrink-0 truncate text-sm text-text-primary">{topic.topic_label}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-bg-secondary">
              <div
                className="h-full rounded-full bg-accent-primary"
                style={{ width: `${(topic.post_count / maxVolume) * 100}%` }}
              />
            </div>
            <span className="w-20 shrink-0 text-right font-mono text-xs text-text-muted">
              {topic.post_count.toLocaleString()}
            </span>
            <span className="w-20 shrink-0 text-right text-xs text-text-secondary">
              {momentumLabel(topic.momentum)}
            </span>
          </div>
        ))}
      </div>
    </Section>
  )
}
