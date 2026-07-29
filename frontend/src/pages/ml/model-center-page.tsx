import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Cpu } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ModelCard } from '@/components/domain/model-card'
import { TrainingPanel } from '@/components/domain/training-panel'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { FeatureImportanceBars, type FeatureContribution } from '@/components/domain/feature-importance-bar'
import { ModelEvaluationsDialog } from '@/components/domain/model-evaluations-dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { marketsApi } from '@/lib/api/markets'
import { mlPlatformApi } from '@/lib/api/ml-platform'
import { useAuthStore } from '@/stores/auth-store'
import { toast } from '@/stores/toast-store'
import type { DeploymentMode } from '@/lib/api/types'

const DEPLOYMENT_MODES: DeploymentMode[] = ['shadow', 'canary', 'full']

export default function ModelCenterPage() {
  const queryClient = useQueryClient()
  const approvedBy = useAuthStore((s) => s.profile?.email) ?? 'unknown-admin'
  const [marketKey, setMarketKey] = useState<string | undefined>()
  const [promotingId, setPromotingId] = useState<string | null>(null)

  const marketsQuery = useQuery({ queryKey: ['markets', 'list'], queryFn: () => marketsApi.list() })
  const activeMarketKey = marketKey ?? marketsQuery.data?.[0]?.market_key

  const modelsQuery = useQuery({
    queryKey: ['ml', 'models', activeMarketKey],
    queryFn: () => mlPlatformApi.listModels(activeMarketKey!),
    enabled: Boolean(activeMarketKey),
  })

  const championQuery = useQuery({
    queryKey: ['ml', 'champion', activeMarketKey],
    queryFn: () => mlPlatformApi.champion(activeMarketKey!),
    enabled: Boolean(activeMarketKey),
    retry: false,
  })

  const featureImportanceQuery = useQuery({
    queryKey: ['ml', 'featureImportance', activeMarketKey],
    queryFn: () => mlPlatformApi.featureImportance(activeMarketKey!),
    enabled: Boolean(activeMarketKey),
    retry: false,
  })

  const modelHealthQuery = useQuery({
    queryKey: ['ml', 'modelHealth', activeMarketKey],
    queryFn: () => mlPlatformApi.modelHealth(activeMarketKey!),
    enabled: Boolean(activeMarketKey),
    retry: false,
  })

  const latencyQuery = useQuery({
    queryKey: ['ml', 'latency', activeMarketKey],
    queryFn: () => mlPlatformApi.latencyStats(activeMarketKey!),
    enabled: Boolean(activeMarketKey),
    retry: false,
  })

  async function handleCheckRetraining() {
    if (!activeMarketKey) return
    try {
      const result = await mlPlatformApi.checkRetraining(activeMarketKey)
      const needsRetraining = Boolean((result as Record<string, unknown>).needs_retraining ?? (result as Record<string, unknown>).recommended)
      toast.show('Retraining check complete', JSON.stringify(result), needsRetraining ? 'warning' : 'success')
    } catch (error) {
      toast.danger('Retraining check failed', error instanceof Error ? error.message : undefined)
    }
  }

  function refetchModels() {
    void queryClient.invalidateQueries({ queryKey: ['ml', 'models', activeMarketKey] })
    void queryClient.invalidateQueries({ queryKey: ['ml', 'champion', activeMarketKey] })
  }

  async function handlePromote(modelId: string) {
    setPromotingId(modelId)
    try {
      await mlPlatformApi.promoteChampion(modelId, approvedBy)
      toast.success('Model promoted to champion')
      refetchModels()
    } catch (error) {
      toast.danger('Promotion failed', error instanceof Error ? error.message : undefined)
    } finally {
      setPromotingId(null)
    }
  }

  async function handleDeploymentMode(modelId: string, mode: DeploymentMode) {
    try {
      await mlPlatformApi.setDeploymentMode(modelId, mode)
      toast.success('Deployment mode updated', mode)
      refetchModels()
    } catch (error) {
      toast.danger('Could not update deployment mode', error instanceof Error ? error.message : undefined)
    }
  }

  return (
    <div data-dashboard-accent="ml" className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Model Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Model Center</h1>
        <p className="mt-1 text-sm text-text-secondary">Champion/Challenger registry per market.</p>
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

      {activeMarketKey && (
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>Current champion</CardTitle>
          </CardHeader>
          <CardContent>
            {championQuery.data ? (
              <div className="flex items-center gap-2 text-sm">
                <span className="font-mono text-text-primary">
                  {championQuery.data.model_key} v{championQuery.data.version}
                </span>
                <Badge variant="success">{championQuery.data.status}</Badge>
              </div>
            ) : (
              <p className="text-sm text-text-muted">No champion selected for this market yet.</p>
            )}
          </CardContent>
        </Card>
      )}

      {activeMarketKey && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Model health</CardTitle>
            </CardHeader>
            <CardContent>
              <KeyValueGrid data={(modelHealthQuery.data as Record<string, unknown>) ?? {}} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Latency</CardTitle>
            </CardHeader>
            <CardContent>
              <KeyValueGrid data={(latencyQuery.data as Record<string, unknown>) ?? {}} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Retraining</CardTitle>
              <Button variant="secondary" size="sm" onClick={handleCheckRetraining}>
                Check now
              </Button>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-text-muted">Runs the drift/staleness check for this market's champion model.</p>
            </CardContent>
          </Card>
        </div>
      )}

      {activeMarketKey && featureImportanceQuery.data && (
        <Card>
          <CardHeader>
            <CardTitle>Global feature importance</CardTitle>
          </CardHeader>
          <CardContent>
            <FeatureImportanceBars {...splitImportance(featureImportanceQuery.data.global_importance)} />
          </CardContent>
        </Card>
      )}

      {activeMarketKey && <TrainingPanel marketKey={activeMarketKey} onChampionSelected={refetchModels} />}

      {modelsQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {modelsQuery.isError && <ErrorState description="Could not load models." onRetry={() => modelsQuery.refetch()} />}

      {modelsQuery.data && modelsQuery.data.length === 0 && (
        <EmptyState
          icon={<Cpu className="h-6 w-6" />}
          title="No models trained yet"
          description="Build a dataset and select a champion above."
        />
      )}

      {modelsQuery.data && modelsQuery.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {modelsQuery.data.map((model) => (
            <div key={model.id} className="flex flex-col gap-2">
              <ModelCard model={model} />
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={model.status === 'champion'}
                  loading={promotingId === model.id}
                  onClick={() => handlePromote(model.id)}
                >
                  Promote
                </Button>
                <Select value={model.deployment_mode ?? undefined} onValueChange={(v) => handleDeploymentMode(model.id, v as DeploymentMode)}>
                  <SelectTrigger className="h-8 w-32 text-xs">
                    <SelectValue placeholder="Deploy mode" />
                  </SelectTrigger>
                  <SelectContent>
                    {DEPLOYMENT_MODES.map((mode) => (
                      <SelectItem key={mode} value={mode}>
                        {mode}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <ModelEvaluationsDialog modelId={model.id} modelKey={`${model.model_key} v${model.version}`} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function splitImportance(importance: Record<string, number>): { positive: FeatureContribution[]; negative: FeatureContribution[] } {
  const entries = Object.entries(importance).map(([feature_key, contribution]) => ({ feature_key, contribution }))
  return {
    positive: entries.filter((e) => e.contribution >= 0).sort((a, b) => b.contribution - a.contribution).slice(0, 8),
    negative: entries
      .filter((e) => e.contribution < 0)
      .sort((a, b) => a.contribution - b.contribution)
      .slice(0, 8),
  }
}
