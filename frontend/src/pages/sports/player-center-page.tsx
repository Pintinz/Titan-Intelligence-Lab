import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { UserRound } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { SportTabs } from '@/components/domain/sport-tabs'
import { PlayerCard } from '@/components/domain/player-card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { sportsApi, type SportCode } from '@/lib/api/sports'

export default function PlayerCenterPage() {
  const [sport, setSport] = useState<SportCode>('football')

  const playersQuery = useQuery({ queryKey: ['sports', 'players', sport], queryFn: () => sportsApi.listPlayers(sport, 100) })

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Player Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Player Center</h1>
      </div>

      <SportTabs value={sport} onChange={setSport} />

      {playersQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {playersQuery.isError && <ErrorState description="Could not load players." onRetry={() => playersQuery.refetch()} />}

      {playersQuery.data && playersQuery.data.length === 0 && (
        <EmptyState icon={<UserRound className="h-6 w-6" />} title="No players found" />
      )}

      {playersQuery.data && playersQuery.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {playersQuery.data.map((player) => (
            <PlayerCard key={player.id} player={player} />
          ))}
        </div>
      )}
    </div>
  )
}
