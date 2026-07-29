import { GraduationCap, Share2, Newspaper, Gauge } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Section, SectionHeading, IllustrativeTag } from './section-primitives'
import { INTELLIGENCE_FEED } from './sample-data'

const kindIcon: Record<(typeof INTELLIGENCE_FEED)[number]['kind'], LucideIcon> = {
  learning: GraduationCap,
  kg: Share2,
  news: Newspaper,
  confidence: Gauge,
}

export function IntelligenceFeedSection() {
  return (
    <Section className="border-b border-border-subtle bg-bg-secondary/40">
      <div className="flex items-end justify-between gap-4">
        <SectionHeading
          eyebrow="Intelligence Feed"
          title="TitanIQ is always working"
          description="Every settled result, news event, and knowledge-graph update ripples back into the platform's confidence — this is what that looks like."
        />
        <IllustrativeTag />
      </div>

      <ol className="max-w-2xl space-y-0">
        {INTELLIGENCE_FEED.map((item, i) => {
          const Icon = kindIcon[item.kind]
          return (
            <li key={item.id} className="flex gap-4">
              <div className="flex flex-col items-center">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border-default bg-bg-elevated">
                  <Icon className="size-3.5 text-accent-primary" aria-hidden="true" />
                </span>
                {i < INTELLIGENCE_FEED.length - 1 && <span className="w-px flex-1 bg-border-subtle" />}
              </div>
              <div className="pb-6">
                <p className="text-sm text-text-primary">{item.text}</p>
                <p className="mt-1 font-mono text-xs text-text-muted">{item.timestamp}</p>
              </div>
            </li>
          )
        })}
      </ol>
    </Section>
  )
}
