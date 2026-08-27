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
  verifiedIntelligence: PublicFeaturedIntelligenceDto[]
  newsIntelligence: PublicNewsIntelligenceItemDto[]
  knowledgeGraphPreview: PublicKnowledgeGraphPreviewDto | null
}

/** How often to quietly re-pull featured intelligence in the background — real predictions
 * publish throughout the day (new fixtures, new kickoffs), and a page left open on a long
 * browsing session should surface them rather than staying pinned to whatever was live at the
 * moment the tab was opened. */
const REFRESH_INTERVAL_MS = 3 * 60 * 1000

/**
 * Fetch-on-mount, then a quiet background refresh every `REFRESH_INTERVAL_MS`, for every section
 * of the public landing page — the only signed-out-visible surface backed by real data
 * (public_router.py). Each of the four calls fails independently: one endpoint erroring never
 * blanks sections that depend on the other three. `loading` only ever reflects the very first
 * fetch — a background refresh updates the data in place, never flashes the skeleton state back
 * in for a page the visitor is already looking at.
 */
export function useLandingIntelligence(): LandingIntelligenceState {
  const [state, setState] = useState<LandingIntelligenceState>({
    loading: true,
    platformSummary: null,
    featuredIntelligence: [],
    verifiedIntelligence: [],
    newsIntelligence: [],
    knowledgeGraphPreview: null,
  })

  useEffect(() => {
    let cancelled = false

    async function load() {
      const [platformSummary, featuredIntelligence, verifiedIntelligence, newsIntelligence, knowledgeGraphPreview] =
        await Promise.all([
          publicApi.platformSummary().catch(() => null),
          publicApi.featuredIntelligence(6).catch(() => []),
          publicApi.verifiedIntelligence(6).catch(() => []),
          publicApi.newsIntelligence(6).catch(() => []),
          publicApi.knowledgeGraphPreview().catch(() => null),
        ])
      if (cancelled) return
      setState({ loading: false, platformSummary, featuredIntelligence, verifiedIntelligence, newsIntelligence, knowledgeGraphPreview })
    }

    void load()
    const intervalId = setInterval(() => void load(), REFRESH_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(intervalId)
    }
  }, [])

  return state
}
