import { useQueries, useQuery } from '@tanstack/react-query'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import type { TeamSummaryDto, FixtureSummaryDto } from '@/lib/api/types'

export interface EnrichedTeam extends TeamSummaryDto {
  /** Only present when this team appears in a fetched live/scheduled/completed fixture — Team
   * has no direct competition relationship in the backend (only reachable through fixtures), so
   * a team outside the fetched window simply has no competition shown, never a guessed one. */
  competitionId: string | null
  competitionName: string | null
  competitionLogoUrl: string | null
  /** From the real `Competition.tier` field, looked up via `competitionId` — `null` whenever the
   * competition itself has no tier recorded (true for every competition in dev data today). */
  competitionTier: number | null
  liveNow: boolean
  /** The earliest real scheduled fixture this team appears in, if any — the only honest anchor
   * for a "Generate Intelligence" action from a bare team card (there is no team-level generate
   * endpoint; every real prediction is generated against a specific fixture + market). */
  nextFixtureId: string | null
}

/**
 * Team Intelligence data layer — mirrors `use-competition-intelligence.ts`'s technique (one
 * teams-list + competitions-list fetch, plus the same three capped live/scheduled/completed
 * fixture fetches per sport), grouped client-side by `home_team.id`/`away_team.id` instead of
 * `competition_id`. Same one-fetch-set-per-sport avoids an N+1 request per team card even with
 * football's real 87 teams on screen at once.
 */
export function useTeamIntelligence(sportCode: SportCode) {
  const teamsQuery = useQuery({
    queryKey: ['sports', sportCode, 'teams', 'intelligence'],
    queryFn: () => sportsApi.listTeams(sportCode),
  })

  const competitionsQuery = useQuery({
    queryKey: ['sports', sportCode, 'competitions', 'intelligence'],
    queryFn: () => sportsApi.listCompetitions(sportCode),
  })

  const fixtureQueries = useQueries({
    queries: (['live', 'scheduled', 'completed'] as const).map((status) => ({
      queryKey: ['sports', sportCode, 'fixtures', 'intelligence', status],
      // `completed` only ever backfills a team's competition context when it has no live/scheduled
      // match (see `anyMatch` below) — it never needs anywhere near a full page. Football alone has
      // 2000+ completed fixtures on record, and fetching 200 of them measured a consistent ~20s
      // server-side (reproduced in isolation, not a contention artifact) — a much smaller page keeps
      // this fetch fast while still covering every team whose only fixture history is completed.
      queryFn: () => sportsApi.listFixturesPaged(sportCode, { status, limit: status === 'completed' ? 50 : 200 }),
    })),
  })

  const marketsQuery = useQuery({
    queryKey: ['markets', sportCode, 'production', 'intelligence'],
    queryFn: () => marketsApi.list({ sport_code: sportCode, status: 'production' }),
  })

  const isLoading = teamsQuery.isPending || competitionsQuery.isPending || fixtureQueries.some((q) => q.isPending) || marketsQuery.isPending
  const isError = teamsQuery.isError || competitionsQuery.isError || fixtureQueries.some((q) => q.isError) || marketsQuery.isError
  const error = teamsQuery.error ?? competitionsQuery.error ?? fixtureQueries.find((q) => q.error)?.error ?? marketsQuery.error

  const [liveFixtures, scheduledFixtures, completedFixtures] = fixtureQueries.map((q) => q.data?.items ?? [])
  const aiReady = (marketsQuery.data?.length ?? 0) > 0
  const tierByCompetitionId = new Map((competitionsQuery.data ?? []).map((c) => [c.id, c.tier]))

  const teams: EnrichedTeam[] = (teamsQuery.data ?? []).map((team) => {
    const isTeam = (f: FixtureSummaryDto) => f.home_team.id === team.id || f.away_team.id === team.id
    const liveMatch = liveFixtures.find(isTeam)
    const anyMatch = liveMatch ?? scheduledFixtures.find(isTeam) ?? completedFixtures.find(isTeam)
    const upcoming = scheduledFixtures
      .filter(isTeam)
      .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())[0]

    return {
      ...team,
      competitionId: anyMatch?.competition_id ?? null,
      competitionName: anyMatch?.competition_name ?? null,
      competitionLogoUrl: anyMatch?.competition_logo_url ?? null,
      competitionTier: anyMatch?.competition_id ? (tierByCompetitionId.get(anyMatch.competition_id) ?? null) : null,
      liveNow: !!liveMatch,
      nextFixtureId: upcoming?.id ?? null,
    }
  })

  return { teams, aiReady, isLoading, isError, error, refetch: () => void teamsQuery.refetch() }
}
