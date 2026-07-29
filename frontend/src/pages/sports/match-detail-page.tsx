import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Sparkles } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { useSportParam } from '@/lib/hooks/use-sport'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { MarketCard } from '@/components/domain/market-card'
import { PredictionPanel } from '@/components/domain/prediction-panel'

export default function MatchDetailPage() {
  const sport = useSportParam()
  const { matchId } = useParams<{ matchId: string }>()
  const [selectedMarketKey, setSelectedMarketKey] = useState<string | null>(null)

  const fixtureQuery = useQuery({
    queryKey: ['sports', 'fixture', matchId],
    queryFn: () => sportsApi.getFixture(matchId!),
    enabled: !!matchId,
  })

  const marketsQuery = useQuery({
    queryKey: ['markets', sport?.code, 'production'],
    queryFn: () => marketsApi.list({ sport_code: sport!.code, status: 'production' }),
    enabled: !!sport,
  })

  const generatePrediction = useMutation({
    mutationFn: (marketKey: string) =>
      predictionsApi.generate({
        market_key: marketKey,
        entity_type: 'fixture',
        entity_id: matchId!,
        subject_ref: matchId!,
      }),
  })

  if (!sport) return null

  if (fixtureQuery.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40" />
      </div>
    )
  }

  if (fixtureQuery.isError) {
    return <ErrorState error={fixtureQuery.error} onRetry={() => void fixtureQuery.refetch()} />
  }

  const fixture = fixtureQuery.data
  const markets = marketsQuery.data ?? []

  function handleSelectMarket(marketKey: string) {
    setSelectedMarketKey(marketKey)
    generatePrediction.reset()
  }

  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <Link
          to={`/app/${sport.slug}/matches`}
          className="inline-flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft className="size-3.5" /> Back to matches
        </Link>
        <p className="mt-3 font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          {fixture.competition_name}
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">
          {fixture.home_team.name} vs {fixture.away_team.name}
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          {new Date(fixture.scheduled_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
          {fixture.venue_name && ` · ${fixture.venue_name}`} · {fixture.status}
        </p>
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-accent-primary" aria-hidden="true" />
          <p className="font-display text-base font-semibold text-text-primary">Prediction Laboratory</p>
        </div>
        <p className="mt-1 text-sm text-text-secondary">
          Choose a market to generate TitanIQ's prediction for this match, with full confidence and evidence.
        </p>

        {marketsQuery.isPending && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        )}

        {marketsQuery.isError && <ErrorState error={marketsQuery.error} onRetry={() => void marketsQuery.refetch()} />}

        {markets.length === 0 && !marketsQuery.isPending && !marketsQuery.isError && (
          <EmptyState title="No production markets yet" description={`No ${sport.label} markets have reached production.`} />
        )}

        {markets.length > 0 && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {markets.map((market) => (
              <MarketCard
                key={market.id}
                market={market}
                selected={selectedMarketKey === market.market_key}
                onSelect={() => handleSelectMarket(market.market_key)}
              />
            ))}
          </div>
        )}

        {selectedMarketKey && !generatePrediction.data && (
          <Button
            className="mt-4"
            onClick={() => generatePrediction.mutate(selectedMarketKey)}
            disabled={generatePrediction.isPending}
          >
            {generatePrediction.isPending ? 'Generating…' : 'Generate prediction'}
          </Button>
        )}

        {generatePrediction.isError && (
          <div className="mt-4">
            <ErrorState error={generatePrediction.error} onRetry={() => generatePrediction.mutate(selectedMarketKey!)} />
          </div>
        )}

        {generatePrediction.data && (
          <div className="mt-5">
            <PredictionPanel prediction={generatePrediction.data} />
          </div>
        )}
      </Card>
    </div>
  )
}
