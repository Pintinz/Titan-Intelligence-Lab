import { useMemo } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { BrainCircuit } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi } from '@/lib/api/sports'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { dedupeByFixture } from '@/lib/predictions/dedupe-by-fixture'
import { AiPickCard, AI_PICK_CONFIDENCE_FLOOR } from '../ai-picks/ai-pick-card'
import { MissionSection, MissionCardGrid, MissionSkeletonGrid, MissionEmptyState } from './mission-section'
import type { PredictionPickDto, FixtureSummaryDto } from '@/lib/api/types'

const DISPLAY_LIMIT = 6

function sportSlugFor(code: string): string {
  return SPORT_SLUGS.find((s) => s.code === code)?.slug ?? code
}

/**
 * Today's Top AI Intelligence — the exact `AiPickCard` + fixture-dedup + confidence-floor logic
 * shipped for `/app/picks`, capped at 6 for the Mission Control preview. Never a second
 * implementation of "one card per match" — same shared `dedupeByFixture` helper, same floor
 * constant, so the two surfaces can't drift.
 */
export function TopAiIntelligence() {
  const query = useQuery({
    queryKey: ['predictions', 'picks', 'mission-control'],
    queryFn: () => predictionsApi.picks({ limit: 100 }),
  })

  const topPicks = useMemo(
    () =>
      dedupeByFixture(query.data ?? [])
        .filter((pick) => pick.confidence_composite >= AI_PICK_CONFIDENCE_FLOOR)
        .sort((a, b) => b.confidence_composite - a.confidence_composite)
        .slice(0, DISPLAY_LIMIT),
    [query.data],
  )

  const fixtureQueries = useQueries({
    queries: topPicks.map((pick) => ({
      queryKey: ['sports', 'fixtures', pick.subject_ref],
      queryFn: () => sportsApi.getFixture(pick.subject_ref),
      retry: false,
      staleTime: 60_000,
    })),
  })

  const cards = topPicks
    .map((pick, i) => ({ pick, fixture: fixtureQueries[i]?.data }))
    .filter((row): row is { pick: PredictionPickDto; fixture: FixtureSummaryDto } => !!row.fixture)

  const isLoading = query.isPending || (topPicks.length > 0 && cards.length === 0 && fixtureQueries.some((q) => q.isPending))

  return (
    <MissionSection
      id="top-ai-intelligence"
      title="Today's Top AI Intelligence"
      subtitle="The strongest ranked predictions across every sport"
      icon={<BrainCircuit className="size-4" aria-hidden="true" />}
      domain="predictions"
      viewAllHref="/app/picks"
    >
      {isLoading && <MissionSkeletonGrid />}
      {!isLoading && cards.length === 0 && (
        <MissionEmptyState
          icon={BrainCircuit}
          title="No AI Picks yet"
          description="Picks appear here once TitanIQ has published a prediction with at least moderate confidence for an upcoming match."
        />
      )}
      {!isLoading && cards.length > 0 && (
        <MissionCardGrid>
          {cards.map(({ pick, fixture }) => (
            <AiPickCard key={pick.id} pick={pick} fixture={fixture} sportSlug={sportSlugFor(pick.sport_code)} />
          ))}
        </MissionCardGrid>
      )}
    </MissionSection>
  )
}
