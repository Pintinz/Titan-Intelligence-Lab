import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { ExperimentCard } from '@/components/domain/experiment-card'
import { BenchmarkForm } from '@/components/domain/benchmark-form'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { marketsApi } from '@/lib/api/markets'
import { mlPlatformApi } from '@/lib/api/ml-platform'
import { toast } from '@/stores/toast-store'

export default function ExperimentCenterPage() {
  const queryClient = useQueryClient()
  const [marketKey, setMarketKey] = useState<string | undefined>()
  const [decidingId, setDecidingId] = useState<string | null>(null)
  const marketsQuery = useQuery({ queryKey: ['markets', 'list'], queryFn: () => marketsApi.list() })
  const activeMarketKey = marketKey ?? marketsQuery.data?.[0]?.market_key

  const experimentsQuery = useQuery({
    queryKey: ['ml', 'experiments', activeMarketKey],
    queryFn: () => mlPlatformApi.listExperiments(activeMarketKey!),
    enabled: Boolean(activeMarketKey),
  })

  async function handleDecide(experimentId: string, decision: 'accepted' | 'rejected') {
    setDecidingId(experimentId)
    try {
      await mlPlatformApi.decideExperiment(experimentId, decision)
      toast.success(`Experiment ${decision}`)
      void queryClient.invalidateQueries({ queryKey: ['ml', 'experiments', activeMarketKey] })
    } catch (error) {
      toast.danger('Could not record decision', error instanceof Error ? error.message : undefined)
    } finally {
      setDecidingId(null)
    }
  }

  return (
    <div data-dashboard-accent="ml" className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Experiment Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Experiment Center</h1>
      </div>

      <Select value={activeMarketKey} onValueChange={setMarketKey}>
        <SelectTrigger className="w-72">
          <SelectValue placeholder="Select a market" />
        </SelectTrigger>
        <SelectContent>
          {marketsQuery.data?.map((market) => (
            <SelectItem key={market.id} value={market.market_key}>
              {market.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {activeMarketKey && <BenchmarkForm marketKey={activeMarketKey} />}

      {experimentsQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {experimentsQuery.isError && (
        <ErrorState description="Could not load experiments." onRetry={() => experimentsQuery.refetch()} />
      )}

      {experimentsQuery.data && experimentsQuery.data.length === 0 && (
        <EmptyState icon={<FlaskConical className="h-6 w-6" />} title="No experiments recorded yet" />
      )}

      {experimentsQuery.data && experimentsQuery.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {experimentsQuery.data.map((experiment) => (
            <div key={experiment.id} className="flex flex-col gap-2">
              <ExperimentCard experiment={experiment} />
              {!experiment.decision && (
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={decidingId === experiment.id}
                    onClick={() => handleDecide(experiment.id, 'accepted')}
                  >
                    Accept
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    loading={decidingId === experiment.id}
                    onClick={() => handleDecide(experiment.id, 'rejected')}
                  >
                    Reject
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
