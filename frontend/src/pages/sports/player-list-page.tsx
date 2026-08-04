import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { UserRound } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityPlayerCard } from '@/components/infinity/cards/player-card'
import type { DomainKey } from '@/components/infinity/primitives/badge'

export default function PlayerListPage() {
  const sport = useSportParam()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'players', sport?.code],
    queryFn: () => sportsApi.listPlayers(sport!.code, 60),
    enabled: !!sport,
  })

  if (!sport) return null

  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  return (
    <div className="space-y-6">
      <div>
        <InfinityLabel tone="var(--infinity-signal)">Player Intelligence</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">{sport.label} players</h2>
      </div>

      {isPending && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <InfinityEmptyState icon={UserRound} title="No players found" description={`No ${sport.label} players are under coverage.`} />
      )}

      {data && data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((player) => (
            <Link key={player.id} to={`/app/${sport.slug}/players/${player.id}`} className="block">
              <InfinityPlayerCard name={player.name} domain={domain} team={player.team_name} position={player.position} />
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
