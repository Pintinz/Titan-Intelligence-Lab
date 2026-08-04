import { useQueries, useQuery } from '@tanstack/react-query'
import { Bell, AlertTriangle, Plug } from 'lucide-react'
import { adminPredictionsApi } from '@/lib/api/admin-predictions'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { OpsPageHeader, SectionCard, MetricTile, BackendPendingState } from '@/components/ops/ops-primitives'

export default function AlertsMonitoringPage() {
  const alertsQuery = useQuery({ queryKey: ['admin', 'predictions', 'alerts'], queryFn: () => adminPredictionsApi.alerts() })
  const providersQuery = useQuery({ queryKey: ['admin', 'providers'], queryFn: () => adminPlatformApi.listProviders() })

  const providers = providersQuery.data ?? []
  const incidentQueries = useQueries({
    queries: providers.map((provider) => ({
      queryKey: ['admin', 'providers', provider.id, 'incidents'],
      queryFn: () => adminPlatformApi.providerIncidents(provider.id),
      enabled: providers.length > 0,
    })),
  })

  const alerts = alertsQuery.data ?? []
  const providerIncidents = providers.flatMap((provider, i) =>
    (incidentQueries[i]?.data ?? []).map((incident) => ({ provider, incident: incident as Record<string, unknown> })),
  )
  const incidentsLoading = incidentQueries.some((q) => q.isPending)

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Reliability"
        title="Alerts & Monitoring"
        description="Live prediction-engine alerts and provider incidents, unified in one feed. Categories with no backend alert source are named explicitly, not silently omitted."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricTile
          icon={Bell}
          label="Prediction alerts"
          value={alertsQuery.isPending ? <Skeleton className="h-6 w-8" /> : alerts.length}
          tone={alerts.length > 0 ? 'warning' : 'default'}
        />
        <MetricTile
          icon={Plug}
          label="Provider incidents"
          value={incidentsLoading ? <Skeleton className="h-6 w-8" /> : providerIncidents.length}
          tone={providerIncidents.length > 0 ? 'warning' : 'default'}
        />
        <MetricTile icon={AlertTriangle} label="Providers monitored" value={providersQuery.isPending ? <Skeleton className="h-6 w-8" /> : providers.length} />
      </div>

      <SectionCard icon={Bell} title="Prediction engine alerts" description="From /api/v1/admin/predictions/alerts.">
        {alertsQuery.isPending && <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>}
        {alertsQuery.isError && <ErrorState error={alertsQuery.error} onRetry={() => void alertsQuery.refetch()} />}
        {alerts.length === 0 && !alertsQuery.isPending && <EmptyState variant="minimal" title="No active prediction alerts" />}
        {alerts.length > 0 && (
          <ul className="space-y-2">
            {alerts.map((alert, i) => (
              <li key={i} className="rounded-md border border-warning/30 bg-warning-muted p-3">
                <KeyValueGrid data={alert as Record<string, unknown>} />
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard icon={Plug} title="Provider incidents" description="Recent incidents across every registered data provider.">
        {(providersQuery.isPending || incidentsLoading) && <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>}
        {providersQuery.isError && <ErrorState error={providersQuery.error} onRetry={() => void providersQuery.refetch()} />}
        {providerIncidents.length === 0 && !providersQuery.isPending && !incidentsLoading && (
          <EmptyState variant="minimal" title="No provider incidents recorded" />
        )}
        {providerIncidents.length > 0 && (
          <ul className="space-y-2">
            {providerIncidents.map(({ provider, incident }, i) => (
              <li key={i} className="rounded-md border border-danger/30 bg-danger-muted p-3">
                <p className="mb-1.5 font-mono text-[11px] uppercase tracking-wide text-text-muted">{provider.name}</p>
                <KeyValueGrid data={incident} />
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard title="Not yet available">
        <BackendPendingState
          title="Unified alert severity, acknowledgement, and resolution workflow"
          description="Prediction alerts and provider incidents are real, but there is no shared alert model — no severity ranking, no acknowledge/resolve action, and no dedicated alert source for ML drift, knowledge graph failures, news/community ingestion failures, database health, or realtime subscription health. Those systems are visible elsewhere in the Operations Center (ML Operations, Knowledge Graph, News Intelligence, Community Intelligence) but do not yet raise alerts here."
          recommendedEndpoint="GET /api/v1/admin/alerts · POST /api/v1/admin/alerts/{id}/acknowledge · POST /api/v1/admin/alerts/{id}/resolve"
        />
      </SectionCard>
    </div>
  )
}
