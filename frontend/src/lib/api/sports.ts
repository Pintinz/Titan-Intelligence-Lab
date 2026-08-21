import { api } from '@/lib/api/client'
import type {
  CoachingStaffDto,
  CompetitionSummaryDto,
  FixtureSummaryDto,
  FixtureTeamStatisticsDto,
  InjuryDto,
  PlayerSummaryDto,
  SeasonSummaryDto,
  StandingRowDto,
  TeamStatisticsSummaryDto,
  TeamSummaryDto,
  TransferDto,
} from '@/lib/api/types'

export type SportCode = 'football' | 'basketball' | 'baseball' | 'table_tennis'

/** Some fixtures reference a team_id the backend can no longer resolve (e.g. after a team merge)
 * and serialize home_team/away_team as null despite `FixtureSummaryDto`'s non-null type. Every
 * `sportsApi` function that returns a fixture *list* filters those out here, once, instead of
 * every one of the ~20 consuming pages/components needing its own null guard. A single fixture
 * fetched by ID (`getFixture`) can't be silently dropped this way — those two callers
 * (match-detail-page.tsx, match-review-page.tsx) guard for it directly and show an honest error. */
function withResolvedTeams(fixtures: FixtureSummaryDto[]): FixtureSummaryDto[] {
  return fixtures.filter((f) => f.home_team && f.away_team)
}

