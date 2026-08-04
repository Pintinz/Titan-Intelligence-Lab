import { IntelligenceFeedEvent, type IntelligenceFeedEventType } from '@/components/domain/intelligence-feed-event'
import { Section, SectionHeading, IllustrativeTag } from './section-primitives'
import { INTELLIGENCE_FEED } from './sample-data'

const kindToEventType: Record<(typeof INTELLIGENCE_FEED)[number]['kind'], IntelligenceFeedEventType> = {
  learning: 'learning_completed',
  kg: 'kg_updated',
  news: 'news_impact',
  confidence: 'confidence_recalibrated',
}

export function IntelligenceFeedSection() {
  return (
    <Section className="border-b border-border-subtle">
      <div className="flex items-end justify-between gap-4">
        <SectionHeading
          eyebrow="Intelligence Feed"
          title="TitanIQ is always working"
          description="Every settled result, news event, and knowledge-graph update ripples back into the platform's confidence — this is what that looks like. Mission control monitoring in real time."
        />
        <IllustrativeTag />
      </div>

      <div className="max-w-2xl space-y-1 rounded-lg border border-border-subtle bg-bg-secondary/30 p-4">
        {INTELLIGENCE_FEED.map((item, i) => (
          <IntelligenceFeedEvent
            key={item.id}
            type={kindToEventType[item.kind]}
            title={item.text}
            timestamp={item.timestamp}
            isNew={i === 0}
          />
        ))}
      </div>
    </Section>
  )
}
