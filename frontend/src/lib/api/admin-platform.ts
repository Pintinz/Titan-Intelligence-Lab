import { api } from '@/lib/api/client'
import type {
  CompetitionFixtureSourceDto,
  ConnectionTestResultDto,
  ProviderCategory,
  ProviderCategorySummaryDto,
  ProviderCredentialMaskedDto,
  ProviderDto,
  ProviderHistoryDto,
  ProviderStatusSummaryDto,
  ProviderUsageSummaryDto,
  SyncRunSummaryDto,
  TeamMappingSuggestionDto,
  NewsSourceDto,
} from '@/lib/api/types'

/**
 * Endpoints defined directly in apps/api/main.py (Provider Management, Feature
 * Registration/Flags/Quality, Sports Ingestion Sync, Redis monitoring, KG node lookup) — all
 * gated `require_role(Role.ADMINISTRATOR)` (M10-prep security fix). Kept in a separate module
 * from the router-backed domains above since these predate the router split and share no
 * request/response types with them.
 */
export const adminPlatformApi = {
  // -- Provider Registry (Milestone 11B) --------------------------------------------------------
  listProviders: () => api.get<ProviderDto[]>('/api/v1/admin/providers'),
  getProvider: (providerId: string) => api.get<ProviderDto>(`/api/v1/admin/providers/${providerId}`),
  registerProvider: (input: {
    key: string
    name: string
    category: ProviderCategory
    priority?: number
    daily_quota_limit?: number | null
    monthly_quota_limit?: number | null
    base_url?: string | null
    auth_type?: string | null
    region?: string | null
    version?: string | null
    environment?: string
    timeout_seconds?: number
    retry_count?: number
    retry_delay_seconds?: number
  }) => api.post<ProviderDto>('/api/v1/admin/providers', input),
  updateProvider: (providerId: string, input: Partial<Record<string, unknown>>) =>
    api.patch<ProviderDto>(`/api/v1/admin/providers/${providerId}`, input),
  deleteProvider: (providerId: string) => api.delete<{ id: string; deleted: boolean }>(`/api/v1/admin/providers/${providerId}`),
  activateProvider: (providerId: string) =>
    api.post<{ id: string; status: string }>(`/api/v1/admin/providers/${providerId}/activate`),
  disableProvider: (providerId: string) =>
    api.post<{ id: string; status: string }>(`/api/v1/admin/providers/${providerId}/disable`),
  listProviderCredentials: (providerId: string) =>
    api.get<ProviderCredentialMaskedDto[]>(`/api/v1/admin/providers/${providerId}/credentials`),
  addProviderCredential: (providerId: string, input: { label: string; value: string; expires_at?: string | null }) =>
    api.post<ProviderCredentialMaskedDto>(`/api/v1/admin/providers/${providerId}/credentials`, input),
  rotateProviderKey: (
    providerId: string,
    input: { old_credential_id: string; label: string; value: string; expires_at?: string | null },
  ) => api.post<ProviderCredentialMaskedDto>(`/api/v1/admin/providers/${providerId}/rotate-key`, input),
  testProviderConnection: (providerId: string) =>
    api.post<ConnectionTestResultDto>(`/api/v1/admin/providers/${providerId}/test`),
  refreshProviderConnection: (providerId: string) =>
    api.post<ConnectionTestResultDto>(`/api/v1/admin/providers/${providerId}/refresh`),
  importProviderFromEnv: (input: { env_var_name: string; key: string; name: string; category: ProviderCategory; credential_label?: string }) =>
    api.post<{ provider: ProviderDto; credential: ProviderCredentialMaskedDto }>('/api/v1/admin/providers/import-from-env', input),
  providerUsage: (providerId: string, period: 'daily' | 'monthly' = 'daily', limit = 30) =>
    api.get<ProviderUsageSummaryDto>(`/api/v1/admin/providers/${providerId}/usage`, { period, limit }),
  providerHistory: (providerId: string, limit = 20) =>
    api.get<ProviderHistoryDto>(`/api/v1/admin/providers/${providerId}/history`, { limit }),
  providerCategories: () => api.get<ProviderCategorySummaryDto[]>('/api/v1/admin/providers/categories'),
  providerStatusSummary: () => api.get<ProviderStatusSummaryDto>('/api/v1/admin/providers/status'),

  // -- Provider Health Intelligence ------------------------------------------------------------
  providerHealthSummary: (providerId: string, windowHours = 24) =>
    api.get<Record<string, unknown>>(`/api/v1/admin/providers/${providerId}/health/summary`, {
      window_hours: windowHours,
    }),
  providerHealthTrend: (providerId: string, days = 7) =>
    api.get<unknown[]>(`/api/v1/admin/providers/${providerId}/health/trend`, { days }),
  providerIncidents: (providerId: string) => api.get<unknown[]>(`/api/v1/admin/providers/${providerId}/health/incidents`),
  providerDiagnostics: (providerId: string) => api.get<Record<string, unknown>>(`/api/v1/admin/providers/${providerId}/diagnostics`),
  recordProviderHealthCheck: (providerId: string, input: { success: boolean; latency_ms?: number; message?: string }) =>
    api.post<Record<string, unknown>>(`/api/v1/admin/providers/${providerId}/health/check`, input),
  credentialHealth: (credentialId: string, providerId: string) =>
    api.get<{ credential_id: string; reliability_score: number | null }>(
      `/api/v1/admin/credentials/${credentialId}/health`,
      { provider_id: providerId },
    ),

  // -- Feature registration workflow -----------------------------------------------------------
  registerFeature: (input: Record<string, unknown>) => api.post<Record<string, unknown>>('/api/v1/admin/features', input),
  listFeatures: () => api.get<Array<Record<string, unknown>>>('/api/v1/admin/features'),
  getFeature: (featureKey: string) => api.get<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}`),
  submitFeature: (featureKey: string) => api.post<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/submit`),
  approveFeature: (featureKey: string, reviewer: string, reason?: string) =>
    api.post<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/approve`, { reviewer, reason }),
  rejectFeature: (featureKey: string, reviewer: string, reason?: string) =>
    api.post<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/reject`, { reviewer, reason }),
  deprecateFeature: (featureKey: string) => api.post<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/deprecate`),

  // -- Feature flags -----------------------------------------------------------------------------
  createFlag: (input: { key: string; name: string; description: string; enabled?: boolean; rollout_percentage?: number }) =>
    api.post<Record<string, unknown>>('/api/v1/admin/flags', input),
  listFlags: () => api.get<Array<Record<string, unknown>>>('/api/v1/admin/flags'),
  enableFlag: (key: string) => api.post<Record<string, unknown>>(`/api/v1/admin/flags/${key}/enable`),
  disableFlag: (key: string) => api.post<Record<string, unknown>>(`/api/v1/admin/flags/${key}/disable`),
  setFlagRollout: (key: string, percentage: number) =>
    api.post<Record<string, unknown>>(`/api/v1/admin/flags/${key}/rollout`, { percentage }),
  evaluateFlag: (key: string, contextId?: string) =>
    api.get<{ key: string; context_id: string | null; enabled: boolean }>(`/api/v1/admin/flags/${key}/evaluate`, {
      context_id: contextId,
    }),

  // -- Feature quality / validation / usage / statistics / health --------------------------------
  featureQuality: (featureKey: string, windowDays = 7, totalExpectedEntities?: number) =>
    api.get<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/quality`, {
      window_days: windowDays,
      total_expected_entities: totalExpectedEntities,
    }),
  validateFeature: (featureKey: string, windowDays = 7, totalExpectedEntities?: number) =>
    api.post<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/validate`, undefined, {
      window_days: windowDays,
      total_expected_entities: totalExpectedEntities,
    }),
  listFeatureValidations: (featureKey: string, limit = 50) =>
    api.get<unknown[]>(`/api/v1/admin/features/${featureKey}/validations`, { limit }),
  latestFeatureValidation: (featureKey: string) =>
    api.get<Record<string, unknown> | null>(`/api/v1/admin/features/${featureKey}/validations/latest`),
  featureUsage: (featureKey: string, windowDays = 7) =>
    api.get<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/usage`, { window_days: windowDays }),
  registerFeatureConsumer: (featureKey: string, consumerKey: string) =>
    api.post<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/consumers`, { consumer_key: consumerKey }),
  listFeatureConsumers: (featureKey: string) => api.get<unknown[]>(`/api/v1/admin/features/${featureKey}/consumers`),
  featureStatistics: (featureKey: string) => api.get<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/statistics`),
  featureHealth: (featureKey: string, totalExpectedEntities?: number) =>
    api.get<Record<string, unknown>>(`/api/v1/admin/features/${featureKey}/health`, {
      total_expected_entities: totalExpectedEntities,
    }),

  // -- Sports ingestion sync ----------------------------------------------------------------------
  bootstrapCompetition: (
    sportCode: string,
    input: { competition_ref: string; competition_name: string; season_label: string },
  ) =>
    api.post<{ sport_id: string; competition_id: string; competition_created: boolean; season_id: string; season_created: boolean }>(
      `/api/v1/admin/sync/${sportCode}/bootstrap`,
      input,
    ),
  triggerSyncCountries: (sportCode: string, force = false) =>
    api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/countries`, { force }),
  triggerSyncTeams: (sportCode: string, competitionRef: string, opts: { force?: boolean; seasonLabel?: string } = {}) =>
    api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/teams/${competitionRef}`, {
      force: opts.force ?? false,
      season_label: opts.seasonLabel ?? null,
    }),
  triggerSyncFixtures: (
    sportCode: string,
    competitionRef: string,
    seasonLabel: string,
    input: { season_id: string; force?: boolean; live?: boolean },
  ) => api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/fixtures/${competitionRef}/${seasonLabel}`, input),
  triggerSyncStandings: (
    sportCode: string,
    competitionRef: string,
    seasonLabel: string,
    input: { season_id: string; force?: boolean },
  ) => api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/standings/${competitionRef}/${seasonLabel}`, input),
  triggerSyncStatistics: (sportCode: string, fixtureId: string, force = false) =>
    api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/statistics/${fixtureId}`, { force }),
  triggerSyncLineups: (sportCode: string, fixtureId: string, force = false) =>
    api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/lineups/${fixtureId}`, { force }),
  triggerSyncInjuries: (sportCode: string, teamId: string, opts: { force?: boolean; seasonLabel?: string } = {}) =>
    api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/injuries/${teamId}`, {
      force: opts.force ?? false,
      season_label: opts.seasonLabel ?? null,
    }),
  triggerSyncTransfers: (sportCode: string, teamId: string, force = false) =>
    api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/transfers/${teamId}`, { force }),
  triggerSyncCoachingStaff: (sportCode: string, teamId: string, force = false) =>
    api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/coaching-staff/${teamId}`, { force }),
  syncStatus: (opts: { sport_code?: string; entity_kind?: string; limit?: number } = {}) =>
    api.get<unknown[]>('/api/v1/admin/sync/status', opts),
  syncStats: (opts: { sport_code?: string; entity_kind?: string; limit?: number } = {}) =>
    api.get<Record<string, unknown>>('/api/v1/admin/sync/stats', opts),
  ingestionQuality: (sportCode: string, entityKind: string) =>
    api.get<Record<string, unknown> | null>(`/api/v1/admin/ingestion/quality/${sportCode}/${entityKind}`),

  // -- football-data.org integration: per-competition fixture source + team mapping --------------
  getCompetitionFixtureSource: (competitionId: string) =>
    api.get<CompetitionFixtureSourceDto | null>(`/api/v1/admin/competitions/${competitionId}/fixture-source`),
  setCompetitionFixtureSource: (
    competitionId: string,
    input: { preferred_provider_key: string; provider_competition_ref: string; notes?: string | null },
  ) => api.put<CompetitionFixtureSourceDto>(`/api/v1/admin/competitions/${competitionId}/fixture-source`, input),
  clearCompetitionFixtureSource: (competitionId: string) =>
    api.delete<{ deleted: boolean }>(`/api/v1/admin/competitions/${competitionId}/fixture-source`),
  suggestTeamMappings: (competitionId: string, providerCompetitionRef: string) =>
    api.get<TeamMappingSuggestionDto[]>('/api/v1/admin/providers/football-data-org/team-suggestions', {
      competition_id: competitionId,
      provider_competition_ref: providerCompetitionRef,
    }),
  confirmTeamMappings: (mappings: Array<{ football_data_org_team_id: string; titaniq_team_id: string }>) =>
    api.post<{ mapped: number }>('/api/v1/admin/providers/football-data-org/team-mappings', { mappings }),
  triggerUpcomingFixturesSync: (
    sportCode: string,
    competitionId: string,
    input: { season_label: string; season_id: string; force?: boolean },
  ) =>
    api.post<SyncRunSummaryDto | null>(
      `/api/v1/admin/sync/${sportCode}/competitions/${competitionId}/upcoming-fixtures`,
      input,
    ),
  triggerCompletedFixturesSync: (
    sportCode: string,
    competitionId: string,
    input: { season_label: string; season_id: string; force?: boolean },
  ) =>
    api.post<SyncRunSummaryDto | null>(
      `/api/v1/admin/sync/${sportCode}/competitions/${competitionId}/completed-fixtures`,
      input,
    ),
  triggerStandingsAltSync: (
    sportCode: string,
    competitionId: string,
    input: { season_label: string; season_id: string; force?: boolean },
  ) =>
    api.post<SyncRunSummaryDto | null>(
      `/api/v1/admin/sync/${sportCode}/competitions/${competitionId}/standings-alt`,
      input,
    ),

  // -- Redis ----------------------------------------------------------------------------------------
  redisHealth: () => api.get<{ healthy: boolean; latency_ms: number | null; error: string | null }>('/api/v1/admin/monitoring/redis'),
  // KG single-entity lookup moved to graphApi.getEntity() — the admin-only duplicate endpoint
  // this called was removed (see backend/apps/api/main.py); that endpoint now also returns
  // edges_out/edges_in, so nothing was lost.

  // -- News ingestion -------------------------------------------------------------------------------
  registerNewsSource: (input: { name: string; url: string; source_type?: string; is_official?: boolean }) =>
    api.post<NewsSourceDto>('/api/v1/admin/news/sources', input),
  listNewsSources: () => api.get<NewsSourceDto[]>('/api/v1/admin/news/sources'),
  triggerNewsSync: (sourceId: string) =>
    api.post<Record<string, unknown>>(`/api/v1/admin/news/sources/${sourceId}/sync`),
}
