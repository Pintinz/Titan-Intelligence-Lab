import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Users } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityTeamCard } from '@/components/infinity/cards/team-card'
import type { DomainKey } from '@/components/infinity/primitives/badge'

export default function TeamListPage() {
  const sport = useSportParam()
  const watchlist = useWatchlist()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'teams', sport?.code],
    queryFn: () => sportsApi.listTeams(sport!.code),
    enabled: !!sport,
  })

  if (!sport) return null

  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  return (
    <div className="space-y-6">
      <div>
        <InfinityLabel tone="var(--infinity-signal)">Team Intelligence</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">{sport.label} teams</h2>
      </div>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <InfinityEmptyState icon={Users} title="No teams found" description={`No ${sport.label} teams are under coverage.`} />
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {data.map((team) => (
            <Link key={team.id} to={`/app/${sport.slug}/teams/${team.id}`} className="block">
              <InfinityTeamCard
                name={team.name}
                domain={domain}
                country={team.country}
                venueName={team.venue_name}
                logoUrl={team.logo_url}
                following={watchlist.isFollowing('team', team.id)}
                onToggleFollow={() => watchlist.toggle('team', team.id)}
              />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