export const sportsApi = {
  listCompetitions: (sportCode: SportCode) => api.get<CompetitionSummaryDto[]>(`/api/v1/sports/${sportCode}/competitions`),
  getCompetition: (competitionId: string) => api.get<CompetitionSummaryDto>(`/api/v1/sports/competitions/${competitionId}`),
  /** Omit `seasonId` for the backend's own best-effort "current season" pick; pass one (from
   * `competitionSeasons`) to pin the response to that exact season instead — powers the season
   * filter on the competition detail page. */
  competitionStandings: (competitionId: string, seasonId?: string) =>
    api.get<StandingRowDto[]>(`/api/v1/sports/competitions/${competitionId}/standings`, seasonId ? { season_id: seasonId } : undefined),
  competitionFixtures: async (competitionId: string, limit = 50, seasonId?: string) =>
    withResolvedTeams(
      await api.get<FixtureSummaryDto[]>(`/api/v1/sports/competitions/${competitionId}/fixtures`, { limit, ...(seasonId ? { season_id: seasonId } : {}) }),
    ),
  /** Every season TitanIQ has fixture data for under this competition, most recent first — powers
   * the season picker on the Completed Matches browser so users can jump straight to an older
   * season instead of paging past every newer one first. */
  competitionSeasons: (competitionId: string) =>
    api.get<SeasonSummaryDto[]>(`/api/v1/sports/competitions/${competitionId}/seasons`),

  listTeams: (sportCode: SportCode) => api.get<TeamSummaryDto[]>(`/api/v1/sports/${sportCode}/teams`),
  getTeam: (teamId: string) => api.get<TeamSummaryDto>(`/api/v1/sports/teams/${teamId}`),
  teamPlayers: (teamId: string) => api.get<PlayerSummaryDto[]>(`/api/v1/sports/teams/${teamId}/players`),
  teamFixtures: async (teamId: string, limit = 10, when: 'recent' | 'upcoming' = 'recent') =>
    withResolvedTeams(await api.get<FixtureSummaryDto[]>(`/api/v1/sports/teams/${teamId}/fixtures`, { limit, when })),
  /** Averages of real recorded per-match stats (possession/shots/corners/fouls/cards) — never
   * fabricated, see backend `get_team_statistics`. A key comes back `null` if no recent match
   * ever recorded it; `sample_size` says how many matches actually contributed. */
  teamStatistics: (teamId: string, limit = 20) =>
    api.get<TeamStatisticsSummaryDto>(`/api/v1/sports/teams/${teamId}/statistics`, { limit }),
  /** Every player on this team's roster with a currently-reported injury — an empty array is
   * the honest, common case (most teams have no reported injuries at any given moment). */
  teamInjuries: (teamId: string) => api.get<InjuryDto[]>(`/api/v1/sports/teams/${teamId}/injuries`),
  /** Confirmed transfers in and out of this team, most recent first. */
  teamTransfers: (teamId: string) => api.get<TransferDto[]>(`/api/v1/sports/teams/${teamId}/transfers`),
  /** Current head coach/manager plus full history — `meta.current_coach_id` names which row
   * (if any) is the current one. */
  teamCoachingStaff: (teamId: string) =>
    api.getWithMeta<CoachingStaffDto[]>(`/api/v1/sports/teams/${teamId}/coaching-staff`),

  listPlayers: (sportCode: SportCode, limit = 100) =>
    api.get<PlayerSummaryDto[]>(`/api/v1/sports/${sportCode}/players`, { limit }),
  getPlayer: (playerId: string) => api.get<PlayerSummaryDto>(`/api/v1/sports/players/${playerId}`),
  playerInjuries: (playerId: string) => api.get<InjuryDto[]>(`/api/v1/sports/players/${playerId}/injuries`),
  playerTransfers: (playerId: string) => api.get<TransferDto[]>(`/api/v1/sports/players/${playerId}/transfers`),

  getFixture: (fixtureId: string) => api.get<FixtureSummaryDto>(`/api/v1/sports/fixtures/${fixtureId}`),
  /** Real per-fixture team stats for the AI Match Snapshot cards — empty array is the honest,
   * common case (most completed fixtures have no synced stats yet), never an error. */
  fixtureStatistics: (fixtureId: string) =>
    api.get<FixtureTeamStatisticsDto[]>(`/api/v1/sports/fixtures/${fixtureId}/statistics`),
  listFixtures: async (sportCode: SportCode, opts: { competition_id?: string; limit?: number } = {}) =>
    withResolvedTeams(await api.get<FixtureSummaryDto[]>(`/api/v1/sports/${sportCode}/fixtures`, opts)),
  /** Paginated fixture browse for the Matches/Live discovery surfaces — carries `meta.total`/
   * `has_more` through, unlike `listFixtures` (which every existing "just show me some fixtures"
   * caller keeps using unchanged). */
  listFixturesPaged: async (sportCode: SportCode, opts: FixtureQueryOpts = {}): Promise<FixturePage> => {
    const envelope = await api.getWithMeta<FixtureSummaryDto[]>(`/api/v1/sports/${sportCode}/fixtures`, opts as Record<string, unknown>)
    const meta = envelope.meta as { total?: number; offset?: number; limit?: number; has_more?: boolean }
    const items = withResolvedTeams(envelope.data)
    return {
      items,
      // `total`/`hasMore` intentionally still reflect the server's real count, not the
      // post-filter length — a handful of orphaned-team fixtures shouldn't understate how much
      // real data exists or break pagination math for the caller.
      total: meta.total ?? envelope.data.length,
      offset: meta.offset ?? opts.offset ?? 0,
      limit: meta.limit ?? opts.limit ?? envelope.data.length,
      hasMore: meta.has_more ?? false,
    }
  },
  /** Real "when did TitanIQ last pull data from a provider" reading — the most recent
   * succeeded-or-partial sync run across every sport, not derived from unrelated content
   * timestamps (e.g. a fixture's future kickoff). `null` until the first sync has run. */
  syncStatus: () => api.get<{ last_synced_at: string | null }>('/api/v1/sports/sync-status'),
}

export interface FixtureQueryOpts {
  competition_id?: string
  season_id?: string
  status?: 'scheduled' | 'live' | 'completed' | 'postponed' | 'cancelled'
  date_from?: string
  date_to?: string
  search?: string
  limit?: number
  offset?: number
}

export interface FixturePage {
  items: FixtureSummaryDto[]
  total: number
  offset: number
  limit: number
  hasMore: boolean
}

export const SPORT_OPTIONS: Array<{ code: SportCode; label: string }> = [
  { code: 'football', label: 'Football' },
  { code: 'basketball', label: 'Basketball' },
  { code: 'baseball', label: 'Baseball' },
  { code: 'table_tennis', label: 'Table Tennis' },
]
