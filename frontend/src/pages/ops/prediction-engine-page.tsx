import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Target, Download, RotateCcw, BellRing, ListFilter } from 'lucide-react'
import { adminPredictionsApi } from '@/lib/api/admin-predictions'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { overallConfidence } from '@/components/domain/prediction-panel'
import { OpsPageHeader, SectionCard } from '@/components/ops/ops-primitives'
import { toast } from '@/stores/toast-store'

export default function PredictionEnginePage() {
  const [marketId, setMarketId] = useState('')

  const marketsQuery = useQuery({ queryKey: ['markets', 'all'], queryFn: () => marketsApi.list() })
  const marketsHealthQuery = useQuery({ queryKey: ['admin', 'markets-health'], queryFn: () => adminPredictionsApi.marketsHealth() })
  const alertsQuery = useQuery({ queryKey: ['admin', 'prediction-alerts'], queryFn: () => adminPredictionsApi.alerts() })

  const market = marketsQuery.data?.find((m) => m.id === marketId)

  const confidenceQuery = useQuery({
    queryKey: ['admin', 'predictions', market?.market_key, 'confidence'],
    queryFn: () => adminPredictionsApi.marketConfidence(market!.market_key),
    enabled: !!market,
  })
  const accuracyQuery = useQuery({
    queryKey: ['admin', 'predictions', market?.market_key, 'accuracy'],
    queryFn: () => adminPredictionsApi.marketAccuracy(market!.market_key),
    enabled: !!market,
  })
  const driftQuery = useQuery({
    queryKey: ['admin', 'predictions', market?.market_key, 'drift'],
    queryFn: () => adminPredictionsApi.marketDrift(market!.market_key),
    enabled: !!market,
  })
  const predictionsQuery = useQuery({
    queryKey: ['predictions', 'by-market', marketId],
    queryFn: () => predictionsApi.list(marketId, { limit: 25 }),
    enabled: !!marketId,
  })

  const regenerate = useMutation({
    mutationFn: () =>
      adminPredictionsApi.regenerate({
        market_key: market!.market_key,
        entity_type: 'fixture',
        entity_id: 'ops-console-test',
        subject_ref: 'ops-console-test',
      }),
    onSuccess: () => toast.success('Prediction regenerated'),
    onError: (error) => toast.danger('Could not regenerate prediction', error instanceof Error ? error.message : undefined),
  })

  const rollback = useMutation({
    mutationFn: () => adminPredictionsApi.rollbackModel(marketId),
    onSuccess: () => toast.success('Model rollback initiated'),
    onError: (error) => toast.danger('Could not roll back model', error instanceof Error ? error.message : undefined),
  })

  function exportMarket() {
    if (!market) return
    adminPredictionsApi
      .exportMarket(market.market_key)
      .then((rows) => {
        const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${market.market_key}-predictions.json`
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch((error: unknown) => toast.danger('Export failed', error instanceof Error ? error.message : undefined))
  }

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Predictions"
        title="Prediction Engine"
        description="Market coverage, confidence and accuracy tracking, drift monitoring, and prediction search across every TitanIQ market."
      />

      <SectionCard icon={Target} title="Markets health" description="Coverage and health across every registered prediction market.">
        {marketsHealthQuery.isPending && <Skeleton className="h-16" />}
        {marketsHealthQuery.isError && <ErrorState error={marketsHealthQuery.error} onRetry={() => void marketsHealthQuery.refetch()} />}
        {marketsHealthQuery.data && <KeyValueGrid data={marketsHealthQuery.data} />}
      </SectionCard>

      <SectionCard
        icon={ListFilter}
        title="Inspect a market"
        description="Select a market to see confidence, accuracy, drift, and its recent predictions."
      >
        <Select value={marketId} onValueChange={setMarketId}>
          <SelectTrigger className="w-64" aria-label="Market"><SelectValue placeholder="Choose a market" /></SelectTrigger>
          <SelectContent>
            {(marketsQuery.data ?? []).map((m) => (
              <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {market && (
          <div className="mt-5 space-y-5">
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Confidence</p>
                {confidenceQuery.isPending && <Skeleton className="h-16" />}
                {confidenceQuery.data && <KeyValueGrid data={confidenceQuery.data} />}
              </div>
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Accuracy</p>
                {accuracyQuery.isPending && <Skeleton className="h-16" />}
                {accuracyQuery.data && <KeyValueGrid data={accuracyQuery.data} />}
              </div>
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Drift</p>
                {driftQuery.isPending && <Skeleton className="h-16" />}
                {driftQuery.data && <KeyValueGrid data={driftQuery.data} />}
              </div>
            </div>

            <div className="flex flex-wrap gap-2 border-t border-border-subtle pt-4">
              <Button size="sm" variant="secondary" onClick={exportMarket} className="gap-1">
                <Download className="size-3.5" /> Export predictions
              </Button>
              <Button size="sm" variant="secondary" onClick={() => regenerate.mutate()} disabled={regenerate.isPending} className="gap-1">
                <RotateCcw className="size-3.5" /> {regenerate.isPending ? 'Regenerating…' : 'Regenerate test prediction'}
              </Button>
              <Button size="sm" variant="danger" onClick={() => rollback.mutate()} disabled={rollback.isPending} className="gap-1">
                {rollback.isPending ? 'Rolling back…' : 'Rollback model'}
              </Button>
            </div>

            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Recent predictions</p>
              {predictionsQuery.isPending && <Skeleton className="h-24" />}
              {predictionsQuery.isError && <ErrorState error={predictionsQuery.error} onRetry={() => void predictionsQuery.refetch()} />}
              {predictionsQuery.data && predictionsQuery.data.length === 0 && (
                <EmptyState variant="minimal" title="No predictions for this market yet" />
              )}
              {predictionsQuery.data && predictionsQuery.data.length > 0 && (
                <ul className="space-y-1.5">
                  {predictionsQuery.data.map((p) => (
                    <li key={p.id} className="flex items-center justify-between gap-3 rounded-md border border-border-default p-2.5">
                      <div className="min-w-0">
                        <p className="truncate font-telemetry text-sm text-text-primary">{String(p.value)}</p>
                        <p className="truncate font-mono text-[11px] text-text-muted">{p.subject_ref} · {p.status}</p>
                      </div>
                      <ConfidenceTelemetry confidence={overallConfidence(p.confidence)} size="sm" />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </SectionCard>

      <SectionCard icon={BellRing} title="Prediction alerts" description="Active alerts raised by the prediction monitoring pipeline.">
        {alertsQuery.isPending && <Skeleton className="h-16" />}
        {alertsQuery.isError && <ErrorState error={alertsQuery.error} onRetry={() => void alertsQuery.refetch()} />}
        {alertsQuery.data && alertsQuery.data.length === 0 && <p className="text-sm text-text-secondary">No active alerts.</p>}
        {alertsQuery.data && alertsQuery.data.length > 0 && (
          <ul className="space-y-2">
            {alertsQuery.data.map((alert, i) => (
              <li key={i} className="rounded-md border border-warning/30 bg-warning-muted p-2.5">
                <KeyValueGrid data={alert as Record<string, unknown>} />
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  )
}
