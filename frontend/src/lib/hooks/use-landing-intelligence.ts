import { useEffect, useState } from 'react'
import { publicApi } from '@/lib/api/public'
import type {
  PublicFeaturedIntelligenceDto,
  PublicKnowledgeGraphPreviewDto,
  PublicNewsIntelligenceItemDto,
  PublicPlatformSummaryDto,
} from '@/lib/api/types'

interface LandingIntelligenceState {
  loading: boolean
  platformSummary: PublicPlatformSummaryDto | null
  featuredIntelligence: PublicFeaturedIntelligenceDto[]
  newsIntelligence: PublicNewsIntelligenceItemDto[]
  knowledgeGraphPreview: PublicKnowledgeGraphPreviewDto | null
}

/**
 * Single fetch-on-mount for every section of the public landing page — the only signed-out-visible
 * surface backed by real data (public_router.py). Each of the four calls fails independently: one
 * endpoint erroring never blanks sections that depend on the other three.
 */
export function useLandingIntelligence(): LandingIntelligenceState {
  const [state, setState] = useState<LandingIntelligenceState>({
    loading: true,
    platformSummary: null,
    featuredIntelligence: [],
    newsIntelligence: [],
    knowledgeGraphPreview: null,
  })

  useEffect(() => {
    let cancelled = false

    async function load() {
      const [platformSummary, featuredIntelligence, newsIntelligence, knowledgeGraphPreview] = await Promise.all([
        publicApi.platformSummary().catch(() => null),
        publicApi.featuredIntelligence(6).catch(() => []),
        publicApi.newsIntelligence(6).catch(() => []),
        publicApi.knowledgeGraphPreview().catch(() => null),
      ])
      if (cancelled) return
      setState({ loading: false, platformSummary, featuredIntelligence, newsIntelligence, knowledgeGraphPreview })
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
