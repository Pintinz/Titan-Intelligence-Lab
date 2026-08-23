import { useMemo } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi } from '@/lib/api/sports'
import { rankPicks } from '@/lib/predictions/dedupe-by-fixture'
import type { FixtureSummaryDto, InjuryDto, PredictionDto, PredictionPickDto } from '@/lib/api/types'

export interface RankedIntelligenceItem {
  pick: PredictionPickDto
  fixture: FixtureSummaryDto
  topPositiveFeatures: Array<[string, number]>
  topNegativeFeatures: Array<[string, number]>
  homeInjuries: InjuryDto[]
  awayInjuries: InjuryDto[]
}

const PRIORITY_COUNT = 3
/** Intelligence Now (rank 0) + Priority Intelligence (ranks 1-3) — also the offset Top
 * Intelligence starts from, so the three sections cascade through one ranked pool with no
 * repeated match. */
const LEAD_COUNT = 1 + PRIORITY_COUNT

/**
 * Powers Intelligence Now + Priority Intelligence: the top 4 ranked picks from the same pool
 * `/app/picks` and Top Intelligence use, each enriched with real SHAP-backed top features (a
 * bounded per-pick fetch — the same technique already proven for the Workspace's Predictions tab)
 * and real per-team injuries (`sportsApi.teamInjuries` is callable for any team, not just followed
 * ones — bounded to the ≤8 teams actually involved in these 4 fixtures). A pick with no qualifying
 * feature or injury renders fewer bullets; nothing here is ever a filler sentence.
 */
export function usePriorityIntelligence() {
  const picksQuery = useQuery({ queryKey: ['predictions', 'picks', 'mission-control'], queryFn: () => predictionsApi.picks({ limit: 100 }) })
  const lead = useMemo(() => rankPicks(picksQuery.data ?? []).slice(0, LEAD_COUNT), [picksQuery.data])

  const fixtureQueries = useQueries({
    queries: lead.map((pick) => ({
      queryKey: ['sports', 'fixtures', pick.subject_ref],
      queryFn: () => sportsApi.getFixture(pick.subject_ref),
      retry: false,
      staleTime: 60_000,
    })),
  })
  const explanationQueries = useQueries({
    queries: lead.map((pick) => ({
      queryKey: ['predictions', pick.id],
      queryFn: () => predictionsApi.get(pick.id),
      staleTime: 60_000,
    })),
  })

  const rows = lead
    .map((pick, i) => ({ pick, fixture: fixtureQueries[i]?.data, detail: explanationQueries[i]?.data }))
    .filter((row): row is { pick: PredictionPickDto; fixture: FixtureSummaryDto; detail: PredictionDto | undefined } => !!row.fixture)

  const teamIds = Array.from(
    new Set(rows.flatMap((row) => [row.fixture.home_team?.id, row.fixture.away_team?.id].filter((id): id is string => !!id))),
  )
  const injuryQueries = useQueries({
    queries: teamIds.map((teamId) => ({
      queryKey: ['sports', 'team', teamId, 'injuries', 'context'],
      queryFn: () => sportsApi.teamInjuries(teamId),
      staleTime: 5 * 60 * 1000,
    })),
  })
  const injuriesByTeam = new Map(teamIds.map((teamId, i) => [teamId, injuryQueries[i]?.data ?? []]))

  const items: RankedIntelligenceItem[] = rows.map(({ pick, fixture, detail }) => ({
    pick,
    fixture,
    topPositiveFeatures: detail?.explanation.top_positive_features ?? [],
    topNegativeFeatures: detail?.explanation.top_negative_features ?? [],
    homeInjuries: fixture.home_team?.id ? (injuriesByTeam.get(fixture.home_team.id) ?? []) : [],
    awayInjuries: fixture.away_team?.id ? (injuriesByTeam.get(fixture.away_team.id) ?? []) : [],
  }))

  const isLoading = picksQuery.isPending || (lead.length > 0 && rows.length === 0 && fixtureQueries.some((q) => q.isPending))

  return {
    heroItem: items[0] as RankedIntelligenceItem | undefined,
    priorityItems: items.slice(1, LEAD_COUNT),
    isLoading,
    /** Pass straight through to `<TopAiIntelligence rankOffset={...} />`. */
    topIntelligenceRankOffset: LEAD_COUNT,
  }
}
