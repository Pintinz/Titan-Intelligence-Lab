import { api } from '@/lib/api/client'
import type { CompetitionSummaryDto, FixtureSummaryDto, PlayerSummaryDto, StandingRowDto, TeamSummaryDto } from '@/lib/api/types'

export type SportCode = 'football' | 'basketball' | 'baseball' | 'table_tennis'

export const sportsApi = {
  listCompetitions: (sportCode: SportCode) => api.get<CompetitionSummaryDto[]>(`/api/v1/sports/${sportCode}/competitions`),
  getCompetition: (competitionId: string) => api.get<CompetitionSummaryDto>(`/api/v1/sports/competitions/${competitionId}`),
  competitionStandings: (competitionId: string) =>
    api.get<StandingRowDto[]>(`/api/v1/sports/competitions/${competitionId}/standings`),
  competitionFixtures: (competitionId: string, limit = 50) =>
    api.get<FixtureSummaryDto[]>(`/api/v1/sports/competitions/${competitionId}/fixtures`, { limit }),

  listTeams: (sportCode: SportCode) => api.get<TeamSummaryDto[]>(`/api/v1/sports/${sportCode}/teams`),
  getTeam: (teamId: string) => api.get<TeamSummaryDto>(`/api/v1/sports/teams/${teamId}`),
  teamPlayers: (teamId: string) => api.get<PlayerSummaryDto[]>(`/api/v1/sports/teams/${teamId}/players`),
  teamFixtures: (teamId: string, limit = 10) => api.get<FixtureSummaryDto[]>(`/api/v1/sports/teams/${teamId}/fixtures`, { limit }),

  listPlayers: (sportCode: SportCode, limit = 100) =>
    api.get<PlayerSummaryDto[]>(`/api/v1/sports/${sportCode}/players`, { limit }),
  getPlayer: (playerId: string) => api.get<PlayerSummaryDto>(`/api/v1/sports/players/${playerId}`),

  getFixture: (fixtureId: string) => api.get<FixtureSummaryDto>(`/api/v1/sports/fixtures/${fixtureId}`),
  listFixtures: (sportCode: SportCode, opts: { competition_id?: string; limit?: number } = {}) =>
    api.get<FixtureSummaryDto[]>(`/api/v1/sports/${sportCode}/fixtures`, opts),
  /** Paginated fixture browse for the Matches/Live discovery surfaces — carries `meta.total`/
   * `has_more` through, unlike `listFixtures` (which every existing "just show me some fixtures"
   * caller keeps using unchanged). */
  listFixturesPaged: async (sportCode: SportCode, opts: FixtureQueryOpts = {}): Promise<FixturePage> => {
    const envelope = await api.getWithMeta<FixtureSummaryDto[]>(`/api/v1/sports/${sportCode}/fixtures`, opts as Record<string, unknown>)
    const meta = envelope.meta as { total?: number; offset?: number; limit?: number; has_more?: boolean }
    return {
      items: envelope.data,
      total: meta.total ?? envelope.data.length,
      offset: meta.offset ?? opts.offset ?? 0,
      limit: meta.limit ?? opts.limit ?? envelope.data.length,
      hasMore: meta.has_more ?? false,
    }
  },
}

export interface FixtureQueryOpts {
  competition_id?: string
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
