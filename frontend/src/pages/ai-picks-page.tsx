import { useState } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi } from '@/lib/api/sports'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityButton } from '@/components/infinity/primitives/button'
import { InfinityPredictionCard } from '@/components/infinity/cards/prediction-card'
import type { PredictionPickDto } from '@/lib/api/types'
import type { SportCode } from '@/lib/api/sports'

const SPORT_FILTERS: Array<{ label: string; code: SportCode | null }> = [
  { label: 'All sports', code: null },
  ...SPORT_SLUGS.map((s) => ({ label: s.label, code: s.code })),
]

export default function AiPicksPage() {
  const [sportCode, setSportCode] = useState<SportCode | null>(null)

  const query = useQuery({
    queryKey: ['predictions', 'picks', sportCode],
    queryFn: () => predictionsApi.picks({ sport_code: sportCode ?? undefined, limit: 30 }),
  })

  return (
    <div className="space-y-6">
      <div>
        <InfinityLabel tone="var(--infinity-domain-predictions)">AI Picks</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">
          Today's highest-confidence predictions
        </h2>
        <p className="mt-1 font-infinity-body text-[12px] text-infinity-text-secondary">
          Every pick here is a real, already-published prediction — ranked by confidence, never fabricated.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {SPORT_FILTERS.map((filter) => (
          <InfinityButton
            key={filter.label}
            type="button"
            size="sm"
            variant={sportCode === filter.code ? 'secondary' : 'ghost'}
            onClick={() => setSportCode(filter.code)}
          >
            {filter.label}
          </InfinityButton>
        ))}
      </div>

      {query.isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}

      {query.data && query.data.length === 0 && (
        <InfinityEmptyState
          icon={Sparkles}
          title="No AI Picks yet"
          description="Picks appear here once TitanIQ has published high-confidence predictions for upcoming matches."
        />
      )}

      {query.data && query.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {query.data.map((pick) => (
            <PickCard key={pick.id} pick={pick} />
          ))}
        </div>
      )}
    </div>
  )
}

function PickCard({ pick }: { pick: PredictionPickDto }) {
  const fixtureQuery = useQueries({
    queries: [
      {
        queryKey: ['sports', 'fixtures', pick.subject_ref],
        queryFn: () => sportsApi.getFixture(pick.subject_ref),
        retry: false,
      },
    ],
  })[0]

  const fixture = fixtureQuery.data

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-infinity-mono text-[10px] uppercase tracking-[0.06em] text-infinity-text-muted">
          {pick.sport_code.replace('_', ' ')}
        </span>
        {fixture && (
          <span className="truncate font-infinity-body text-[11px] text-infinity-text-secondary">
            {fixture.home_team?.short_name ?? fixture.home_team?.name} vs{' '}
            {fixture.away_team?.short_name ?? fixture.away_team?.name}
          </span>
        )}
      </div>
      <InfinityPredictionCard
        market={pick.market_name}
        selection={String(pick.value)}
        probability={pick.probability}
        confidence={pick.confidence_composite}
        evidenceCount={pick.evidence_count}
      />
    </div>
  )
}
