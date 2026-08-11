import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { PublicMatchCard } from './public-match-card'
import { Section, SectionHeading } from './section-primitives'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

export function FeaturedMatchSection({
  loading,
  picks,
}: {
  loading: boolean
  picks: PublicFeaturedIntelligenceDto[]
}) {
  if (!loading && picks.length === 0) return null

  return (
    <Section className="border-b border-border-subtle">
      <SectionHeading
        eyebrow="Featured Match Intelligence"
        title="The matches where TitanIQ has enough evidence to explain what matters"
        description="Ranked by real confidence — not every fixture, only the ones with the strongest evidence base right now."
      />

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-56 animate-pulse rounded-lg bg-bg-secondary" />
          ))}
        </div>
      ) : (
        <div className="-mx-6 flex snap-x snap-mandatory gap-4 overflow-x-auto px-6 pb-2 lg:-mx-10 lg:px-10">
          {picks.map((pick) => (
            <div key={pick.prediction_id} className="w-[320px] shrink-0 snap-start lg:w-[360px]">
              <PublicMatchCard pick={pick} />
            </div>
          ))}
        </div>
      )}

      <Link
        to="/signup"
        className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-text-primary transition-colors hover:text-accent-primary"
      >
        Explore all Intelligence <ArrowRight className="size-4" />
      </Link>
    </Section>
  )
}
