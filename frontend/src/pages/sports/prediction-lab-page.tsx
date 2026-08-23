import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { FlaskConical } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi, REWARDED_AD_CREDIT_GRANT } from '@/lib/api/predictions'
import { ApiError } from '@/lib/api/client'
import { useSportParam } from '@/lib/hooks/use-sport'
import { usePredictionEntitlement, useInvalidatePredictionEntitlement } from '@/lib/hooks/use-prediction-entitlement'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { MarketCard } from '@/components/domain/market-card'
import { PredictionPanel } from '@/components/domain/prediction-panel'

/**
 * The workbench: pick a production market, pick a fixture, generate a real prediction. This is
 * the general form of what Match Intelligence offers pre-scoped to one match.
 */
export default function PredictionLabPage() {
  const sport = useSportParam()
  const [selectedMarketKey, setSelectedMarketKey] = useState<string | null>(null)
  const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(null)

  const marketsQuery = useQuery({
    queryKey: ['markets', sport?.code, 'production'],
    queryFn: () => marketsApi.list({ sport_code: sport!.code, status: 'production' }),
    enabled: !!sport,
  })
  const fixturesQuery = useQuery({
    queryKey: ['sports', 'fixtures', sport?.code, 'lab'],
    queryFn: () => sportsApi.listFixtures(sport!.code, { limit: 30 }),
    enabled: !!sport,
  })
  const entitlement = usePredictionEntitlement()
  const invalidateEntitlement = useInvalidatePredictionEntitlement()

  const generatePrediction = useMutation({
    onSettled: invalidateEntitlement,
    mutationFn: () =>
      predictionsApi.generate({
        market_key: selectedMarketKey!,
        entity_type: 'fixture',
        entity_id: selectedFixtureId!,
        subject_ref: selectedFixtureId!,
        include_contextual_review: true,
        // Sports-Analyst Explainability is football-specific (attribution translated into
        // football-analyst language) — requesting it for another sport would just degrade to
        // "unavailable" server-side, so skip the extra Gemini round trip entirely.
        include_football_explanation: sport?.code === 'football',
      }),
  })

  if (!sport) return null

  const markets = marketsQuery.data ?? []
  const fixtures = fixturesQuery.data ?? []
  const selectedFixture = fixtures.find((f) => f.id === selectedFixtureId)

  return (
    <div className="max-w-4xl space-y-8">
      <div className="flex items-center gap-2">
        <FlaskConical className="size-5 text-accent-primary" aria-hidden="true" />
        <div>
          <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
            Prediction Laboratory
          </p>
          <h2 className="font-display text-lg font-semibold text-text-primary">{sport.label} market explorer</h2>
        </div>
      </div>

      <div>
        <p className="mb-3 text-sm font-medium text-text-primary">1. Choose a market</p>
        {marketsQuery.isPending && (
          <div className="grid gap-3 sm:grid-cols-2">
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
          <div className="grid gap-3 sm:grid-cols-2">
            {markets.map((market) => (
              <MarketCard
                key={market.id}
                market={market}
                selected={selectedMarketKey === market.market_key}
                onSelect={() => {
                  setSelectedMarketKey(market.market_key)
                  generatePrediction.reset()
                }}
              />
            ))}
          </div>
        )}
      </div>

      {selectedMarketKey && (
        <div>
          <p className="mb-3 text-sm font-medium text-text-primary">2. Choose a match</p>
          {fixturesQuery.isPending && <Skeleton className="h-9 w-72" />}
          {fixtures.length > 0 && (
            <Select
              value={selectedFixtureId ?? undefined}
              onValueChange={(v) => {
                setSelectedFixtureId(v)
                generatePrediction.reset()
              }}
            >
              <SelectTrigger className="w-full sm:w-96">
                <SelectValue placeholder="Select a match" />
              </SelectTrigger>
              <SelectContent>
                {fixtures.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.home_team.name} vs {f.away_team.name} — {f.competition_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      )}

      {selectedMarketKey && selectedFixtureId && (
        <div>
          <p className="mb-3 text-sm font-medium text-text-primary">3. Generate</p>
          {!generatePrediction.data && (
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => generatePrediction.mutate()} disabled={generatePrediction.isPending}>
                {generatePrediction.isPending ? 'Generating…' : 'Generate prediction'}
              </Button>
              {entitlement.data && (
                <span className="text-xs text-text-muted">
                  {entitlement.data.available_predictions} prediction{entitlement.data.available_predictions === 1 ? '' : 's'} remaining
                </span>
              )}
            </div>
          )}
          {generatePrediction.isError &&
            (generatePrediction.error instanceof ApiError &&
            generatePrediction.error.status === 402 &&
            generatePrediction.error.reasonCode === 'PREDICTION_CREDIT_REQUIRED' ? (
              <Card className="mt-4 p-4">
                <p className="text-sm text-text-primary">Prediction access exhausted.</p>
                <p className="mt-1 text-xs text-text-muted">
                  Rewarded video unlocks (+{REWARDED_AD_CREDIT_GRANT} predictions) are available in the TitanIQ mobile app —
                  AdMob rewarded ads don&apos;t play inside this web admin console.
                </p>
              </Card>
            ) : (
              <div className="mt-4">
                <ErrorState error={generatePrediction.error} onRetry={() => generatePrediction.mutate()} />
              </div>
            ))}
          {generatePrediction.data && (
            <Card className="mt-4 p-5">
              <PredictionPanel
                prediction={generatePrediction.data}
                homeTeam={selectedFixture ? { name: selectedFixture.home_team.name, logoUrl: selectedFixture.home_team.logo_url } : undefined}
                awayTeam={selectedFixture ? { name: selectedFixture.away_team.name, logoUrl: selectedFixture.away_team.logo_url } : undefined}
              />
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
