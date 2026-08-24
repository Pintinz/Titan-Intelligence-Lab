import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ChevronLeft, ChevronRight } from 'lucide-react'
import { PublicMatchCard } from './public-match-card'
import { Section } from './section-primitives'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

export function FeaturedMatchSection({
  loading,
  picks,
}: {
  loading: boolean
  picks: PublicFeaturedIntelligenceDto[]
}) {
  const scrollerRef = useRef<HTMLDivElement>(null)

  if (!loading && picks.length === 0) return null

  function scrollByCard(direction: 1 | -1) {
    scrollerRef.current?.scrollBy({ left: direction * 340, behavior: 'smooth' })
  }

  return (
    <Section id="proof-of-mechanism" className="border-b border-[var(--li-border)] scroll-mt-20">
      <div className="mb-8 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[var(--li-text-primary)] lg:text-3xl">
            The matches where TitanIQ has enough evidence to explain what matters
          </h2>
          <p className="mt-3 max-w-2xl text-sm text-[var(--li-text-secondary)]">
            Ranked by real confidence — not every fixture, only the ones with the strongest
            evidence base right now.
          </p>
        </div>
        {!loading && picks.length > 1 && (
          <div className="hidden shrink-0 items-center gap-2 lg:flex">
            <button
              type="button"
              onClick={() => scrollByCard(-1)}
              aria-label="Scroll to previous prediction"
              className="flex size-9 items-center justify-center rounded-full border border-[var(--li-border)] bg-[var(--li-surface)] text-[var(--li-text-secondary)] transition-colors hover:border-[var(--li-border-strong)] hover:text-[var(--li-text-primary)]"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => scrollByCard(1)}
              aria-label="Scroll to next prediction"
              className="flex size-9 items-center justify-center rounded-full border border-[var(--li-border)] bg-[var(--li-surface)] text-[var(--li-text-secondary)] transition-colors hover:border-[var(--li-border-strong)] hover:text-[var(--li-text-primary)]"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-64 animate-pulse rounded-[var(--li-radius-md)] bg-[var(--li-surface)]" />
          ))}
        </div>
      ) : (
        <div ref={scrollerRef} className="-mx-6 flex snap-x snap-mandatory gap-4 overflow-x-auto px-6 pb-2 lg:-mx-10 lg:px-10">
          {picks.map((pick) => (
            <div key={pick.prediction_id} className="w-[320px] shrink-0 snap-start lg:w-[360px]">
              <PublicMatchCard pick={pick} />
            </div>
          ))}
        </div>
      )}

      <Link
        to="/signup"
        className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--li-text-primary)] transition-colors hover:text-[var(--li-cyan)]"
      >
        Explore all Intelligence <ArrowRight className="size-4" />
      </Link>
    </Section>
  )
}
