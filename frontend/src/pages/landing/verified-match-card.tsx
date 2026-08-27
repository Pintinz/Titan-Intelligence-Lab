import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { VerifiedIntelligenceReport } from './intelligence-card'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { cn } from '@/lib/cn'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

/** Same card shell as `PublicMatchCard`, showing a resolved predicted-vs-actual comparison instead
 * of a live forecast — the "Verified Intelligence" section's card. */
export function VerifiedMatchCard({ pick }: { pick: PublicFeaturedIntelligenceDto }) {
  const sportSlug = SPORT_SLUGS.find((s) => s.code === pick.sport_code)?.slug ?? pick.sport_code

  return (
    <Link to={`/app/${sportSlug}/matches/${pick.fixture_id}`}>
      <div
        className={cn(
          'group relative flex h-full flex-col gap-1 overflow-hidden rounded-[var(--li-radius-md)] border border-[var(--li-glass-2-border)] bg-[var(--li-glass-2-bg)] p-5 backdrop-blur-[var(--li-glass-2-blur)]',
          'shadow-[var(--li-shadow-card)] transition-all duration-300 hover:-translate-y-1 hover:border-[var(--li-border-strong)] hover:shadow-[var(--li-shadow-card-hover)]',
        )}
      >
        <VerifiedIntelligenceReport pick={pick} />

        <span className="mt-3 inline-flex items-center gap-1 font-sans text-xs font-medium text-[var(--li-cyan)] opacity-0 transition-opacity group-hover:opacity-100">
          Open Match Intelligence <ArrowRight className="size-3" />
        </span>
      </div>
    </Link>
  )
}
