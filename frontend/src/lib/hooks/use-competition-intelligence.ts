import { useQueries, useQuery } from '@tanstack/react-query'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import type { CompetitionSummaryDto } from '@/lib/api/types'

export interface EnrichedCompetition extends CompetitionSummaryDto {
  liveCount: number
  upcomingCount: number
  completedCount: number
  /** Distinct teams observed across this competition's fetched live/upcoming/completed fixtures —
   * an honest "teams featured" reading, not a claimed roster size. A competition can have real
   * teams TitanIQ hasn't yet scheduled a fixture for in the fetched window; this only counts what
   * has actually appeared. */
  teamsFeatured: number
}

/**
 * Competition Intelligence data layer — one real per-sport fetch set (competitions + live/
 * scheduled/completed fixtures, capped generously) grouped client-side by `competition_id`, the
 * same technique `CompetitionsUnderWatch` already uses for Mission Control. Avoids an N+1 fetch
 * per competition card. `aiReady` is sport-level (a production market exists for this sport) —
 * the same granularity every other Command Deck surface already uses; TitanIQ has no per-
 * competition market coverage today; showing more would fabricate precision that doesn't exist.
 */
export function useCompetitionIntelligence(sportCode: SportCode) {
  const competitionsQuery = useQuery({
    queryKey: ['sports', sportCode, 'competitions', 'intelligence'],
    queryFn: () => sportsApi.listCompetitions(sportCode),
  })

  const fixtureQueries = useQueries({
    queries: (['live', 'scheduled', 'completed'] as const).map((status) => ({
      queryKey: ['sports', sportCode, 'fixtures', 'intelligence', status],
      queryFn: () => sportsApi.listFixturesPaged(sportCode, { status, limit: 200 }),
    })),
  })

  const marketsQuery = useQuery({
    queryKey: ['markets', sportCode, 'production', 'intelligence'],
    queryFn: () => marketsApi.list({ sport_code: sportCode, status: 'production' }),
  })

  const isLoading = competitionsQuery.isPending || fixtureQueries.some((q) => q.isPending) || marketsQuery.isPending
  const isError = competitionsQuery.isError || fixtureQueries.some((q) => q.isError) || marketsQuery.isError
  const error = competitionsQuery.error ?? fixtureQueries.find((q) => q.error)?.error ?? marketsQuery.error

  const [liveFixtures, upcomingFixtures, completedFixtures] = fixtureQueries.map((q) => q.data?.items ?? [])
  const aiReady = (marketsQuery.data?.length ?? 0) > 0

  const competitions: EnrichedCompetition[] = (competitionsQuery.data ?? []).map((competition) => {
    const own = (f: { competition_id: string | null }) => f.competition_id === competition.id
    const live = liveFixtures.filter(own)
    const upcoming = upcomingFixtures.filter(own)
    const completed = completedFixtures.filter(own)
    const teamIds = new Set<string>()
    for (const f of [...live, ...upcoming, ...completed]) {
      teamIds.add(f.home_team.id)
      teamIds.add(f.away_team.id)
    }
    return {
      ...competition,
      liveCount: live.length,
      upcomingCount: upcoming.length,
      completedCount: completed.length,
      teamsFeatured: teamIds.size,
    }
  })

  return { competitions, aiReady, isLoading, isError, error, refetch: () => void competitionsQuery.refetch() }
}
