import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { FEATURED_MATCHES } from '@/pages/landing/sample-data'
import { IntelligenceCard } from '@/pages/landing/intelligence-card'
import { IllustrativeTag, Section, SectionHeading } from '@/pages/landing/telemetry'

export function FeaturedMatchSection() {
  return (
    <Section id="featured-intelligence">
      <SectionHeading
        eyebrow="Featured Match Intelligence"
        title="Only the highest-intelligence matches make the cut"
        description="Every card is a full read on a fixture: the prediction, the confidence behind it, and the news and community signal that moved it — not a fixture list."
        action={<IllustrativeTag />}
      />

      <div className="mt-8 -mx-6 flex snap-x snap-mandatory gap-4 overflow-x-auto px-6 pb-4 sm:-mx-10 sm:px-10">
        {FEATURED_MATCHES.map((match) => (
          <IntelligenceCard key={match.fixture.id} match={match} />
        ))}
      </div>

      <div className="mt-6 flex justify-end">
        <Link
          to="/signup"
          className="tl-eyebrow flex items-center gap-1.5"
          style={{ color: 'var(--tl-signal)', fontSize: '0.7rem' }}
        >
          Explore All Intelligence
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      </div>
    </Section>
  )
}
