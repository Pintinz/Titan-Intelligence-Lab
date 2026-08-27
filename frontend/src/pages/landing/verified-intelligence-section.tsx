import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ChevronLeft, ChevronRight } from 'lucide-react'
import { VerifiedMatchCard } from './verified-match-card'
import { Section } from './section-primitives'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

/** "Verified Intelligence" — completed matches with a resolved predicted-vs-actual outcome,
 * proving the platform's real track record. Distinct from `FeaturedMatchSection` (live/upcoming
 * forecasts only, `verified-intelligence` never returns those): this section only ever shows a
 * fixture whose result is already known and whose prediction has actually been scored — see
 * `public_router.py`'s `verified_intelligence` endpoint, which drops anything still unresolved
 * rather than padding the list with a pending card. Renders nothing while there's genuinely
 * nothing verified yet, same honest-empty-state posture as every other landing section. */
export function VerifiedIntelligenceSection({
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
    <Section id="verified-intelligence" className="border-b border-[var(--li-border)] scroll-mt-20">
      <div className="mb-8 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[var(--li-text-primary)] lg:text-3xl">
            Verified Intelligence
          </h2>
          <p className="mt-3 max-w-2xl text-sm text-[var(--li-text-secondary)]">
            Real completed matches, real final scores, checked against what TitanIQ predicted
            before kickoff.
          </p>
        </div>
        {!loading && picks.length > 1 && (
          <div className="hidden shrink-0 items-center gap-2 lg:flex">
            <button
              type="button"
              onClick={() => scrollByCard(-1)}
              aria-label="Scroll to previous verified match"
              className="flex size-9 items-center justify-center rounded-full border border-[var(--li-border)] bg-[var(--li-surface)] text-[var(--li-text-secondary)] transition-colors hover:border-[var(--li-border-strong)] hover:text-[var(--li-text-primary)]"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => scrollByCard(1)}
              aria-label="Scroll to next verified match"
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
              <VerifiedMatchCard pick={pick} />
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
