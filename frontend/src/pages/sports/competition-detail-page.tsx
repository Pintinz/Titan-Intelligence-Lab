import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ListOrdered, ListTree } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityPanel, InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import type { DomainKey } from '@/components/infinity/primitives/badge'

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
  if (competitionQuery.isPending) {
    return (
      <div className="space-y-4">
        <InfinitySkeleton className="h-8 w-64" />
        <InfinitySkeleton className="h-32" />
      </div>
    )
  }
  if (competitionQuery.isError) {
    return <ErrorState error={competitionQuery.error} onRetry={() => void competitionQuery.refetch()} />
  }

  const competition = competitionQuery.data
  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  return (
    <div className="max-w-4xl space-y-8">
      <Link
        to={`/app/${sport.slug}/competitions`}
        className="inline-flex items-center gap-1 font-infinity-body text-[13px] text-infinity-text-secondary hover:text-infinity-text-primary"
      >
        <ArrowLeft className="size-3.5" /> Back to competitions
      </Link>

      <InfinityPanel tone={`var(--infinity-domain-${domain})`}>
        <InfinityLabel tone={`var(--infinity-domain-${domain})`}>Competition Intelligence</InfinityLabel>
        <div className="mt-2 flex items-center gap-3">
          {competition.logo_url ? (
            <img src={competition.logo_url} alt="" className="size-10 shrink-0 object-contain" loading="lazy" />
          ) : (
            <span
              aria-hidden="true"
              className="flex size-10 shrink-0 items-center justify-center rounded-sm bg-infinity-ground-2 font-infinity-mono text-sm font-semibold text-infinity-text-muted"
            >
              {competition.name.charAt(0).toUpperCase()}
            </span>
          )}
          <h1 className="font-infinity-display text-2xl font-semibold text-infinity-text-primary sm:text-3xl">{competition.name}</h1>
        </div>
        {(competition.type || competition.country) && (
          <p className="mt-2 font-infinity-mono text-[12px] text-infinity-text-secondary">
            {[competition.type, competition.country].filter(Boolean).join(' · ')}
          </p>
        )}
      </InfinityPanel>

      <div>
        <div className="mb-4 flex items-center gap-2">
          <ListOrdered className="size-4 text-infinity-text-muted" aria-hidden="true" />
          <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">Standings</p>
        </div>
        {standingsQuery.isPending && <InfinitySkeleton className="h-40" />}
        {standingsQuery.data && standingsQuery.data.length === 0 && (
          <InfinityEmptyState icon={ListOrdered} title="No standings available" description="This competition has no standings on file yet." />
        )}
        {standingsQuery.data && standingsQuery.data.length > 0 && (
          <InfinityPanel className="!p-0 overflow-hidden">
            <table className="w-full font-infinity-body text-[13px]">
              <thead>
                <tr className="border-b border-infinity-border-hairline bg-infinity-ground-2 text-left">
                  <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-[0.06em] text-infinity-text-muted">Rank</th>
                  <th className="px-4 py-2.5 text-[11px] font-medium uppercase tracking-[0.06em] text-infinity-text-muted">Team</th>
                  <th className="px-4 py-2.5 text-right text-[11px] font-medium uppercase tracking-[0.06em] text-infinity-text-muted">Points</th>
                </tr>
              </thead>
              <tbody>
                {standingsQuery.data.map((row) => (
                  <tr key={row.team_id} className="border-t border-infinity-border-hairline first:border-t-0">
                    <td className="px-4 py-2.5 font-infinity-mono tabular-nums text-infinity-text-secondary">{row.rank}</td>
                    <td className="px-4 py-2.5 text-infinity-text-primary">
                      <Link to={`/app/${sport.slug}/teams/${row.team_id}`} className="hover:text-infinity-signal">
                        {row.team_name}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-right font-infinity-telemetry tabular-nums text-infinity-text-primary">{row.points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </InfinityPanel>
        )}
      </div>

      <div>
        <div className="mb-4 flex items-center gap-2">
          <ListTree className="size-4 text-infinity-text-muted" aria-hidden="true" />
          <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">Fixtures</p>
        </div>
        {fixturesQuery.isPending && <InfinitySkeleton className="h-24" />}
        {fixturesQuery.data && fixturesQuery.data.length === 0 && (
          <InfinityEmptyState icon={ListTree} title="No fixtures scheduled" description="Nothing under coverage for this competition right now." />
        )}
        {fixturesQuery.data && fixturesQuery.data.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {fixturesQuery.data.map((fixture) => {
              const { homeScore, awayScore } = fixtureScores(fixture.final_state)
              return (
                <InfinityMatchCard
                  key={fixture.id}
                  sport={domain}
                  competition={competition.name}
                  competitionLogoUrl={competition.logo_url}
                  status={fixtureCardStatus(fixture.status)}
                  kickoff={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                  venue={fixture.venue_name}
                  homeTeam={fixture.home_team.name}
                  awayTeam={fixture.away_team.name}
                  homeScore={homeScore}
                  awayScore={awayScore}
                  homeLogoUrl={fixture.home_team.logo_url}
                  awayLogoUrl={fixture.away_team.logo_url}
                  href={`/app/${sport.slug}/matches/${fixture.id}`}
                />
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
