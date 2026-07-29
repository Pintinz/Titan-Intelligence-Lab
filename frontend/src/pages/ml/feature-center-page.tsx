import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sliders } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { FeatureDetailPanel } from '@/components/domain/feature-detail-panel'
import { adminPlatformApi } from '@/lib/api/admin-platform'

const STATUS_VARIANT = {
  draft: 'neutral',
  in_review: 'info',
  active: 'success',
  deprecated: 'warning',
} as const

export default function FeatureCenterPage() {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  const featuresQuery = useQuery({ queryKey: ['admin', 'features'], queryFn: () => adminPlatformApi.listFeatures() })

  const features = featuresQuery.data ?? []
  const selectedFeature = features.find((f) => (f.feature_key as string) === selectedKey)

  return (
    <div data-dashboard-accent="ml" className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Feature Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Feature Center</h1>
        <p className="mt-1 text-sm text-text-secondary">Feature Registry — lifecycle status and quality.</p>
      </div>

      {featuresQuery.isLoading && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      )}

      {features.length === 0 && !featuresQuery.isLoading && (
        <EmptyState icon={<Sliders className="h-6 w-6" />} title="No features registered yet" />
      )}

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="flex flex-col gap-2">
          {features.map((feature) => {
            const key = feature.feature_key as string
            const status = feature.status as string
            return (
              <button key={key} type="button" onClick={() => setSelectedKey(key)} className="text-left">
                <Card className={selectedKey === key ? 'border-accent-primary' : ''}>
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="font-mono text-sm text-text-primary">{key}</p>
                      <p className="text-xs text-text-muted">{feature.name as string}</p>
                    </div>
                    <Badge variant={STATUS_VARIANT[status as keyof typeof STATUS_VARIANT] ?? 'neutral'}>{status}</Badge>
                  </CardContent>
                </Card>
              </button>
            )
          })}
        </div>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>{selectedKey ?? 'Feature detail'}</CardTitle>
          </CardHeader>
          <CardContent>
            {selectedFeature ? (
              <FeatureDetailPanel featureKey={selectedFeature.feature_key as string} status={selectedFeature.status as string} />
            ) : (
              <p className="text-sm text-text-muted">Select a feature to view its quality, usage, and lifecycle actions.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
