import { useQueries } from '@tanstack/react-query'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { predictionsApi } from '@/lib/api/predictions'
import type { FixtureSummaryDto } from '@/lib/api/types'

export interface ReviewedFixture {
  fixture: FixtureSummaryDto
  sportSlug: string
  review: Awaited<ReturnType<typeof predictionsApi.review>>
}

/**
 * Shared "AI Match Reviews" logic — a completed fixture only qualifies once
 * `resolve_for_fixture` has recorded a real outcome for at least one of its PUBLISHED predictions.
 * Extracted so the Match Discovery Center's single-sport rail and Mission Control's cross-sport
 * section read from exactly one source of truth, not two copies that could drift. Accepts a list
 * of sports so a single-sport caller just passes a one-item array — same query shape either way.
 */
export function useRecentlyCompletedIntelligence(sports: Array<{ code: SportCode; slug: string }>, limit = 6) {
  const completedQueries = useQueries({
    queries: sports.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'recently-completed-intelligence'],
      queryFn: () => sportsApi.listFixturesPaged(sport.code, { status: 'completed', limit: 20 }),
    })),
  })

  const candidates = sports.flatMap((sport, i) =>
    (completedQueries[i].data?.items ?? []).map((fixture) => ({ fixture, sportSlug: sport.slug })),
  )

  const reviewQueries = useQueries({
    queries: candidates.map(({ fixture }) => ({
      queryKey: ['predictions', 'review', fixture.id],
      queryFn: () => predictionsApi.review(fixture.id),
      enabled: candidates.length > 0,
    })),
  })

  const reviewed: ReviewedFixture[] = candidates
    .map((c, i) => ({ ...c, review: reviewQueries[i]?.data }))
    .filter((row): row is ReviewedFixture => (row.review?.meta.resolved_count ?? 0) > 0)
    .slice(0, limit)

  const isLoading = completedQueries.some((q) => q.isPending) || (candidates.length > 0 && reviewQueries.some((q) => q.isPending))

  return { reviewed, isLoading }
}
