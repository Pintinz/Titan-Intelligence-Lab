import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { FixtureCard } from '@/components/domain/fixture-card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

export default function CompetitionDetailPage() {
  const sport = useSportParam()
  const { competitionId } = useParams<{ competitionId: string }>()

  const competitionQuery = useQuery({
    queryKey: ['sports', 'competition', competitionId],
    queryFn: () => sportsApi.getCompetition(competitionId!),
    enabled: !!competitionId,
  })
  const standingsQuery = useQuery({
    queryKey: ['sports', 'competition', competitionId, 'standings'],
    queryFn: () => sportsApi.competitionStandings(competitionId!),
    enabled: !!competitionId,
  })
  const fixturesQuery = useQuery({
    queryKey: ['sports', 'competition', competitionId, 'fixtures'],
    queryFn: () => sportsApi.competitionFixtures(competitionId!),
    enabled: !!competitionId,
  })

  if (!sport) return null
  if (competitionQuery.isPending) return <Skeleton className="h-40" />
  if (competitionQuery.isError) {
    return <ErrorState error={competitionQuery.error} onRetry={() => void competitionQuery.refetch()} />
  }

  const competition = competitionQuery.data

  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <Link
          to={`/app/${sport.slug}/competitions`}
          className="inline-flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft className="size-3.5" /> Back to competitions
        </Link>
        <p className="mt-3 font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Competition Intelligence
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">{competition.name}</h1>
        <p className="mt-1 text-sm text-text-secondary">
          {[competition.type, competition.country].filter(Boolean).join(' · ')}
        </p>
      </div>

      <div>
        <p className="mb-3 text-sm font-medium text-text-primary">Standings</p>
        {standingsQuery.isPending && <Skeleton className="h-40" />}
        {standingsQuery.data && standingsQuery.data.length === 0 && (
          <EmptyState title="No standings available" description="This competition has no standings on file yet." />
        )}
        {standingsQuery.data && standingsQuery.data.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-border-default">
            <table className="w-full text-sm">
              <thead className="bg-bg-secondary text-left text-xs text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Rank</th>
                  <th className="px-3 py-2 font-medium">Team</th>
                  <th className="px-3 py-2 text-right font-medium">Points</th>
                </tr>
              </thead>
              <tbody>
                {standingsQuery.data.map((row) => (
                  <tr key={row.team_id} className="border-t border-border-subtle">
                    <td className="px-3 py-2 font-mono text-text-secondary">{row.rank}</td>
                    <td className="px-3 py-2 text-text-primary">
                      <Link to={`/app/${sport.slug}/teams/${row.team_id}`} className="hover:text-accent-primary">
                        {row.team_name}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-text-primary">{row.points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div>
        <p className="mb-3 text-sm font-medium text-text-primary">Fixtures</p>
        {fixturesQuery.isPending && <Skeleton className="h-24" />}
        {fixturesQuery.data && fixturesQuery.data.length === 0 && (
          <EmptyState title="No fixtures scheduled" description="Nothing under coverage for this competition right now." />
        )}
        {fixturesQuery.data && fixturesQuery.data.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {fixturesQuery.data.map((fixture) => (
              <FixtureCard key={fixture.id} fixture={fixture} sportSlug={sport.slug} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
