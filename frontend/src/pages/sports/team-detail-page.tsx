import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { PlayerCard } from '@/components/domain/player-card'
import { FixtureCard } from '@/components/domain/fixture-card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

export default function TeamDetailPage() {
  const sport = useSportParam()
  const { teamId } = useParams<{ teamId: string }>()

  const teamQuery = useQuery({
    queryKey: ['sports', 'team', teamId],
    queryFn: () => sportsApi.getTeam(teamId!),
    enabled: !!teamId,
  })
  const playersQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'players'],
    queryFn: () => sportsApi.teamPlayers(teamId!),
    enabled: !!teamId,
  })
  const fixturesQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'fixtures'],
    queryFn: () => sportsApi.teamFixtures(teamId!),
    enabled: !!teamId,
  })

  if (!sport) return null

  if (teamQuery.isPending) return <Skeleton className="h-40" />
  if (teamQuery.isError) return <ErrorState error={teamQuery.error} onRetry={() => void teamQuery.refetch()} />

  const team = teamQuery.data

  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <Link
          to={`/app/${sport.slug}/teams`}
          className="inline-flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft className="size-3.5" /> Back to teams
        </Link>
        <p className="mt-3 font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Team Intelligence
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">{team.name}</h1>
        <p className="mt-1 text-sm text-text-secondary">
          {[team.country, team.venue_name].filter(Boolean).join(' · ')}
        </p>
      </div>

      <div>
        <p className="mb-3 text-sm font-medium text-text-primary">Upcoming fixtures</p>
        {fixturesQuery.isPending && <Skeleton className="h-24" />}
        {fixturesQuery.data && fixturesQuery.data.length === 0 && (
          <EmptyState title="No fixtures scheduled" description="Nothing under coverage for this team right now." />
        )}
        {fixturesQuery.data && fixturesQuery.data.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {fixturesQuery.data.map((fixture) => (
              <FixtureCard key={fixture.id} fixture={fixture} sportSlug={sport.slug} />
            ))}
          </div>
        )}
      </div>

      <div>
        <p className="mb-3 text-sm font-medium text-text-primary">Roster</p>
        {playersQuery.isPending && <Skeleton className="h-24" />}
        {playersQuery.data && playersQuery.data.length === 0 && (
          <EmptyState title="No roster on file" description="Player data isn't available for this team yet." />
        )}
        {playersQuery.data && playersQuery.data.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {playersQuery.data.map((player) => (
              <PlayerCard key={player.id} player={player} sportSlug={sport.slug} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
