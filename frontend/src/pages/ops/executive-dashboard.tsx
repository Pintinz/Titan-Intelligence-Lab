import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { adminPredictionsApi } from '@/lib/api/admin-predictions'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { KeyValueGrid } from '@/components/domain/key-value-grid'

export default function ExecutiveDashboard() {
  const healthQuery = useQuery({
    queryKey: ['admin', 'redis-health'],
    queryFn: () => adminPlatformApi.redisHealth(),
  })
  const marketsHealthQuery = useQuery({
    queryKey: ['admin', 'markets-health'],
    queryFn: () => adminPredictionsApi.marketsHealth(),
  })
  const redis = healthQuery.data
  const redisHealthy = redis?.healthy ?? false

  return (
    <div className="space-y-6">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Operations
        </p>
        <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">Executive Dashboard</h2>
        <p className="mt-1 text-sm text-text-secondary">Real-time health summary across all platform systems.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-text-muted">Redis cache</p>
              <p className="font-display text-sm font-semibold text-text-primary">
                {healthQuery.isPending ? '…' : redisHealthy ? 'Healthy' : 'Down'}
              </p>
            </div>
            {redisHealthy ? (
              <CheckCircle2 className="size-5 text-success" aria-hidden="true" />
            ) : healthQuery.isPending ? (
              <Activity className="size-5 text-text-muted animate-spin" aria-hidden="true" />
            ) : (
              <AlertTriangle className="size-5 text-danger" aria-hidden="true" />
            )}
          </div>
          {redis && !healthQuery.isPending && (
            <p className="mt-2 font-mono text-xs text-text-muted">
              {redis.latency_ms ?? 0}ms{redis.error && ` — ${redis.error}`}
            </p>
          )}
        </Card>

        <Card className="p-4">
          <p className="text-xs text-text-muted">Markets under coverage</p>
          {marketsHealthQuery.isPending && <Skeleton className="mt-2 h-6" />}
          {marketsHealthQuery.data && (
            <p className="mt-2 font-telemetry text-2xl font-medium text-text-primary">
              {Object.keys(marketsHealthQuery.data).length}
            </p>
          )}
        </Card>

        <Card className="p-4">
          <p className="text-xs text-text-muted">Sync status</p>
          <p className="mt-2 text-sm text-text-secondary">Check Data Pipeline module</p>
        </Card>
      </div>

      <Card className="p-5">
        <p className="font-display text-base font-semibold text-text-primary">Markets health overview</p>
        <div className="mt-4">
          {marketsHealthQuery.isPending && <Skeleton className="h-24" />}
          {marketsHealthQuery.isError && (
            <ErrorState error={marketsHealthQuery.error} onRetry={() => void marketsHealthQuery.refetch()} />
          )}
          {marketsHealthQuery.data && <KeyValueGrid data={marketsHealthQuery.data} />}
        </div>
      </Card>
    </div>
  )
}
