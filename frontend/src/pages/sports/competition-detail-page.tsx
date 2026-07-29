import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { PageLoader } from '@/components/layout/page-loader'
import { ErrorState } from '@/components/ui/error-state'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MatchCard } from '@/components/domain/match-card'
import { sportsApi } from '@/lib/api/sports'

export default function CompetitionDetailPage() {
  const { competitionId } = useParams<{ competitionId: string }>()

  const competitionQuery = useQuery({
    queryKey: ['sports', 'competition', competitionId],
    queryFn: () => sportsApi.getCompetition(competitionId!),
    enabled: Boolean(competitionId),
  })
  const standingsQuery = useQuery({
    queryKey: ['sports', 'standings', competitionId],
    queryFn: () => sportsApi.competitionStandings(competitionId!),
    enabled: Boolean(competitionId),
  })
  const fixturesQuery = useQuery({
    queryKey: ['sports', 'competitionFixtures', competitionId],
    queryFn: () => sportsApi.competitionFixtures(competitionId!),
    enabled: Boolean(competitionId),
  })

  if (competitionQuery.isLoading) return <PageLoader />
  if (competitionQuery.isError || !competitionQuery.data) {
    return (
      <div className="p-6">
        <ErrorState description="Could not load this competition." onRetry={() => competitionQuery.refetch()} />
      </div>
    )
  }

  const competition = competitionQuery.data

  return (
    <div className="flex flex-col gap-6 p-6">
      <Breadcrumbs
        items={[
          { label: 'Dashboard', to: '/app' },
          { label: 'Competition Center', to: '/app/competitions' },
          { label: competition.name },
        ]}
      />
      <h1 className="font-display text-2xl font-semibold text-text-primary">{competition.name}</h1>

      <Tabs defaultValue="standings">
        <TabsList>
          <TabsTrigger value="standings">Standings</TabsTrigger>
          <TabsTrigger value="fixtures">Fixtures</TabsTrigger>
        </TabsList>
        <TabsContent value="standings">
          <Card>
            <CardHeader>
              <CardTitle>Standings</CardTitle>
            </CardHeader>
            <CardContent>
              {standingsQuery.data && standingsQuery.data.length > 0 ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border-subtle text-left text-xs uppercase tracking-wide text-text-muted">
                      <th className="py-2">Rank</th>
                      <th>Team</th>
                      <th className="text-right">Points</th>
                    </tr>
                  </thead>
                  <tbody>
                    {standingsQuery.data.map((row) => (
                      <tr key={row.team_id} className="border-b border-border-subtle last:border-0">
                        <td className="py-2 font-mono text-text-muted">{row.rank}</td>
                        <td className="text-text-primary">{row.team_name}</td>
                        <td className="text-right font-mono text-text-primary">{row.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-sm text-text-muted">No standings available for the current season.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="fixtures">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {fixturesQuery.data?.map((fixture) => <MatchCard key={fixture.id} fixture={fixture} />)}
            {fixturesQuery.data?.length === 0 && <p className="text-sm text-text-muted">No fixtures for the current season.</p>}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
