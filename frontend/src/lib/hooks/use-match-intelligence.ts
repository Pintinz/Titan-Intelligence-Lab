import { useQueries, useQuery } from '@tanstack/react-query'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'

const FETCH_LIMIT = 100

/**
 * Match Intelligence data layer — the cross-sport Matches destination's fetch set, same
 * live/scheduled/completed three-query technique `use-competition-intelligence.ts`/
 * `use-team-intelligence.ts` already established (one query per status, capped, no per-card N+1
 * fetch). `aiReady` is sport-level, same granularity every other Command Deck surface uses.
 */
export function useMatchIntelligence(sportCode: SportCode) {
  const fixtureQueries = useQueries({
    queries: (['live', 'scheduled', 'completed'] as const).map((status) => ({
      queryKey: ['sports', sportCode, 'fixtures', 'match-intelligence', status],
      queryFn: () => sportsApi.listFixturesPaged(sportCode, { status, limit: FETCH_LIMIT }),
    })),
  })

  const marketsQuery = useQuery({
    queryKey: ['markets', sportCode, 'production', 'match-intelligence'],
    queryFn: () => marketsApi.list({ sport_code: sportCode, status: 'production' }),
  })

  const isLoading = fixtureQueries.some((q) => q.isPending) || marketsQuery.isPending
  const isError = fixtureQueries.some((q) => q.isError) || marketsQuery.isError
  const error = fixtureQueries.find((q) => q.error)?.error ?? marketsQuery.error

  const [live, upcoming, completed] = fixtureQueries.map((q) => q.data?.items ?? [])
  const aiReady = (marketsQuery.data?.length ?? 0) > 0

  return {
    live,
    upcoming,
    completed,
    aiReady,
    isLoading,
    isError,
    error,
    refetch: () => fixtureQueries.forEach((q) => void q.refetch()),
  }
}
