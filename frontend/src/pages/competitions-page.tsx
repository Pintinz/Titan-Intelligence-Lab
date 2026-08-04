import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Trophy } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityButton } from '@/components/infinity/primitives/button'
import { InfinityCompetitionCard } from '@/components/infinity/cards/competition-card'
import type { DomainKey } from '@/components/infinity/primitives/badge'

/** Cross-sport Competitions — the top-level nav destination. Competitions themselves stay
 * sport-scoped data (a competition always belongs to exactly one sport), so this is a sport
 * switcher over the same per-sport list/card/follow logic already proven in
 * competition-list-page.tsx, not a new data shape. */
export default function CompetitionsPage() {
  const [sport, setSport] = useState(SPORT_SLUGS[0])
  const watchlist = useWatchlist()

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'competitions', sport.code],
    queryFn: () => sportsApi.listCompetitions(sport.code),
  })

  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  return (
    <div className="space-y-6">
      <div>
        <InfinityLabel tone="var(--infinity-signal)">Competitions</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">
          Every competition TitanIQ covers
        </h2>
      </div>

      <div className="flex flex-wrap gap-2">
        {SPORT_SLUGS.map((s) => (
          <InfinityButton
            key={s.slug}
            type="button"
            size="sm"
            variant={sport.slug === s.slug ? 'secondary' : 'ghost'}
            onClick={() => setSport(s)}
          >
            {s.label}
          </InfinityButton>
        ))}
      </div>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <InfinityEmptyState icon={Trophy} title="No competitions found" description={`No ${sport.label} competitions are under coverage.`} />
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((competition) => (
            <Link key={competition.id} to={`/app/${sport.slug}/competitions/${competition.id}`} className="block">
              <InfinityCompetitionCard
                name={competition.name}
                domain={domain}
                type={competition.type}
                country={competition.country}
                tier={competition.tier}
                logoUrl={competition.logo_url}
                following={watchlist.isFollowing('competition', competition.id)}
                onToggleFollow={() => watchlist.toggle('competition', competition.id)}
              />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
