import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Cpu, Crown, Swords, FlaskConical, Gauge, RotateCw, BrainCircuit } from 'lucide-react'
import { mlPlatformApi } from '@/lib/api/ml-platform'
import { marketsApi } from '@/lib/api/markets'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { OpsPageHeader, SectionCard, TelemetryBarChart } from '@/components/ops/ops-primitives'
import { toast } from '@/stores/toast-store'

export default function MlOperationsPage() {
  const [marketId, setMarketId] = useState('')
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const marketsQuery = useQuery({ queryKey: ['markets', 'all'], queryFn: () => marketsApi.list() })
  const market = marketsQuery.data?.find((m) => m.id === marketId)
  const marketKey = market?.market_key

  const championQuery = useQuery({
    queryKey: ['ml', 'champion', marketKey],
    queryFn: () => mlPlatformApi.champion(marketKey!),
    enabled: !!marketKey,
    retry: false,
  })
  const modelsQuery = useQuery({
    queryKey: ['ml', 'models', marketKey],
    queryFn: () => mlPlatformApi.listModels(marketKey!),
    enabled: !!marketKey,
  })
  const experimentsQuery = useQuery({
    queryKey: ['ml', 'experiments', marketKey],
    queryFn: () => mlPlatformApi.listExperiments(marketKey!),
    enabled: !!marketKey,
  })
  const featureImportanceQuery = useQuery({
    queryKey: ['ml', 'feature-importance', marketKey],
    queryFn: () => mlPlatformApi.featureImportance(marketKey!),
    enabled: !!marketKey,
    retry: false,
  })
  const modelHealthQuery = useQuery({
    queryKey: ['ml', 'model-health', marketKey],
    queryFn: () => mlPlatformApi.modelHealth(marketKey!),
    enabled: !!marketKey,
  })
  const latencyQuery = useQuery({
    queryKey: ['ml', 'latency', marketKey],
    queryFn: () => mlPlatformApi.latencyStats(marketKey!),
    enabled: !!marketKey,
  })
  const evaluationsQuery = useQuery({
    queryKey: ['ml', 'evaluations', selectedModelId],
    queryFn: () => mlPlatformApi.listEvaluations(selectedModelId!),
    enabled: !!selectedModelId,
  })
  const comparisonQuery = useQuery({
    queryKey: ['ml', 'comparison', marketKey],
    queryFn: () => mlPlatformApi.latestComparison(marketKey!),
    enabled: !!marketKey,
  })
  const marketRankingQuery = useQuery({
    queryKey: ['ml', 'market-ranking'],
    queryFn: () => mlPlatformApi.marketPerformanceRanking(),
  })
  const featureFailuresQuery = useQuery({
    queryKey: ['ml', 'feature-failures', marketKey],
    queryFn: () => mlPlatformApi.featureFailures(marketKey!),
    enabled: !!marketKey,
  })
  const overconfidenceQuery = useQuery({
    queryKey: ['ml', 'overconfidence', marketKey],
    queryFn: () => mlPlatformApi.overconfidence(marketKey!),
    enabled: !!marketKey,
  })

  const promote = useMutation({
    mutationFn: (modelId: string) => mlPlatformApi.promoteChampion(modelId, 'ops-console'),
    onSuccess: () => {
      toast.success('Champion promotion requested')
      void queryClient.invalidateQueries({ queryKey: ['ml', 'champion', marketKey] })
      void queryClient.invalidateQueries({ queryKey: ['ml', 'models', marketKey] })
    },
    onError: (error) => toast.danger('Could not promote model', error instanceof Error ? error.message : undefined),
  })

  const checkRetraining = useMutation({
    mutationFn: () => mlPlatformApi.checkRetraining(marketKey!),
    onSuccess: (data) => toast.success('Retraining check complete', JSON.stringify(data).slice(0, 120)),
    onError: (error) => toast.danger('Retraining check failed', error instanceof Error ? error.message : undefined),
  })

  const importanceData = featureImportanceQuery.data
    ? Object.entries(featureImportanceQuery.data.global_importance)
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
        .slice(0, 12)
        .map(([x, y]) => ({ x, y }))
    : []

  const models = modelsQuery.data ?? []
  const challengers = models.filter((m) => m.id !== championQuery.data?.id)

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="ML Platform"
        title="ML Operations"
        description="Champion/challenger models, experiments, calibration, feature importance, and monitoring for every market's prediction model."
      />

      <SectionCard icon={Cpu} title="Select a market">
        <Select value={marketId} onValueChange={(v) => { setMarketId(v); setSelectedModelId(null) }}>
          <SelectTrigger className="w-64" aria-label="Market"><SelectValue placeholder="Choose a market" /></SelectTrigger>
          <SelectContent>
            {(marketsQuery.data ?? []).map((m) => (
              <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </SectionCard>

      {marketKey && (
        <Tabs defaultValue="models">
          <TabsList>
            <TabsTrigger value="models">Champion & Challengers</TabsTrigger>
            <TabsTrigger value="experiments">Experiments</TabsTrigger>
            <TabsTrigger value="importance">Feature Importance</TabsTrigger>
            <TabsTrigger value="monitoring">Monitoring</TabsTrigger>
            <TabsTrigger value="error-memory">Error Memory</TabsTrigger>
          </TabsList>

          <TabsContent value="models" className="space-y-4">
            <SectionCard icon={Crown} title="Champion model" description="Currently deployed production model for this market.">
              {championQuery.isPending && <Skeleton className="h-16" />}
              {championQuery.isError && (
                <EmptyState variant="minimal" title="No champion selected yet" description="Run champion selection once training data is available." />
              )}
              {championQuery.data && (
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-telemetry text-sm text-text-primary">{championQuery.data.model_key} v{championQuery.data.version}</p>
                    <p className="text-xs text-text-muted">{championQuery.data.id}</p>
                  </div>
                  <Badge variant="success">{championQuery.data.status}</Badge>
                </div>
              )}
            </SectionCard>

            <SectionCard icon={Swords} title="Challenger models" description="All non-champion models registered for this market.">
              {modelsQuery.isPending && <Skeleton className="h-24" />}
              {modelsQuery.isError && <ErrorState error={modelsQuery.error} onRetry={() => void modelsQuery.refetch()} />}
              {modelsQuery.isSuccess && challengers.length === 0 && (
                <p className="text-sm text-text-secondary">No challenger models registered.</p>
              )}
              {challengers.length > 0 && (
                <ul className="space-y-2">
                  {challengers.map((m) => (
                    <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border-default p-3">
                      <button type="button" onClick={() => setSelectedModelId(m.id)} className="text-left">
                        <p className="font-telemetry text-sm text-text-primary">{m.model_key} v{m.version}</p>
                        <p className="text-xs text-text-muted">{m.algorithm} · {m.framework} · {m.status}</p>
                      </button>
                      <Button size="sm" variant="secondary" onClick={() => promote.mutate(m.id)} disabled={promote.isPending}>
                        {promote.isPending ? 'Promoting…' : 'Promote to champion'}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>

            {selectedModelId && (
              <SectionCard icon={Gauge} title="Evaluation history" description={`Recent evaluations for ${selectedModelId}`}>
                {evaluationsQuery.isPending && <Skeleton className="h-20" />}
                {evaluationsQuery.isError && <ErrorState error={evaluationsQuery.error} onRetry={() => void evaluationsQuery.refetch()} />}
                {evaluationsQuery.data && evaluationsQuery.data.length === 0 && (
                  <p className="text-sm text-text-secondary">No evaluations recorded for this model yet.</p>
                )}
                {evaluationsQuery.data && evaluationsQuery.data.length > 0 && (
                  <div className="space-y-3">
                    {evaluationsQuery.data.slice(0, 5).map((ev) => (
                      <div key={ev.id} className="rounded-md border border-border-subtle p-3">
                        <p className="mb-1.5 font-mono text-[11px] text-text-muted">{new Date(ev.evaluated_at).toLocaleString()}</p>
                        <KeyValueGrid data={ev.metrics} />
                      </div>
                    ))}
                  </div>
                )}
              </SectionCard>
            )}
          </TabsContent>

          <TabsContent value="experiments">
            <SectionCard icon={FlaskConical} title="Experiments" description="Training experiments and their decisions for this market.">
              {experimentsQuery.isPending && <Skeleton className="h-24" />}
              {experimentsQuery.isError && <ErrorState error={experimentsQuery.error} onRetry={() => void experimentsQuery.refetch()} />}
              {experimentsQuery.data && experimentsQuery.data.length === 0 && (
                <EmptyState variant="minimal" title="No experiments yet" description="Experiments appear here once training runs are logged." />
              )}
              {experimentsQuery.data && experimentsQuery.data.length > 0 && (
                <ul className="space-y-2">
                  {experimentsQuery.data.map((exp) => (
                    <li key={exp.id} className="rounded-md border border-border-default p-3">
                      <div className="mb-2 flex items-center justify-between">
                        <p className="font-mono text-xs text-text-muted">{exp.id}</p>
                        <Badge variant={exp.decision ? 'success' : 'neutral'}>{exp.decision ?? 'pending'}</Badge>
                      </div>
                      <KeyValueGrid data={exp.metrics} />
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>
          </TabsContent>

          <TabsContent value="importance">
            <SectionCard
              icon={Gauge}
              title="Feature importance"
              description="Global feature contribution (SHAP-derived) driving this market's champion model."
            >
              {featureImportanceQuery.isPending && <Skeleton className="h-56" />}
              {featureImportanceQuery.isError && (
                <EmptyState variant="minimal" title="No feature importance available" description="Feature importance is computed once a champion model exists." />
              )}
              {importanceData.length > 0 && <TelemetryBarChart data={importanceData} dataKey="y" height={260} />}
            </SectionCard>
          </TabsContent>

          <TabsContent value="monitoring" className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <SectionCard icon={Gauge} title="Model health">
                {modelHealthQuery.isPending && <Skeleton className="h-16" />}
                {modelHealthQuery.isError && <ErrorState error={modelHealthQuery.error} onRetry={() => void modelHealthQuery.refetch()} />}
                {modelHealthQuery.data && <KeyValueGrid data={modelHealthQuery.data} />}
              </SectionCard>
              <SectionCard icon={Gauge} title="Inference latency">
                {latencyQuery.isPending && <Skeleton className="h-16" />}
                {latencyQuery.isError && <ErrorState error={latencyQuery.error} onRetry={() => void latencyQuery.refetch()} />}
                {latencyQuery.data && <KeyValueGrid data={latencyQuery.data} />}
              </SectionCard>
            </div>
            <SectionCard icon={RotateCw} title="Retraining">
              <p className="mb-3 text-sm text-text-secondary">
                Check whether this market's model meets the criteria for scheduled retraining (drift, staleness, or performance decay).
              </p>
              <Button size="sm" onClick={() => checkRetraining.mutate()} disabled={checkRetraining.isPending} className="gap-1">
                <RotateCw className="size-3.5" /> {checkRetraining.isPending ? 'Checking…' : 'Run retraining check'}
              </Button>
            </SectionCard>

            <SectionCard
              icon={Swords}
              title="Challenger vs. Champion"
              description="The Continuous Outcome Learning Engine's most recent automated comparison — what a Promote to champion decision above should confirm, not re-derive by hand."
            >
              {comparisonQuery.isPending && <Skeleton className="h-24" />}
              {comparisonQuery.isError && <ErrorState error={comparisonQuery.error} onRetry={() => void comparisonQuery.refetch()} />}
              {comparisonQuery.isSuccess && !comparisonQuery.data && (
                <EmptyState
                  variant="minimal"
                  title="No comparison recorded yet"
                  description="A comparison runs automatically the next time a scheduled retrain finds enough new outcomes to score a Challenger against this market's live Champion."
                />
              )}
              {comparisonQuery.data && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Badge
                      variant={
                        comparisonQuery.data.verdict === 'challenger_better' ? 'success'
                        : comparisonQuery.data.verdict === 'champion_better' ? 'danger' : 'neutral'
                      }
                    >
                      {comparisonQuery.data.verdict === 'challenger_better' ? 'Challenger better'
                        : comparisonQuery.data.verdict === 'champion_better' ? 'Champion better — challenger auto-retired'
                        : 'Inconclusive'}
                    </Badge>
                    <p className="text-xs text-text-muted">
                      decided by {comparisonQuery.data.decisive_metric} · {comparisonQuery.data.holdout_sample_count} holdout samples ·{' '}
                      {new Date(comparisonQuery.data.evaluated_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-md border border-border-subtle p-3">
                      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">Challenger</p>
                      <KeyValueGrid
                        data={Object.fromEntries(
                          Object.entries(comparisonQuery.data.challenger_metrics).filter(([, v]) => v !== null),
                        )}
                      />
                    </div>
                    <div className="rounded-md border border-border-subtle p-3">
                      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">Champion</p>
                      {comparisonQuery.data.champion_metrics ? (
                        <KeyValueGrid
                          data={Object.fromEntries(
                            Object.entries(comparisonQuery.data.champion_metrics).filter(([, v]) => v !== null),
                          )}
                        />
                      ) : (
                        <p className="text-sm text-text-secondary">No champion at comparison time.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </SectionCard>
          </TabsContent>

          <TabsContent value="error-memory" className="space-y-4">
            <SectionCard
              icon={BrainCircuit}
              title="Market performance ranking"
              description="Every market, best real accuracy/mean error first — real PredictionOutcome history, not a fabricated leaderboard."
            >
              {marketRankingQuery.isPending && <Skeleton className="h-32" />}
              {marketRankingQuery.isError && <ErrorState error={marketRankingQuery.error} onRetry={() => void marketRankingQuery.refetch()} />}
              {marketRankingQuery.data && marketRankingQuery.data.length === 0 && (
                <EmptyState variant="minimal" title="No markets yet" description="Rankings appear once markets exist." />
              )}
              {marketRankingQuery.data && marketRankingQuery.data.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border-subtle text-left text-xs uppercase tracking-wide text-text-muted">
                        <th className="py-2 pr-4">Market</th>
                        <th className="py-2 pr-4">Samples</th>
                        <th className="py-2 pr-4">Accuracy</th>
                        <th className="py-2 pr-4">Mean error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {marketRankingQuery.data.map((m) => (
                        <tr key={m.market_id} className="border-b border-border-subtle/50">
                          <td className="py-2 pr-4 font-telemetry text-text-primary">{m.market_key}</td>
                          <td className="py-2 pr-4 text-text-secondary">{m.sample_count}</td>
                          <td className="py-2 pr-4 text-text-secondary">{m.accuracy !== null ? `${(m.accuracy * 100).toFixed(1)}%` : '—'}</td>
                          <td className="py-2 pr-4 text-text-secondary">{m.mean_error !== null ? m.mean_error.toFixed(3) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>

            {marketKey && (
              <div className="grid gap-4 lg:grid-cols-2">
                <SectionCard icon={Gauge} title="Overconfidence" description="Stated probability vs. real outcome for this market.">
                  {overconfidenceQuery.isPending && <Skeleton className="h-16" />}
                  {overconfidenceQuery.isError && <ErrorState error={overconfidenceQuery.error} onRetry={() => void overconfidenceQuery.refetch()} />}
                  {overconfidenceQuery.data && overconfidenceQuery.data.sample_count === 0 && (
                    <EmptyState variant="minimal" title="No resolved outcomes yet" description="This market has no real outcome history to score against." />
                  )}
                  {overconfidenceQuery.data && overconfidenceQuery.data.sample_count > 0 && (
                    <KeyValueGrid
                      data={{
                        sample_count: overconfidenceQuery.data.sample_count,
                        mean_predicted_probability: overconfidenceQuery.data.mean_predicted_probability,
                        mean_actual_positive_rate: overconfidenceQuery.data.mean_actual_positive_rate,
                        overconfidence_score: overconfidenceQuery.data.overconfidence_score,
                        expected_calibration_error: overconfidenceQuery.data.expected_calibration_error,
                      }}
                    />
                  )}
                </SectionCard>
                <SectionCard icon={Gauge} title="Feature/failure association" description="Features whose average value diverges most between correct and incorrect predictions.">
                  {featureFailuresQuery.isPending && <Skeleton className="h-32" />}
                  {featureFailuresQuery.isError && <ErrorState error={featureFailuresQuery.error} onRetry={() => void featureFailuresQuery.refetch()} />}
                  {featureFailuresQuery.data && featureFailuresQuery.data.length === 0 && (
                    <EmptyState variant="minimal" title="No resolved outcomes yet" description="Feature/failure divergence needs real correct and incorrect predictions to compare." />
                  )}
                  {featureFailuresQuery.data && featureFailuresQuery.data.length > 0 && (
                    <ul className="space-y-1.5">
                      {featureFailuresQuery.data.slice(0, 8).map((f) => (
                        <li key={f.feature_key} className="flex items-center justify-between text-sm">
                          <span className="font-telemetry text-text-primary">{f.feature_key}</span>
                          <span className="font-mono text-xs text-text-muted">
                            correct {f.correct_mean?.toFixed(2) ?? '—'} · incorrect {f.incorrect_mean?.toFixed(2) ?? '—'} · Δ {f.divergence?.toFixed(2) ?? '—'}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </SectionCard>
              </div>
            )}
          </TabsContent>
        </Tabs>
      )}

      <p className="text-xs text-text-muted">
        ROC/precision/recall/F1/log-loss are exposed inside each evaluation's <code>metrics</code> object above when
        the training pipeline records them — TitanIQ has no separate endpoint per metric. Calibration reports
        (Brier score, reliability curve) are generated on demand from prediction/outcome samples rather than stored
        per model; wire a "generate calibration report" action here once a canonical sample source is decided.
      </p>
    </div>
  )
}
