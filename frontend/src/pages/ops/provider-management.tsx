import { useMutation, useQuery } from '@tanstack/react-query'
import { Database } from 'lucide-react'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

export default function ProviderManagement() {
  const providersQuery = useQuery({
    queryKey: ['admin', 'providers'],
    queryFn: () => adminPlatformApi.listProviders(),
  })

  const activate = useMutation({
    mutationFn: (providerId: string) => adminPlatformApi.activateProvider(providerId),
    onSuccess: () => void providersQuery.refetch(),
  })

  const providers = providersQuery.data ?? []

  return (
    <div className="space-y-6">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Providers
        </p>
        <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">Provider Management</h2>
        <p className="mt-1 text-sm text-text-secondary">External data source providers (APIs, databases, feeds).</p>
      </div>

      {providersQuery.isPending && (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}

      {providersQuery.isError && <ErrorState error={providersQuery.error} onRetry={() => void providersQuery.refetch()} />}

      {providers.length === 0 && !providersQuery.isPending && (
        <EmptyState icon={Database} title="No providers configured" description="Add a data provider to ingest external data." />
      )}

      {providers.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {providers.map((provider) => (
            <Card key={provider.id} className="flex flex-col gap-3 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-display text-sm font-semibold text-text-primary">{provider.name}</p>
                  <p className="text-xs text-text-muted">{provider.category}</p>
                </div>
                <span
                  className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                    provider.status === 'active' ? 'bg-success-muted text-success' : 'bg-text-muted/20 text-text-muted'
                  }`}
                >
                  {provider.status}
                </span>
              </div>
              <p className="font-mono text-xs text-text-secondary">{provider.key}</p>
              {provider.status !== 'active' && (
                <Button
                  size="sm"
                  onClick={() => activate.mutate(provider.id)}
                  disabled={activate.isPending}
                  className="mt-auto"
                >
                  {activate.isPending ? 'Activating…' : 'Activate'}
                </Button>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
