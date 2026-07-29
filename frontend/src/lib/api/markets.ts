import { api } from '@/lib/api/client'
import type { FeatureMarketMappingDto, MarketKind, PredictionMarketDto, TargetType } from '@/lib/api/types'

export const marketsApi = {
  register: (input: {
    market_key: string
    sport_code: string
    name: string
    category: string
    market_kind: MarketKind
    target_type: TargetType
    description?: string
    min_historical_window_days?: number
    required_data_quality?: number
    explainability_required?: boolean
    confidence_threshold?: number
    owner?: string
  }) => api.post<PredictionMarketDto>('/api/v1/markets', input),
  list: (opts: { sport_code?: string; status?: string } = {}) => api.get<PredictionMarketDto[]>('/api/v1/markets', opts),
  get: (marketKey: string) => api.get<PredictionMarketDto>(`/api/v1/markets/${marketKey}`),
  submit: (marketKey: string) => api.post<PredictionMarketDto>(`/api/v1/markets/${marketKey}/submit`),
  approve: (marketKey: string, reviewer: string, reason?: string) =>
    api.post<PredictionMarketDto>(`/api/v1/markets/${marketKey}/approve`, { reviewer, reason }),
  reject: (marketKey: string, reviewer: string, reason?: string) =>
    api.post<PredictionMarketDto>(`/api/v1/markets/${marketKey}/reject`, { reviewer, reason }),
  promote: (marketKey: string) => api.post<PredictionMarketDto>(`/api/v1/markets/${marketKey}/promote`),
  deprecate: (marketKey: string) => api.post<PredictionMarketDto>(`/api/v1/markets/${marketKey}/deprecate`),
  archive: (marketKey: string) => api.post<PredictionMarketDto>(`/api/v1/markets/${marketKey}/archive`),
  remove: (marketKey: string) => api.post<PredictionMarketDto>(`/api/v1/markets/${marketKey}/remove`),
  listFeatures: (marketKey: string) => api.get<FeatureMarketMappingDto[]>(`/api/v1/markets/${marketKey}/features`),
  mapFeature: (
    marketKey: string,
    input: { feature_key: string; is_required?: boolean; importance?: number; confidence_contribution?: number; weight?: number },
  ) => api.post<FeatureMarketMappingDto>(`/api/v1/markets/${marketKey}/features`, input),
}
