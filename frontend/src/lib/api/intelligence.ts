import { api } from '@/lib/api/client'
import type {
  CommunityTopicDto,
  ImpactScoreDto,
  NewsArticleDto,
  NewsEventDto,
  SentimentResultDto,
  SourceReliabilityDto,
  SummaryDto,
} from '@/lib/api/types'

export const intelligenceApi = {
  searchNews: (opts: { query?: string; source_id?: string; limit?: number } = {}) =>
    api.get<NewsArticleDto[]>('/api/v1/intelligence/news/search', opts),
  getArticle: (articleId: string) => api.get<NewsArticleDto>(`/api/v1/intelligence/news/articles/${articleId}`),
  newsTimeline: (opts: { since?: string; until?: string; limit?: number } = {}) =>
    api.get<NewsEventDto[]>('/api/v1/intelligence/news/timeline', opts),
  newsForEntity: (entityRef: string, limit = 50) =>
    api.get<NewsEventDto[]>(`/api/v1/intelligence/news/entity/${entityRef}`, { limit }),
  communityTopics: (platform?: string) =>
    api.get<CommunityTopicDto[]>('/api/v1/intelligence/community/topics', { platform }),
  sentiment: (entityRef: string, limit = 20) =>
    api.get<SentimentResultDto[]>(`/api/v1/intelligence/sentiment/${entityRef}`, { limit }),
  impact: (limit = 50) => api.get<ImpactScoreDto[]>('/api/v1/intelligence/impact', { limit }),
  impactForEvent: (newsEventId: string) => api.get<ImpactScoreDto>(`/api/v1/intelligence/impact/event/${newsEventId}`),
  summary: (subjectRef: string, summaryType: string) =>
    api.get<SummaryDto>(`/api/v1/intelligence/summaries/${subjectRef}/${summaryType}`),
  sourceReliability: (sourceId: string) =>
    api.get<SourceReliabilityDto>(`/api/v1/intelligence/sources/${sourceId}/reliability`),
  analytics: () => api.get<Record<string, unknown>>('/api/v1/intelligence/analytics'),
}
