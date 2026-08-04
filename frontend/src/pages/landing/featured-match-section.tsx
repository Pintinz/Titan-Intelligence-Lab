import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { MatchIntelligenceCard } from '@/components/domain/match-intelligence-card'
import { Section, SectionHeading, IllustrativeTag } from './section-primitives'
import { FEATURED_MATCHES } from './sample-data'

export function FeaturedMatchSection() {
  return (
    <Section className="border-b border-border-subtle">
      <div className="flex items-end justify-between gap-4">
        <SectionHeading
          eyebrow="Featured Match Intelligence"
          title="The highest-intelligence matches right now"
          description="Not every fixture — only the matches where TitanIQ has the strongest evidence base and something worth explaining."
        />
        <IllustrativeTag />
      </div>

      <div className="-mx-6 flex snap-x snap-mandatory gap-4 overflow-x-auto px-6 pb-2 lg:-mx-10 lg:px-10">
        {FEATURED_MATCHES.map((m) => (
          <div key={m.fixture.id} className="w-[320px] shrink-0 snap-start lg:w-[360px]">
            <MatchIntelligenceCard
              fixture={m.fixture}
              sportLabel={m.sportLabel}
              sportSlug={m.sportSlug}
              market={m.market}
              pick={m.pick}
              confidence={m.confidence.composite}
              matchHighlight={m.matchHighlight}
              newsHighlight={m.newsHighlight}
              communityPulse={m.communityPulse}
              whyItMatters={m.whyItMatters}
              rail={m.rail}
              hasNews={true}
            />
          </div>
        ))}
      </div>

      <Link
        to="/signup"
        className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-text-primary hover:text-accent-primary transition-colors"
      >
        Explore all Intelligence <ArrowRight className="size-4" />
      </Link>
    </Section>
  )
}
