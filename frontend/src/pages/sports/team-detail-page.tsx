import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { PageLoader } from '@/components/layout/page-loader'
import { ErrorState } from '@/components/ui/error-state'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PlayerCard } from '@/components/domain/player-card'
import { MatchCard } from '@/components/domain/match-card'
import { RelatedNewsPanel } from '@/components/domain/related-news-panel'
import { sportsApi } from '@/lib/api/sports'

export default function TeamDetailPage() {
  const { teamId } = useParams<{ teamId: string }>()

  const teamQuery = useQuery({ queryKey: ['sports', 'team', teamId], queryFn: () => sportsApi.getTeam(teamId!), enabled: Boolean(teamId) })
  const playersQuery = useQuery({
    queryKey: ['sports', 'teamPlayers', teamId],
    queryFn: () => sportsApi.teamPlayers(teamId!),
    enabled: Boolean(teamId),
  })
  const fixturesQuery = useQuery({
    queryKey: ['sports', 'teamFixtures', teamId],
    queryFn: () => sportsApi.teamFixtures(teamId!),
    enabled: Boolean(teamId),
  })

  if (teamQuery.isLoading) return <PageLoader />
  if (teamQuery.isError || !teamQuery.data) {
    return (
      <div className="p-6">
        <ErrorState description="Could not load this team." onRetry={() => teamQuery.refetch()} />
      </div>
    )
  }

  const team = teamQuery.data

  return (
    <div className="flex flex-col gap-6 p-6">
      <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Team Center', to: '/app/teams' }, { label: team.name }]} />
      <div>
        <h1 className="font-display text-2xl font-semibold text-text-primary">{team.name}</h1>
        <p className="text-sm text-text-muted">{team.country ?? '—'} {team.venue_name ? `· ${team.venue_name}` : ''}</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Roster</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {playersQuery.data && playersQuery.data.length > 0 ? (
              playersQuery.data.map((player) => <PlayerCard key={player.id} player={player} />)
            ) : (
              <p className="text-sm text-text-muted">No players registered yet.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent fixtures</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {fixturesQuery.data && fixturesQuery.data.length > 0 ? (
              fixturesQuery.data.map((fixture) => <MatchCard key={fixture.id} fixture={fixture} />)
            ) : (
              <p className="text-sm text-text-muted">No recent fixtures.</p>
            )}
          </CardContent>
        </Card>

        <RelatedNewsPanel entityRef={team.name} />
      </div>
    </div>
  )
}
