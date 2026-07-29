import { api } from '@/lib/api/client'

/**
 * Endpoints defined directly in apps/api/main.py (Provider Management, Feature
 * Registration/Flags/Quality, Sports Ingestion Sync, Redis monitoring, KG node lookup) — all
 * gated `require_role(Role.ADMINISTRATOR)` (M10-prep security fix). Kept in a separate module
 * from the router-backed domains above since these predate the router split and share no
 * request/response types with them.
 */
export const adminPlatformApi = {
  // -- Provider Management --------------------------------------------------------------------
  listProviders: () =>
    api.get<Array<{ id: string; key: string; name: string; category: string; status: string; priority: number }>>(
      '/api/v1/admin/providers',
    ),
  activateProvider: (providerId: string) =>
    api.post<{ id: string; status: string }>(`/api/v1/admin/providers/${providerId}/activate`),

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
  triggerSyncCountries: (sportCode: string, force = false) =>
    api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/countries`, { force }),
  triggerSyncTeams: (sportCode: string, competitionRef: string, force = false) =>
    api.post<Record<string, unknown> | null>(`/api/v1/admin/sync/${sportCode}/teams/${competitionRef}`, { force }),
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
  syncStatus: (opts: { sport_code?: string; entity_kind?: string; limit?: number } = {}) =>
    api.get<unknown[]>('/api/v1/admin/sync/status', opts),
  syncStats: (opts: { sport_code?: string; entity_kind?: string; limit?: number } = {}) =>
    api.get<Record<string, unknown>>('/api/v1/admin/sync/stats', opts),
  ingestionQuality: (sportCode: string, entityKind: string) =>
    api.get<Record<string, unknown> | null>(`/api/v1/admin/ingestion/quality/${sportCode}/${entityKind}`),

  // -- Redis / KG ---------------------------------------------------------------------------------
  redisHealth: () => api.get<{ healthy: boolean; latency_ms: number | null; error: string | null }>('/api/v1/admin/monitoring/redis'),
  kgNode: (nodeType: string, entityRef: string) => api.get<Record<string, unknown>>(`/api/v1/admin/graph/nodes/${nodeType}/${entityRef}`),
}
