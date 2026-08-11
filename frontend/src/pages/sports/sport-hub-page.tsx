import { useQuery } from '@tanstack/react-query'
import { Radio } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import { ErrorState } from '@/components/ui/error-state'
import type { DomainKey } from '@/components/infinity/primitives/badge'

export default function SportHubPage() {
  const sport = useSportParam()
  const watchlist = useWatchlist()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'fixtures', sport?.code, 'hub'],
    queryFn: () => sportsApi.listFixtures(sport!.code, { limit: 12 }),
    enabled: !!sport,
  })

  if (!sport) return null

  return (
    <div className="space-y-6">
      <div>
        <InfinityLabel tone="var(--infinity-signal)">Live Intelligence</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">
          What's happening in {sport.label} right now
        </h2>
      </div>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <InfinityEmptyState
          icon={Radio}
          title="No fixtures under coverage"
          description={`TitanIQ has no ${sport.label} fixtures scheduled right now.`}
        />
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((fixture) => {
            const { homeScore, awayScore } = fixtureScores(fixture.final_state)
            const status = fixtureCardStatus(fixture.status)
            return (
              <InfinityMatchCard
                key={fixture.id}
                sport={sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>}
                competition={fixture.competition_name}
                competitionLogoUrl={fixture.competition_logo_url}
                status={status}
                kickoff={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                venue={fixture.venue_name}
                homeTeam={fixture.home_team.name}
                awayTeam={fixture.away_team.name}
                homeScore={homeScore}
                awayScore={awayScore}
                homeLogoUrl={fixture.home_team.logo_url}
                awayLogoUrl={fixture.away_team.logo_url}
                following={watchlist.isFollowing('fixture', fixture.id)}
                onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
                href={status === 'completed' ? `/app/${sport.slug}/matches/${fixture.id}/review` : `/app/${sport.slug}/matches/${fixture.id}`}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
