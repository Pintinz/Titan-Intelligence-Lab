import { useQueries } from '@tanstack/react-query'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { useTeamIntelligence, type EnrichedTeam } from './use-team-intelligence'
import type { InjuryDto, TransferDto } from '@/lib/api/types'

export interface TeamInjuries {
  team: EnrichedTeam
  injuries: InjuryDto[]
}

export interface TeamTransfers {
  team: EnrichedTeam
  transfers: TransferDto[]
}

/**
 * Context Intelligence's injury/transfer data layer. There is no cross-team "all recent
 * injuries/transfers" endpoint anywhere in the backend — `sportsApi.teamInjuries`/`teamTransfers`
 * are per-team only (confirmed via a full grep of `lib/api/`, no global feed exists). Scanning
 * every team in a sport would be a real N+1 fan-out (87 real football teams today); scoping to
 * the user's own followed teams keeps this bounded, real, and honestly relevant ("what should I
 * know about MY teams") rather than fabricating a global feed the backend can't actually back.
 * Suspensions and Lineups have no consumer-facing read endpoint at all (only an admin lineup
 * sync-trigger exists) — deliberately omitted from Context entirely, never faked.
 */
export function useContextIntelligence(sportCode: SportCode, followedTeamRefs: string[]) {
  const { teams, isLoading: teamsLoading, isError: teamsError, error: teamsErrorObj } = useTeamIntelligence(sportCode)
  const followedTeams = teams.filter((t) => followedTeamRefs.includes(t.id))

  const injuryQueries = useQueries({
    queries: followedTeams.map((team) => ({
      queryKey: ['sports', 'team', team.id, 'injuries', 'context'],
      queryFn: () => sportsApi.teamInjuries(team.id),
    })),
  })
  const transferQueries = useQueries({
    queries: followedTeams.map((team) => ({
      queryKey: ['sports', 'team', team.id, 'transfers', 'context'],
      queryFn: () => sportsApi.teamTransfers(team.id),
    })),
  })

  const isLoading = teamsLoading || injuryQueries.some((q) => q.isPending) || transferQueries.some((q) => q.isPending)
  const isError = teamsError || injuryQueries.some((q) => q.isError) || transferQueries.some((q) => q.isError)
  const error = teamsErrorObj ?? injuryQueries.find((q) => q.error)?.error ?? transferQueries.find((q) => q.error)?.error

  const injuriesByTeam: TeamInjuries[] = followedTeams
    .map((team, i) => ({ team, injuries: injuryQueries[i]?.data ?? [] }))
    .filter((entry) => entry.injuries.length > 0)

  const transfersByTeam: TeamTransfers[] = followedTeams
    .map((team, i) => ({ team, transfers: transferQueries[i]?.data ?? [] }))
    .filter((entry) => entry.transfers.length > 0)

  return { followedTeams, injuriesByTeam, transfersByTeam, isLoading, isError, error }
}
