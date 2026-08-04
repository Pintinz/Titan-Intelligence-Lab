import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ListTree, Users } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityPanel, InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import { InfinityPlayerCard } from '@/components/infinity/cards/player-card'
import type { DomainKey } from '@/components/infinity/primitives/badge'

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

  if (teamQuery.isPending) {
    return (
      <div className="space-y-4">
        <InfinitySkeleton className="h-8 w-64" />
        <InfinitySkeleton className="h-32" />
      </div>
    )
  }
  if (teamQuery.isError) return <ErrorState error={teamQuery.error} onRetry={() => void teamQuery.refetch()} />

  const team = teamQuery.data
  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  return (
    <div className="max-w-4xl space-y-8">
      <Link
        to={`/app/${sport.slug}/teams`}
        className="inline-flex items-center gap-1 font-infinity-body text-[13px] text-infinity-text-secondary hover:text-infinity-text-primary"
      >
        <ArrowLeft className="size-3.5" /> Back to teams
      </Link>

      <InfinityPanel tone={`var(--infinity-domain-${domain})`}>
        <InfinityLabel tone={`var(--infinity-domain-${domain})`}>Team Intelligence</InfinityLabel>
        <div className="mt-3 flex items-center gap-4">
          <TeamCrestLarge name={team.name} logoUrl={team.logo_url} />
          <div>
            <h1 className="font-infinity-display text-2xl font-semibold text-infinity-text-primary sm:text-3xl">{team.name}</h1>
            {(team.country || team.venue_name) && (
              <p className="mt-1 font-infinity-mono text-[12px] text-infinity-text-secondary">
                {[team.country, team.venue_name].filter(Boolean).join(' · ')}
              </p>
            )}
          </div>
        </div>
      </InfinityPanel>

      <div>
        <div className="mb-4 flex items-center gap-2">
          <ListTree className="size-4 text-infinity-text-muted" aria-hidden="true" />
          <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">Recent fixtures</p>
        </div>
        {fixturesQuery.isPending && <InfinitySkeleton className="h-24" />}
        {fixturesQuery.data && fixturesQuery.data.length === 0 && (
          <InfinityEmptyState icon={ListTree} title="No recent fixtures" description="Nothing under coverage for this team in the past yet." />
        )}
        {fixturesQuery.data && fixturesQuery.data.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {fixturesQuery.data.map((fixture) => {
              const { homeScore, awayScore } = fixtureScores(fixture.final_state)
              return (
                <InfinityMatchCard
                  key={fixture.id}
                  sport={domain}
                  competition={fixture.competition_name}
                  competitionLogoUrl={fixture.competition_logo_url}
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

      <div>
        <div className="mb-4 flex items-center gap-2">
          <Users className="size-4 text-infinity-text-muted" aria-hidden="true" />
          <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">Roster</p>
        </div>
        {playersQuery.isPending && <InfinitySkeleton className="h-24" />}
        {playersQuery.data && playersQuery.data.length === 0 && (
          <InfinityEmptyState icon={Users} title="No roster on file" description="Player data isn't available for this team yet." />
        )}
        {playersQuery.data && playersQuery.data.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {playersQuery.data.map((player) => (
              <Link key={player.id} to={`/app/${sport.slug}/players/${player.id}`} className="block">
                <InfinityPlayerCard name={player.name} domain={domain} team={team.name} position={player.position} />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function TeamCrestLarge({ name, logoUrl }: { name: string; logoUrl?: string | null }) {
  if (logoUrl) {
    return <img src={logoUrl} alt="" className="size-14 shrink-0 object-contain sm:size-16" loading="lazy" />
  }
  return (
    <span
      aria-hidden="true"
      className="flex size-14 shrink-0 items-center justify-center rounded-full bg-infinity-ground-2 font-infinity-display text-xl font-semibold text-infinity-text-muted sm:size-16 sm:text-2xl"
    >
      {name.charAt(0).toUpperCase()}
    </span>
  )
}
