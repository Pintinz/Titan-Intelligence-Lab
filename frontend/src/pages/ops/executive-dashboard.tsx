import { useQueries, useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Radio,
  Target,
  Plug,
  Network,
  Newspaper,
  MessageCircle,
  Clock,
  BellRing,
  Cog,
} from 'lucide-react'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { adminPredictionsApi } from '@/lib/api/admin-predictions'
import { predictionsApi } from '@/lib/api/predictions'
import { graphApi } from '@/lib/api/graph'
import { intelligenceApi } from '@/lib/api/intelligence'
import { sportsApi } from '@/lib/api/sports'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { OpsPageHeader, MetricTile, SectionCard, BackendPendingState } from '@/components/ops/ops-primitives'
import { KeyValueGrid } from '@/components/domain/key-value-grid'

const NOT_INSTRUMENTED = [
  { label: 'Active Users', endpoint: 'GET /api/v1/admin/analytics/active-users' },
  { label: 'API Requests', endpoint: 'GET /api/v1/admin/analytics/api-requests' },
  { label: 'Intelligence Requests', endpoint: 'GET /api/v1/admin/analytics/intelligence-requests' },
  { label: 'Queue Health', endpoint: 'GET /api/v1/admin/queues/health' },
  { label: 'Background Workers', endpoint: 'GET /api/v1/admin/workers' },
]

