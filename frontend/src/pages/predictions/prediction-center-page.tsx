import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Button } from '@/components/ui/button'
import { PredictionCard } from '@/components/domain/prediction-card'
import { PredictionComparisonPanel } from '@/components/domain/prediction-comparison-panel'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { useRealtimeInvalidate } from '@/lib/hooks/use-realtime-invalidate'
import { Gauge, Scale } from 'lucide-react'

export default function PredictionCenterPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const marketKeyParam = searchParams.get('market')
  const [compareMode, setCompareMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [comparing, setComparing] = useState(false)

  const marketsQuery = useQuery({ queryKey: ['markets', 'list'], queryFn: () => marketsApi.list({ status: 'production' }) })
  const markets = marketsQuery.data ?? []

  const selectedMarket = useMemo(
    () => markets.find((m) => m.market_key === marketKeyParam) ?? markets[0],
    [markets, marketKeyParam],
  )

  const predictionsQuery = useQuery({
    queryKey: ['predictions', 'byMarket', selectedMarket?.id],
    queryFn: () => predictionsApi.list(selectedMarket!.id, { limit: 50 }),
    enabled: Boolean(selectedMarket),
  })

  useRealtimeInvalidate('predictions', [['predictions', 'byMarket', selectedMarket?.id]])

  function toggleSelected(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id]))
  }

  function toggleCompareMode() {
    setCompareMode((prev) => !prev)
    setSelectedIds([])
  }

  return (
    <div data-dashboard-accent="prediction" className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Prediction Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Prediction Center</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Calibrated, explainable predictions across every production market.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={selectedMarket?.market_key}
          onValueChange={(value) => setSearchParams({ market: value })}
        >
          <SelectTrigger className="w-72">
            <SelectValue placeholder="Select a market" />
          </SelectTrigger>
          <SelectContent>
            {markets.map((market) => (
              <SelectItem key={market.id} value={market.market_key}>
                {market.name} · {market.sport_code}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant={compareMode ? 'primary' : 'secondary'} size="sm" onClick={toggleCompareMode}>
          <Scale className="h-3.5 w-3.5" aria-hidden="true" />
          {compareMode ? 'Exit compare' : 'Compare predictions'}
        </Button>
        {compareMode && (
          <Button size="sm" disabled={selectedIds.length < 2} onClick={() => setComparing(true)}>
            Compare selected ({selectedIds.length})
          </Button>
        )}
      </div>

      {predictionsQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      )}

      {predictionsQuery.isError && (
        <ErrorState description="Could not load predictions for this market." onRetry={() => predictionsQuery.refetch()} />
      )}

      {predictionsQuery.data && predictionsQuery.data.length === 0 && (
        <EmptyState
          icon={<Gauge className="h-6 w-6" />}
          title="No predictions yet"
          description="This market has no generated predictions in the current window."
        />
      )}

      {predictionsQuery.data && predictionsQuery.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {predictionsQuery.data.map((prediction) => (
            <PredictionCard
              key={prediction.id}
              prediction={prediction}
              selectable={compareMode}
              selected={selectedIds.includes(prediction.id)}
              onToggleSelect={() => toggleSelected(prediction.id)}
            />
          ))}
        </div>
      )}

      <PredictionComparisonPanel
        open={comparing}
        onOpenChange={setComparing}
        predictionIds={selectedIds}
      />
    </div>
  )
}
