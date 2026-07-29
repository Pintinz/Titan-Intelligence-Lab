import { useQuery } from '@tanstack/react-query'
import { UserRound } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { PlayerCard } from '@/components/domain/player-card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

export default function PlayerListPage() {
  const sport = useSportParam()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'players', sport?.code],
    queryFn: () => sportsApi.listPlayers(sport!.code, 60),
    enabled: !!sport,
  })

  if (!sport) return null

  return (
    <div className="space-y-6">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Player Intelligence
        </p>
        <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">{sport.label} players</h2>
      </div>

      {isPending && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <EmptyState icon={UserRound} title="No players found" description={`No ${sport.label} players are under coverage.`} />
      )}

      {data && data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((player) => (
            <PlayerCard key={player.id} player={player} sportSlug={sport.slug} />
          ))}
        </div>
      )}
    </div>
  )
}
