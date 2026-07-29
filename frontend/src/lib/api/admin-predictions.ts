import { api } from '@/lib/api/client'

export const adminPredictionsApi = {
  marketsHealth: () => api.get<Record<string, unknown>>('/api/v1/admin/predictions/markets/health'),
  marketConfidence: (marketKey: string, limit = 200) =>
    api.get<Record<string, unknown>>(`/api/v1/admin/predictions/markets/${marketKey}/confidence`, { limit }),
  marketAccuracy: (marketKey: string, limit = 200) =>
    api.get<Record<string, unknown>>(`/api/v1/admin/predictions/markets/${marketKey}/accuracy`, { limit }),
  marketDrift: (marketKey: string, window = 50) =>
    api.get<Record<string, unknown>>(`/api/v1/admin/predictions/markets/${marketKey}/drift`, { window }),
  exportMarket: (marketKey: string, limit = 500) =>
    api.get<unknown[]>(`/api/v1/admin/predictions/markets/${marketKey}/export`, { limit }),
  alerts: () => api.get<unknown[]>('/api/v1/admin/predictions/alerts'),
  regenerate: (input: { market_key: string; entity_type: string; entity_id: string; subject_ref: string }) =>
    api.post<{ id: string; status: string; probability: number }>('/api/v1/admin/predictions/regenerate', input),
  rollbackModel: (marketId: string) =>
    api.post<{ id: string; model_key: string; status: string }>('/api/v1/admin/predictions/models/rollback', {
      market_id: marketId,
    }),
}