export default function ExecutiveDashboard() {
  const healthQuery = useQuery({ queryKey: ['admin', 'redis-health'], queryFn: () => adminPlatformApi.redisHealth() })
  const marketsHealthQuery = useQuery({ queryKey: ['admin', 'markets-health'], queryFn: () => adminPredictionsApi.marketsHealth() })
  const providersQuery = useQuery({ queryKey: ['admin', 'providers'], queryFn: () => adminPlatformApi.listProviders() })
  const syncStatusQuery = useQuery({ queryKey: ['admin', 'sync-status'], queryFn: () => adminPlatformApi.syncStatus({ limit: 8 }) })
  const alertsQuery = useQuery({ queryKey: ['admin', 'prediction-alerts'], queryFn: () => adminPredictionsApi.alerts() })
  const monitoringQuery = useQuery({ queryKey: ['predictions', 'monitoring', 'summary'], queryFn: () => predictionsApi.monitoringSummary() })
  const graphStatsQuery = useQuery({ queryKey: ['graph', 'statistics'], queryFn: () => graphApi.statistics() })
  const intelligenceQuery = useQuery({ queryKey: ['intelligence', 'analytics'], queryFn: () => intelligenceApi.analytics() })

  const fixtureQueries = useQueries({
    queries: SPORT_SLUGS.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'ops-dashboard'],
      queryFn: () => sportsApi.listFixtures(sport.code, { limit: 20 }),
    })),
  })
  const allFixtures = fixtureQueries.flatMap((q) => q.data ?? [])
  const liveCount = allFixtures.filter((f) => ['live', 'in_play'].includes(f.status.toLowerCase())).length
  const fixturesLoading = fixtureQueries.some((q) => q.isPending)

  const redis = healthQuery.data
  const redisHealthy = redis?.healthy ?? false
  const providers = providersQuery.data ?? []
  const activeProviders = providers.filter((p) => p.status === 'active').length
  const alerts = alertsQuery.data ?? []

  const platformHealthy = redisHealthy && (marketsHealthQuery.isSuccess ?? false) && !marketsHealthQuery.isError

  return (
    <div className="space-y-8">
      <OpsPageHeader
        eyebrow="Operations"
        title="Executive Dashboard"
        description="Live operational intelligence across every system that powers TitanIQ."
      />

      <div className="flex items-center gap-2 rounded-lg border border-border-default bg-bg-elevated px-4 py-3">
        {healthQuery.isPending ? (
          <Activity className="size-4 animate-spin text-text-muted" aria-hidden="true" />
        ) : platformHealthy ? (
          <CheckCircle2 className="size-4 text-success" aria-hidden="true" />
        ) : (
          <AlertTriangle className="size-4 text-warning" aria-hidden="true" />
        )}
        <p className="text-sm font-medium text-text-primary">
          {healthQuery.isPending ? 'Checking platform health…' : platformHealthy ? 'All monitored systems operational' : 'One or more systems need attention'}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        <MetricTile
          icon={Radio}
          label="Live matches"
          value={fixturesLoading ? <Skeleton className="h-6 w-8" /> : liveCount}
          tone={liveCount > 0 ? 'live' : 'default'}
        />
        <MetricTile
          icon={Target}
          label="Predictions tracked"
          value={monitoringQuery.isPending ? <Skeleton className="h-6 w-8" /> : ((monitoringQuery.data?.sample_size as number | undefined) ?? '—')}
          href="/app/ops/markets"
        />
        <MetricTile
          icon={Plug}
          label="Active providers"
          value={providersQuery.isPending ? <Skeleton className="h-6 w-8" /> : `${activeProviders}/${providers.length}`}
          tone={providersQuery.isPending ? 'default' : activeProviders === providers.length && providers.length > 0 ? 'success' : 'warning'}
          href="/app/ops/providers"
        />
        <MetricTile
          icon={Network}
          label="Knowledge Graph nodes"
          value={graphStatsQuery.isPending ? <Skeleton className="h-6 w-8" /> : ((graphStatsQuery.data?.node_count as number | undefined) ?? '—')}
          href="/app/ops/graph"
        />
        <MetricTile
          icon={Newspaper}
          label="Articles ingested"
          value={intelligenceQuery.isPending ? <Skeleton className="h-6 w-8" /> : ((intelligenceQuery.data?.article_count as number | undefined) ?? '—')}
          href="/app/ops/news"
        />
        <MetricTile
          icon={MessageCircle}
          label="Community signals"
          value={intelligenceQuery.isPending ? <Skeleton className="h-6 w-8" /> : ((intelligenceQuery.data?.community_post_count as number | undefined) ?? '—')}
          href="/app/ops/community"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard icon={Activity} title="Redis cache" description="Backing store for feature caching and rate limiting.">
          {healthQuery.isPending && <Skeleton className="h-16" />}
          {healthQuery.isError && <ErrorState error={healthQuery.error} onRetry={() => void healthQuery.refetch()} />}
          {redis && !healthQuery.isPending && (
            <div className="flex items-center justify-between">
              <span className={redisHealthy ? 'text-sm font-medium text-success' : 'text-sm font-medium text-danger'}>
                {redisHealthy ? 'Healthy' : 'Down'}
              </span>
              <span className="font-mono text-xs text-text-muted">
                {redis.latency_ms ?? 0}ms{redis.error && ` — ${redis.error}`}
              </span>
            </div>
          )}
        </SectionCard>

        <SectionCard icon={Cog} title="Prediction markets health" description="Coverage and health across every registered market.">
          {marketsHealthQuery.isPending && <Skeleton className="h-16" />}
          {marketsHealthQuery.isError && <ErrorState error={marketsHealthQuery.error} onRetry={() => void marketsHealthQuery.refetch()} />}
          {marketsHealthQuery.data && <KeyValueGrid data={marketsHealthQuery.data} />}
        </SectionCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard icon={Clock} title="Last synchronization" description="Most recent ingestion sync runs across all sports.">
          {syncStatusQuery.isPending && <Skeleton className="h-24" />}
          {syncStatusQuery.isError && <ErrorState error={syncStatusQuery.error} onRetry={() => void syncStatusQuery.refetch()} />}
          {syncStatusQuery.data && syncStatusQuery.data.length === 0 && (
            <p className="text-sm text-text-secondary">No sync runs recorded yet — see Data Pipeline to trigger one.</p>
          )}
          {syncStatusQuery.data && syncStatusQuery.data.length > 0 && (
            <ul className="space-y-2">
              {syncStatusQuery.data.slice(0, 5).map((entry, i) => (
                <li key={i} className="rounded-md border border-border-subtle p-2.5">
                  <KeyValueGrid data={entry as Record<string, unknown>} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard icon={BellRing} title="System alerts" description="Active prediction and market alerts." actions={<a href="/app/ops/alerts" className="text-xs text-accent-primary hover:text-accent-primary-hover">View all →</a>}>
          {alertsQuery.isPending && <Skeleton className="h-24" />}
          {alertsQuery.isError && <ErrorState error={alertsQuery.error} onRetry={() => void alertsQuery.refetch()} />}
          {alerts.length === 0 && !alertsQuery.isPending && (
            <p className="text-sm text-text-secondary">No active alerts.</p>
          )}
          {alerts.length > 0 && (
            <ul className="space-y-2">
              {alerts.slice(0, 5).map((alert, i) => (
                <li key={i} className="rounded-md border border-warning/30 bg-warning-muted p-2.5">
                  <KeyValueGrid data={alert as Record<string, unknown>} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Not yet instrumented" description="Brief-requested metrics with no backend endpoint yet — shown honestly rather than faked.">
        <BackendPendingState
          title="Platform-wide usage analytics"
          description="Active user counts, API request volume, intelligence-request volume, queue depth, and background-worker status all require a new analytics/monitoring surface — none of it currently exists in the backend."
          recommendedEndpoint={NOT_INSTRUMENTED.map((n) => n.endpoint).join(' · ')}
        />
      </SectionCard>
    </div>
  )
}
