import { api } from '@/lib/api/client'
import type {
  PublicFeaturedIntelligenceDto,
  PublicKnowledgeGraphPreviewDto,
  PublicNewsIntelligenceItemDto,
  PublicPlatformSummaryDto,
} from '@/lib/api/types'

/**
 * Client for public_router.py's `/api/v1/public/*` routes — the only endpoints in the API that
 * work for a signed-out visitor, so this is the landing page's sole source of real data. `api.get`
 * already tolerates a missing/absent auth session (see client.ts's `authHeader`), so these need no
 * special no-auth handling of their own.
 */
export const publicApi = {
  platformSummary: () => api.get<PublicPlatformSummaryDto>('/api/v1/public/platform-summary'),
  featuredIntelligence: (limit?: number) =>
    api.get<PublicFeaturedIntelligenceDto[]>('/api/v1/public/featured-intelligence', { limit }),
  verifiedIntelligence: (limit?: number) =>
    api.get<PublicFeaturedIntelligenceDto[]>('/api/v1/public/verified-intelligence', { limit }),
  newsIntelligence: (limit?: number) =>
    api.get<PublicNewsIntelligenceItemDto[]>('/api/v1/public/news-intelligence', { limit }),
  knowledgeGraphPreview: () => api.get<PublicKnowledgeGraphPreviewDto>('/api/v1/public/knowledge-graph-preview'),
}
