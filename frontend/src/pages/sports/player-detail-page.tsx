import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { PageLoader } from '@/components/layout/page-loader'
import { ErrorState } from '@/components/ui/error-state'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { RelatedNewsPanel } from '@/components/domain/related-news-panel'
import { sportsApi } from '@/lib/api/sports'

export default function PlayerDetailPage() {
  const { playerId } = useParams<{ playerId: string }>()

  const playerQuery = useQuery({
    queryKey: ['sports', 'player', playerId],
    queryFn: () => sportsApi.getPlayer(playerId!),
    enabled: Boolean(playerId),
  })

  if (playerQuery.isLoading) return <PageLoader />
  if (playerQuery.isError || !playerQuery.data) {
    return (
      <div className="p-6">
        <ErrorState description="Could not load this player." onRetry={() => playerQuery.refetch()} />
      </div>
    )
  }

  const player = playerQuery.data

  return (
    <div className="flex flex-col gap-6 p-6">
      <Breadcrumbs
        items={[{ label: 'Dashboard', to: '/app' }, { label: 'Player Center', to: '/app/players' }, { label: player.name }]}
      />
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>{player.name}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-1 text-sm text-text-secondary">
          <p>Position: {player.position ?? 'Unknown'}</p>
          <p>Team: {player.team_name ?? 'Free agent'}</p>
          {player.date_of_birth && <p>Born: {new Date(player.date_of_birth).toLocaleDateString()}</p>}
        </CardContent>
      </Card>

      <div className="max-w-md">
        <RelatedNewsPanel entityRef={player.name} />
      </div>
    </div>
  )
}
