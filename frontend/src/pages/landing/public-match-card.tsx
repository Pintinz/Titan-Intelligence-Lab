import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { CompactIntelligenceReport } from './intelligence-card'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { cn } from '@/lib/cn'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

/**
 * The landing page's only match card — a compact-density "intelligence report," the same visual
 * language as the hero's card. Deliberately not `MatchIntelligenceCard` (that component requires
 * fabricated narrative fields — matchHighlight/newsHighlight/communityPulse/whyItMatters — none
 * of which `public_router.py`'s `featured-intelligence` returns). Renders only what the endpoint
 * actually provides — never invented explanatory prose (shape brief §10).
 */
export function PublicMatchCard({ pick }: { pick: PublicFeaturedIntelligenceDto }) {
  const sportSlug = SPORT_SLUGS.find((s) => s.code === pick.sport_code)?.slug ?? pick.sport_code

  return (
    <Link to={`/app/${sportSlug}/matches/${pick.fixture_id}`}>
      <div
        className={cn(
          'group relative flex h-full flex-col gap-1 overflow-hidden rounded-[var(--li-radius-md)] border border-[var(--li-glass-2-border)] bg-[var(--li-glass-2-bg)] p-5 backdrop-blur-[var(--li-glass-2-blur)]',
          'shadow-[var(--li-shadow-card)] transition-all duration-300 hover:-translate-y-1 hover:border-[var(--li-border-strong)] hover:shadow-[var(--li-shadow-card-hover)]',
        )}
      >
        <CompactIntelligenceReport pick={pick} />

        <span className="mt-3 inline-flex items-center gap-1 font-sans text-xs font-medium text-[var(--li-cyan)] opacity-0 transition-opacity group-hover:opacity-100">
          Open Match Intelligence <ArrowRight className="size-3" />
        </span>
      </div>
    </Link>
  )
}
