import { useMemo } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { BrainCircuit } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi } from '@/lib/api/sports'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { rankPicks } from '@/lib/predictions/dedupe-by-fixture'
import { fixtureCardStatus } from '@/lib/sports-status'
import { AiPickCard } from '../ai-picks/ai-pick-card'
import { MissionSection, MissionCardGrid, MissionSkeletonGrid, MissionEmptyState } from './mission-section'
import type { PredictionPickDto, FixtureSummaryDto } from '@/lib/api/types'

const DISPLAY_LIMIT = 4

function sportSlugFor(code: string): string {
  return SPORT_SLUGS.find((s) => s.code === code)?.slug ?? code
}

/**
 * Top Intelligence — the next tier of the same ranked pick pool Intelligence Now and Priority
 * Intelligence already consumed. `rankOffset` skips whatever rank those two sections already
 * claimed (0 and 1-3) so the same match is never shown three times on one page — same shared
 * `rankPicks` helper as `/app/picks`, so no surface can drift on what "ranked" means.
 */
export function TopAiIntelligence({ rankOffset = 0 }: { rankOffset?: number } = {}) {
  const query = useQuery({
    queryKey: ['predictions', 'picks', 'mission-control'],
    queryFn: () => predictionsApi.picks({ limit: 100 }),
  })

  const topPicks = useMemo(
    () => rankPicks(query.data ?? []).slice(rankOffset, rankOffset + DISPLAY_LIMIT),
    [query.data, rankOffset],
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
      title="Top Intelligence"
      subtitle="More AI-ranked signals across every sport"
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
            <AiPickCard
              key={pick.id}
              pick={pick}
              fixture={fixture}
              sportSlug={sportSlugFor(pick.sport_code)}
              matchStatus={fixtureCardStatus(fixture.status) === 'completed' ? 'completed' : 'upcoming'}
            />
          ))}
        </MissionCardGrid>
      )}
    </MissionSection>
  )
}
