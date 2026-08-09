import { api } from '@/lib/api/client'
import type {
  CalibrationReportDto,
  ChallengerComparisonDto,
  DatasetDto,
  DeploymentMode,
  ExperimentDto,
  FeatureFailureAssociationDto,
  MarketPerformanceSummaryDto,
  ModelDto,
  OverconfidenceSummaryDto,
} from '@/lib/api/types'

export const mlPlatformApi = {
  buildDataset: (marketKey: string) =>
    api.post<DatasetDto>(`/api/v1/admin/ml/training/datasets/${marketKey}/build`),
  validateDataset: (datasetId: string) =>
    api.post<{ id: string; status: string }>(`/api/v1/admin/ml/training/datasets/${datasetId}/validate`),
  approveDataset: (datasetId: string, approvedBy: string) =>
    api.post<{ id: string; status: string }>(`/api/v1/admin/ml/training/datasets/${datasetId}/approve`, {
      approved_by: approvedBy,
    }),
  selectChampion: (input: { market_key: string; model_key_prefix: string; next_version?: number; target_type?: string }) =>
    api.post<{
      model_id: string
      status: string
      algorithm: string
      framework: string
      ranking_metric: string
      ranking_value: number
    }>('/api/v1/admin/ml/training/select-champion', input),

  listExperiments: (marketKey: string, limit = 50) =>
    api.get<ExperimentDto[]>(`/api/v1/admin/ml/experiments/${marketKey}`, { limit }),
  decideExperiment: (experimentId: string, decision: string) =>
    api.post<{ id: string; decision: string }>(`/api/v1/admin/ml/experiments/${experimentId}/decide`, { decision }),

  listModels: (marketKey: string) => api.get<ModelDto[]>(`/api/v1/admin/ml/models/${marketKey}`),
  setDeploymentMode: (modelId: string, mode?: DeploymentMode) =>
    api.post<{ id: string; deployment_mode: DeploymentMode }>(`/api/v1/admin/ml/models/${modelId}/deployment-mode`, {
      mode,
    }),

  champion: (marketKey: string, opts: { model_key?: string; pinned_version?: number } = {}) =>
    api.get<{ id: string; model_key: string; version: number; status: string }>(
      `/api/v1/admin/ml/champion/${marketKey}`,
      opts,
    ),
  promoteChampion: (modelId: string, approvedBy: string) =>
    api.post<{ id: string; status: string }>(`/api/v1/admin/ml/champion/${modelId}/promote`, {
      approved_by: approvedBy,
    }),

  featureImportance: (marketKey: string) =>
    api.get<{ model_id: string; global_importance: Record<string, number> }>(
      `/api/v1/admin/ml/feature-importance/${marketKey}`,
    ),

  calibrationReport: (method: string, samples: Array<[number, boolean]>) =>
    api.post<CalibrationReportDto>('/api/v1/admin/ml/calibration/reports', { method, samples }),

  benchmark: (input: { market_key: string; algorithm: string; framework: string; target_type?: string }) =>
    api.post<{ algorithm: string; framework: string; ranking_metric: string; ranking_value: number }>(
      '/api/v1/admin/ml/benchmark',
      input,
    ),

  modelHealth: (marketKey: string) => api.get<Record<string, unknown>>(`/api/v1/admin/ml/monitoring/${marketKey}/health`),
  latencyStats: (marketKey: string) => api.get<Record<string, unknown>>(`/api/v1/admin/ml/monitoring/${marketKey}/latency`),
  recordLatency: (marketKey: string, durationMs: number) =>
    api.post<{ recorded: boolean }>(`/api/v1/admin/ml/monitoring/${marketKey}/latency`, { duration_ms: durationMs }),

  checkRetraining: (marketKey: string) => api.post<Record<string, unknown>>(`/api/v1/admin/ml/retraining/${marketKey}/check`),
  latestComparison: (marketKey: string) =>
    api.get<ChallengerComparisonDto | null>(`/api/v1/admin/ml/retraining/${marketKey}/comparison`),

  listEvaluations: (modelId: string, limit = 50) =>
    api.get<Array<{ id: string; evaluated_at: string; metrics: Record<string, number>; calibration_report: unknown }>>(
      `/api/v1/admin/ml/evaluation/${modelId}`,
      { limit },
    ),

  marketPerformanceRanking: (sportCode?: string) =>
    api.get<MarketPerformanceSummaryDto[]>('/api/v1/admin/ml/error-memory/market-ranking', sportCode ? { sport_code: sportCode } : undefined),
  featureFailures: (marketKey: string) =>
    api.get<FeatureFailureAssociationDto[]>(`/api/v1/admin/ml/error-memory/${marketKey}/feature-failures`),
  overconfidence: (marketKey: string) =>
    api.get<OverconfidenceSummaryDto>(`/api/v1/admin/ml/error-memory/${marketKey}/overconfidence`),
}
