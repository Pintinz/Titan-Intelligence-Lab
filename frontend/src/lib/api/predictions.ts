import { api } from '@/lib/api/client'
import type {
  ConfidenceBreakdownDto,
  ExplanationBundleDto,
  FixtureReviewMetaDto,
  MarketReviewDto,
  PredictionDto,
  PredictionEntitlementDto,
  PredictionPickDto,
  PredictionSummaryDto,
} from '@/lib/api/types'

/** Mobile V1 monetization — mirrors `REWARDED_AD_CREDIT_GRANT` (backend `modules.predictions.
 * domain.entities`). A fixed product constant, not server config, so it's duplicated here rather
 * than fetched — the entitlement response itself doesn't carry it (nothing about "how many
 * credits one ad is worth" varies per user or per request). */
export const REWARDED_AD_CREDIT_GRANT = 2

export const predictionsApi = {
  generate: (input: {
    market_key: string
    entity_type: string
    entity_id: string
    subject_ref: string
    include_contextual_review?: boolean
    include_football_explanation?: boolean
    // Can involve two sequential live Gemini calls (explanation + contextual review), and each
    // one now retries once server-side (TextIntelligenceRouter) before falling back to the mock
    // adapter — worst case is ~4x the adapter's own 30s timeout, so the default 20s client
    // timeout isn't nearly enough headroom here.
  }) => api.post<PredictionDto>('/api/v1/predictions/generate', input, undefined, { timeoutMs: 90_000 }),
  get: (predictionId: string) => api.get<PredictionDto>(`/api/v1/predictions/${predictionId}`),
  list: (marketId: string, opts: { status?: string; limit?: number } = {}) =>
    api.get<PredictionDto[]>('/api/v1/predictions', { market_id: marketId, ...opts }),
  approve: (predictionId: string) => api.post<PredictionDto>(`/api/v1/predictions/${predictionId}/approve`),
  reject: (predictionId: string, reason?: string) =>
    api.post<PredictionDto>(`/api/v1/predictions/${predictionId}/reject`, { reason }),

  confidence: (predictionId: string) =>
    api.get<ConfidenceBreakdownDto>(`/api/v1/predictions/${predictionId}/confidence`),
  explanation: (predictionId: string) =>
    api.get<ExplanationBundleDto>(`/api/v1/predictions/${predictionId}/explanation`),
  history: (subjectRef: string, marketId?: string) =>
    api.get<PredictionSummaryDto[]>(`/api/v1/predictions/history/${subjectRef}`, { market_id: marketId }),
  monitoringSummary: (limit = 500) =>
    api.get<Record<string, unknown>>('/api/v1/predictions/monitoring/summary', { limit }),
  statistics: (marketKey: string, limit = 500) =>
    api.get<Record<string, unknown>>(`/api/v1/predictions/statistics/${marketKey}`, { limit }),
  compare: (predictionIds: string[]) =>
    api.post<PredictionSummaryDto[]>('/api/v1/predictions/compare', { prediction_ids: predictionIds }),
  picks: (opts: { sport_code?: string; limit?: number } = {}) =>
    api.get<PredictionPickDto[]>('/api/v1/predictions/picks', opts),
  review: async (fixtureId: string) => {
    const envelope = await api.getWithMeta<MarketReviewDto[]>(`/api/v1/predictions/review/${fixtureId}`)
    return { markets: envelope.data, meta: envelope.meta as unknown as FixtureReviewMetaDto }
  },
  entitlement: () => api.get<PredictionEntitlementDto>('/api/v1/predictions/entitlement'),
}
