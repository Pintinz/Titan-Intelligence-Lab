import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Layers, ChevronDown, ChevronRight } from 'lucide-react'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { OpsPageHeader } from '@/components/ops/ops-primitives'

function keyOf(feature: Record<string, unknown>): string {
  return String(feature.key ?? feature.feature_key ?? feature.id ?? '')
}

function FeatureDetail({ featureKey }: { featureKey: string }) {
  const qualityQuery = useQuery({
    queryKey: ['admin', 'features', featureKey, 'quality'],
    queryFn: () => adminPlatformApi.featureQuality(featureKey),
  })
  const healthQuery = useQuery({
    queryKey: ['admin', 'features', featureKey, 'health'],
    queryFn: () => adminPlatformApi.featureHealth(featureKey),
  })
  const usageQuery = useQuery({
    queryKey: ['admin', 'features', featureKey, 'usage'],
    queryFn: () => adminPlatformApi.featureUsage(featureKey),
  })
  const validationQuery = useQuery({
    queryKey: ['admin', 'features', featureKey, 'validation-latest'],
    queryFn: () => adminPlatformApi.latestFeatureValidation(featureKey),
  })

  return (
    <div className="grid gap-4 border-t border-border-subtle p-4 sm:grid-cols-2">
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Quality</p>
        {qualityQuery.isPending && <Skeleton className="h-16" />}
        {qualityQuery.isError && <ErrorState error={qualityQuery.error} onRetry={() => void qualityQuery.refetch()} />}
        {qualityQuery.data && <KeyValueGrid data={qualityQuery.data} />}
      </div>
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Health</p>
        {healthQuery.isPending && <Skeleton className="h-16" />}
        {healthQuery.isError && <ErrorState error={healthQuery.error} onRetry={() => void healthQuery.refetch()} />}
        {healthQuery.data && <KeyValueGrid data={healthQuery.data} />}
      </div>
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Usage & consumers</p>
        {usageQuery.isPending && <Skeleton className="h-16" />}
        {usageQuery.isError && <ErrorState error={usageQuery.error} onRetry={() => void usageQuery.refetch()} />}
        {usageQuery.data && <KeyValueGrid data={usageQuery.data} />}
      </div>
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Latest validation</p>
        {validationQuery.isPending && <Skeleton className="h-16" />}
        {validationQuery.isError && <ErrorState error={validationQuery.error} onRetry={() => void validationQuery.refetch()} />}
        {validationQuery.data === null && <p className="text-sm text-text-muted">No validation run yet.</p>}
        {validationQuery.data && <KeyValueGrid data={validationQuery.data as Record<string, unknown>} />}
      </div>
    </div>
  )
}

export default function FeatureStorePage() {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  const featuresQuery = useQuery({
    queryKey: ['admin', 'features'],
    queryFn: () => adminPlatformApi.listFeatures(),
  })

  const features = featuresQuery.data ?? []

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="ML Platform"
        title="Feature Store"
        description="Registered feature groups — freshness, validation, drift, and consumer usage for every engineered feature backing TitanIQ's models."
      />

      {featuresQuery.isPending && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)}
        </div>
      )}

      {featuresQuery.isError && <ErrorState error={featuresQuery.error} onRetry={() => void featuresQuery.refetch()} />}

      {features.length === 0 && !featuresQuery.isPending && (
        <EmptyState
          icon={Layers}
          title="No features registered yet"
          description="Features are registered through the feature engineering pipeline as models are built — none have been submitted yet."
        />
      )}

      {features.length > 0 && (
        <div className="space-y-3">
          {features.map((feature, i) => {
            const key = keyOf(feature)
            const isExpanded = expandedKey === key
            return (
              <Card key={key || i} className="overflow-hidden">
                <button
                  type="button"
                  onClick={() => setExpandedKey(isExpanded ? null : key)}
                  className="flex w-full items-center gap-3 p-4 text-left"
                  aria-expanded={isExpanded}
                >
                  {isExpanded ? <ChevronDown className="size-4 shrink-0 text-text-muted" /> : <ChevronRight className="size-4 shrink-0 text-text-muted" />}
                  <div className="min-w-0 flex-1">
                    <p className="font-display text-sm font-semibold text-text-primary">{String(feature.name ?? key)}</p>
                    <p className="font-mono text-xs text-text-muted">{key}</p>
                  </div>
                </button>
                {isExpanded && <FeatureDetail featureKey={key} />}
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
