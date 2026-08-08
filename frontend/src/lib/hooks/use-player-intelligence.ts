import { useQuery } from '@tanstack/react-query'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { useTeamIntelligence } from './use-team-intelligence'
import type { PlayerSummaryDto } from '@/lib/api/types'

export interface EnrichedPlayer extends PlayerSummaryDto {
  /** Real team crest, joined via `team_id` off the same `useTeamIntelligence` fetch every other
   * sport-scoped page already uses — never a stock silhouette. */
  teamLogoUrl: string | null
  /** The player's team's earliest real scheduled fixture, if any — mirrors `EnrichedTeam`'s own
   * justification: there is no player-level generate endpoint, so "Generate Intelligence" from a
   * player card deep-links to their team's actual next fixture instead of pretending to generate
   * something from the player alone. */
  teamNextFixtureId: string | null
  teamLiveNow: boolean
}

const PLAYER_FETCH_LIMIT = 300

/**
 * Player Intelligence data layer — `PlayerSummaryDto` itself carries only name/position/team, so
 * this joins in real team crest/live/next-fixture data from `useTeamIntelligence` (same query
 * cache, no duplicate fixture fetch) rather than inventing per-player AI-readiness or activity
 * signals the backend doesn't expose.
 */
export function usePlayerIntelligence(sportCode: SportCode) {
  const playersQuery = useQuery({
    queryKey: ['sports', sportCode, 'players', 'intelligence'],
    queryFn: () => sportsApi.listPlayers(sportCode, PLAYER_FETCH_LIMIT),
  })

  const { teams, aiReady, isLoading: teamsLoading, isError: teamsError, error: teamsErrorObj } = useTeamIntelligence(sportCode)
  const teamById = new Map(teams.map((t) => [t.id, t]))

  const isLoading = playersQuery.isPending || teamsLoading
  const isError = playersQuery.isError || teamsError
  const error = playersQuery.error ?? teamsErrorObj

  const players: EnrichedPlayer[] = (playersQuery.data ?? []).map((player) => {
    const team = player.team_id ? teamById.get(player.team_id) : undefined
    return {
      ...player,
      teamLogoUrl: team?.logo_url ?? null,
      teamNextFixtureId: team?.nextFixtureId ?? null,
      teamLiveNow: team?.liveNow ?? false,
    }
  })

  return { players, aiReady, isLoading, isError, error, refetch: () => void playersQuery.refetch() }
}
