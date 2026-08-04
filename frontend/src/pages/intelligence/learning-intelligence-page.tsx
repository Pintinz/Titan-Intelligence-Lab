import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, ShieldCheck, Crown, History, Gauge, BarChart3 } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { marketsApi } from '@/lib/api/markets'
import { mlPlatformApi } from '@/lib/api/ml-platform'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { ApiError } from '@/lib/api/client'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { InfinityPanel, InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinityButton } from '@/components/infinity/primitives/button'
import { InfinityBadge } from '@/components/infinity/primitives/badge'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityConfidenceRing } from '@/components/infinity/charts/confidence-ring'

const PIPELINE = [
  { title: 'Prediction Validation', detail: 'Every settled market is compared against the official result.' },
  { title: 'Model Evaluation', detail: 'Champion and challenger models are scored on the same outcome.' },
  { title: 'Learning Report', detail: 'Error signal is attributed back to specific features and markets.' },
  { title: 'Knowledge Graph Update', detail: 'New relationships and context are written back into the graph.' },
  { title: 'Confidence Recalibration', detail: 'Probability calibration is re-fit against the latest outcomes.' },
  { title: 'Retraining Queue', detail: 'Markets crossing a drift threshold are queued for retraining.' },
]

function MarketLearningPanel({ marketKey }: { marketKey: string }) {
  const championQuery = useQuery({
    queryKey: ['ml', 'champion', marketKey],
    queryFn: () => mlPlatformApi.champion(marketKey),
    retry: false,
  })
  const championId = championQuery.data?.id

  const evaluationsQuery = useQuery({
    queryKey: ['ml', 'evaluations', championId],
    queryFn: () => mlPlatformApi.listEvaluations(championId!, 10),
    enabled: !!championId,
  })
  const importanceQuery = useQuery({
    queryKey: ['ml', 'feature-importance', marketKey],
    queryFn: () => mlPlatformApi.featureImportance(marketKey),
    enabled: !!championId,
    retry: false,
  })

  const noChampionYet = championQuery.isError && championQuery.error instanceof ApiError && championQuery.error.status === 404
  const noFittedModel = importanceQuery.isError && importanceQuery.error instanceof ApiError && importanceQuery.error.status === 409

  const latestEvaluation = evaluationsQuery.data?.[0]
  const latestCalibration = latestEvaluation?.calibration_report as
    | { expected_calibration_error?: number; brier_score?: number }
    | null
    | undefined

  if (championQuery.isPending) return <InfinitySkeleton className="h-32" />
  if (noChampionYet) {
    return (
      <InfinityEmptyState
        icon={Crown}
        title="No champion model yet"
        description="This market hasn't had a champion selected — TitanIQ is still running on its default weighted predictor."
      />
    )
  }
  if (championQuery.isError) return <ErrorState error={championQuery.error} onRetry={() => void championQuery.refetch()} />

  const champion = championQuery.data!

  return (
    <div className="space-y-6">
      <InfinityPanel tone="var(--infinity-domain-learning)" glow>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <InfinityLabel tone="var(--infinity-domain-learning)">Champion model</InfinityLabel>
            <p className="mt-1.5 font-infinity-display text-lg font-semibold text-infinity-text-primary">
              {champion.model_key} <span className="text-infinity-text-muted">v{champion.version}</span>
            </p>
          </div>
          <div className="flex items-center gap-4">
            {latestCalibration?.expected_calibration_error !== undefined && (
              <div className="text-center">
                <InfinityConfidenceRing value={1 - latestCalibration.expected_calibration_error} size={56} />
                <p className="mt-1 font-infinity-body text-[10px] uppercase tracking-[0.06em] text-infinity-text-muted">Calibrated</p>
              </div>
            )}
            <InfinityBadge domain="learning">{champion.status}</InfinityBadge>
          </div>
        </div>
      </InfinityPanel>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <div className="mb-3 flex items-center gap-2">
            <History className="size-4 text-infinity-text-muted" aria-hidden="true" />
            <p className="font-infinity-display text-[14px] font-semibold text-infinity-text-primary">Learning timeline</p>
          </div>
          {evaluationsQuery.isPending && <InfinitySkeleton className="h-32" />}
          {evaluationsQuery.isError && <ErrorState error={evaluationsQuery.error} onRetry={() => void evaluationsQuery.refetch()} />}
          {evaluationsQuery.data && evaluationsQuery.data.length === 0 && (
            <InfinityEmptyState icon={History} title="No evaluations yet" description="This model hasn't been scored against a settled result yet." />
          )}
          {evaluationsQuery.data && evaluationsQuery.data.length > 0 && (
            <ol className="space-y-2">
              {evaluationsQuery.data.map((ev) => {
                const metricEntries = Object.entries(ev.metrics).slice(0, 1)
                return (
                  <li key={ev.id} className="rounded-infinity-sm border border-infinity-border-hairline p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-infinity-mono text-[11px] text-infinity-text-muted">
                        {new Date(ev.evaluated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                      </span>
                      {metricEntries.map(([key, value]) => (
                        <span key={key} className="font-infinity-telemetry text-[12px] tabular-nums text-infinity-text-primary">
                          {key} {typeof value === 'number' ? value.toFixed(3) : String(value)}
                        </span>
                      ))}
                    </div>
                  </li>
                )
              })}
            </ol>
          )}
        </div>

        <div>
          <div className="mb-3 flex items-center gap-2">
            <BarChart3 className="size-4 text-infinity-text-muted" aria-hidden="true" />
            <p className="font-infinity-display text-[14px] font-semibold text-infinity-text-primary">Feature importance</p>
          </div>
          {importanceQuery.isPending && <InfinitySkeleton className="h-32" />}
          {noFittedModel && (
            <InfinityEmptyState
              icon={BarChart3}
              title="No trained model to explain"
              description="This market's champion is still the default weighted predictor — SHAP importance needs a real fitted ML model."
            />
          )}
          {importanceQuery.isError && !noFittedModel && (
            <ErrorState error={importanceQuery.error} onRetry={() => void importanceQuery.refetch()} />
          )}
          {importanceQuery.data && (
            <FeatureImportanceBars importance={importanceQuery.data.global_importance} />
          )}
        </div>
      </div>

      {latestCalibration && (latestCalibration.expected_calibration_error !== undefined || latestCalibration.brier_score !== undefined) && (
        <div>
          <div className="mb-3 flex items-center gap-2">
            <Gauge className="size-4 text-infinity-text-muted" aria-hidden="true" />
            <p className="font-infinity-display text-[14px] font-semibold text-infinity-text-primary">Calibration</p>
          </div>
          <InfinityPanel>
            <div className="flex flex-wrap gap-8">
              {latestCalibration.expected_calibration_error !== undefined && (
                <div>
                  <InfinityLabel>Expected calibration error</InfinityLabel>
                  <p className="mt-1 font-infinity-telemetry text-xl font-semibold tabular-nums text-infinity-text-primary">
                    {latestCalibration.expected_calibration_error.toFixed(4)}
                  </p>
                </div>
              )}
              {latestCalibration.brier_score !== undefined && (
                <div>
                  <InfinityLabel>Brier score</InfinityLabel>
                  <p className="mt-1 font-infinity-telemetry text-xl font-semibold tabular-nums text-infinity-text-primary">
                    {latestCalibration.brier_score.toFixed(4)}
                  </p>
                </div>
              )}
            </div>
          </InfinityPanel>
        </div>
      )}
    </div>
  )
}

function FeatureImportanceBars({ importance }: { importance: Record<string, number> }) {
  const entries = Object.entries(importance)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 8)
  const maxAbs = Math.max(0.001, ...entries.map(([, v]) => Math.abs(v)))

  if (entries.length === 0) {
    return <InfinityEmptyState icon={BarChart3} title="No feature importance yet" description="SHAP hasn't been computed for this model yet." />
  }

  return (
    <div className="space-y-2">
      {entries.map(([feature, value]) => (
        <div key={feature} className="flex items-center gap-2">
          <span className="w-32 shrink-0 truncate font-infinity-mono text-[11px] text-infinity-text-secondary">{feature}</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-infinity-ground-2">
            <div
              className={value >= 0 ? 'h-full rounded-full bg-infinity-domain-learning' : 'h-full rounded-full bg-infinity-danger'}
              style={{ width: `${(Math.abs(value) / maxAbs) * 100}%` }}
            />
          </div>
          <span className="w-14 shrink-0 text-right font-infinity-mono text-[11px] tabular-nums text-infinity-text-muted">
            {value >= 0 ? '+' : ''}
            {value.toFixed(3)}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function LearningIntelligencePage() {
  const role = useAuthStore((s) => s.profile?.role)
  const isAdmin = !!role && isAtLeast(role, 'administrator')
  const [marketKey, setMarketKey] = useState<string | null>(null)

  const marketsQuery = useQuery({ queryKey: ['markets', 'production'], queryFn: () => marketsApi.list({ status: 'production' }) })
  const summaryQuery = useQuery({
    queryKey: ['predictions', 'monitoring-summary'],
    queryFn: () => predictionsApi.monitoringSummary(),
  })

  return (
    <div className="mx-auto max-w-4xl space-y-10 p-4 lg:p-8">
      <div>
        <InfinityLabel tone="var(--infinity-domain-learning)">Learning Intelligence</InfinityLabel>
        <h1 className="mt-1 font-infinity-display text-2xl font-semibold text-infinity-text-primary">
          TitanIQ gets smarter after every match
        </h1>
        <p className="mt-2 font-infinity-body text-sm text-infinity-text-secondary">
          This is the real pipeline that runs after every settled result — not a marketing diagram.
        </p>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-stretch lg:gap-2">
        {PIPELINE.map((step, i) => (
          <div key={step.title} className="flex items-center gap-2 lg:flex-1 lg:flex-col lg:items-stretch lg:gap-0">
            <Card className="flex-1 p-4">
              <p className="font-telemetry text-xs text-text-muted">Step {i + 1}</p>
              <p className="mt-1 font-display text-sm font-semibold text-text-primary">{step.title}</p>
              <p className="mt-1.5 text-xs text-text-secondary">{step.detail}</p>
            </Card>
            {i < PIPELINE.length - 1 && (
              <ArrowRight className="size-4 shrink-0 text-text-muted lg:mx-auto lg:my-2 lg:rotate-90" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>

      <div>
        <div className="mb-3 flex items-center gap-2">
          <Crown className="size-4 text-infinity-text-muted" aria-hidden="true" />
          <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">How TitanIQ learns, per market</p>
        </div>
        {marketsQuery.isPending && <InfinitySkeleton className="h-10" />}
        {marketsQuery.isError && <ErrorState error={marketsQuery.error} onRetry={() => void marketsQuery.refetch()} />}
        {marketsQuery.data && marketsQuery.data.length === 0 && (
          <InfinityEmptyState icon={Crown} title="No production markets yet" description="Learning telemetry appears once a market reaches production status." />
        )}
        {marketsQuery.data && marketsQuery.data.length > 0 && (
          <>
            <div className="flex flex-wrap gap-1.5">
              {marketsQuery.data.map((m) => (
                <InfinityButton
                  key={m.id}
                  size="sm"
                  variant={marketKey === m.market_key ? 'secondary' : 'ghost'}
                  onClick={() => setMarketKey(marketKey === m.market_key ? null : m.market_key)}
                >
                  {m.name}
                </InfinityButton>
              ))}
            </div>
            {marketKey && (
              <div className="mt-4">
                <MarketLearningPanel marketKey={marketKey} />
              </div>
            )}
          </>
        )}
      </div>

      <div>
        <p className="mb-3 text-sm font-medium text-text-primary">Prediction monitoring</p>
        <Card className="p-5">
          {summaryQuery.isPending && <Skeleton className="h-20" />}
          {summaryQuery.isError && <ErrorState error={summaryQuery.error} onRetry={() => void summaryQuery.refetch()} />}
          {summaryQuery.data && <KeyValueGrid data={summaryQuery.data} />}
        </Card>
      </div>

      <Card className="flex items-start gap-3 p-4">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
        {isAdmin ? (
          <p className="text-sm text-text-secondary">
            Retraining triggers, model promotion, deployment mode, and full experiment/monitoring detail live in the{' '}
            <Link to="/app/ops/ml" className="text-accent-primary hover:text-accent-primary-hover">
              ML Operations console
            </Link>
            .
          </p>
        ) : (
          <p className="text-sm text-text-secondary">
            Champion models, feature importance, and evaluation history above are real and available to every signed-in account.
            Retraining triggers, model promotion, and deployment controls are restricted to administrator accounts.
          </p>
        )}
      </Card>
    </div>
  )
}
