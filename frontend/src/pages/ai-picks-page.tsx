import { useMemo, useState } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi } from '@/lib/api/sports'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { ErrorState } from '@/components/ui/error-state'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { AiPickCard, AI_PICK_CONFIDENCE_FLOOR } from '@/components/command-deck/ai-picks/ai-pick-card'
import { dedupeByFixture } from '@/lib/predictions/dedupe-by-fixture'
import type { PredictionPickDto, FixtureSummaryDto } from '@/lib/api/types'
import type { SportCode } from '@/lib/api/sports'

const SPORT_FILTERS: Array<{ label: string; code: SportCode | null }> = [
  { label: 'All sports', code: null },
  ...SPORT_SLUGS.map((s) => ({ label: s.label, code: s.code })),
]

const DISPLAY_LIMIT = 24

function sportSlugFor(code: string): string {
  return SPORT_SLUGS.find((s) => s.code === code)?.slug ?? code
}

export default function AiPicksPage() {
  const [sportCode, setSportCode] = useState<SportCode | null>(null)

  const query = useQuery({
    queryKey: ['predictions', 'picks', sportCode],
    queryFn: () => predictionsApi.picks({ sport_code: sportCode ?? undefined, limit: 100 }),
  })

  const topPicks = useMemo(
    () =>
      dedupeByFixture(query.data ?? [])
        .filter((pick) => pick.confidence_composite >= AI_PICK_CONFIDENCE_FLOOR)
        .slice(0, DISPLAY_LIMIT),
    [query.data]
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

  return (
    <div className="command-deck space-y-6 rounded-[var(--cd-radius-xl)]" style={{ backgroundColor: 'var(--cd-bg)', padding: '1.5rem' }}>
      <div>
        <span className="font-[var(--cd-font-telemetry)] text-[11px] font-medium uppercase tracking-[0.08em]" style={{ color: 'var(--cd-accent)' }}>
          AI Picks
        </span>
        <h2 className="mt-1 font-[var(--cd-font-display)] text-lg font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          TitanIQ's strongest daily recommendations
        </h2>
        <p className="mt-1 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
          One card per match — TitanIQ's highest-confidence published prediction, ranked by confidence.
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {SPORT_FILTERS.map((filter) => {
          const active = sportCode === filter.code
          return (
            <button
              key={filter.label}
              type="button"
              onClick={() => setSportCode(filter.code)}
              className="rounded-full border px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors"
              style={{
                borderColor: active ? 'var(--cd-accent-strong)' : 'var(--cd-border-default)',
                backgroundColor: active ? 'var(--cd-accent-muted)' : 'transparent',
                color: active ? 'var(--cd-accent)' : 'var(--cd-text-secondary)',
              }}
            >
              {filter.label}
            </button>
          )
        })}
      </div>

      {(query.isPending || (topPicks.length > 0 && cards.length === 0 && fixtureQueries.some((q) => q.isPending))) && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-72" />
          ))}
        </div>
      )}

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}

      {query.data && topPicks.length === 0 && (
        <InfinityEmptyState
          icon={Sparkles}
          title="No AI Picks yet"
          description="Picks appear here once TitanIQ has published a prediction with at least moderate confidence for an upcoming match."
        />
      )}

      {cards.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cards
            .slice()
            .sort((a, b) => b.pick.confidence_composite - a.pick.confidence_composite)
            .map(({ pick, fixture }) => (
              <AiPickCard key={pick.id} pick={pick} fixture={fixture} sportSlug={sportSlugFor(pick.sport_code)} />
            ))}
        </div>
      )}
    </div>
  )
}
