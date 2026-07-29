import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { useAuthStore } from '@/stores/auth-store'
import { toast } from '@/stores/toast-store'
import { queryClient } from '@/lib/query-client'

export function FeatureDetailPanel({ featureKey, status }: { featureKey: string; status: string }) {
  const reviewer = useAuthStore((s) => s.profile?.email) ?? 'unknown-admin'
  const [consumerKey, setConsumerKey] = useState('')
  const [busy, setBusy] = useState(false)

  const qualityQuery = useQuery({
    queryKey: ['admin', 'featureQuality', featureKey],
    queryFn: () => adminPlatformApi.featureQuality(featureKey),
  })
  const usageQuery = useQuery({
    queryKey: ['admin', 'featureUsage', featureKey],
    queryFn: () => adminPlatformApi.featureUsage(featureKey),
  })
  const statisticsQuery = useQuery({
    queryKey: ['admin', 'featureStatistics', featureKey],
    queryFn: () => adminPlatformApi.featureStatistics(featureKey),
  })
  const healthQuery = useQuery({
    queryKey: ['admin', 'featureHealth', featureKey],
    queryFn: () => adminPlatformApi.featureHealth(featureKey),
  })
  const validationsQuery = useQuery({
    queryKey: ['admin', 'featureValidations', featureKey],
    queryFn: () => adminPlatformApi.listFeatureValidations(featureKey),
  })
  const consumersQuery = useQuery({
    queryKey: ['admin', 'featureConsumers', featureKey],
    queryFn: () => adminPlatformApi.listFeatureConsumers(featureKey),
  })

  function invalidateAll() {
    void queryClient.invalidateQueries({ queryKey: ['admin', 'features'] })
    void queryClient.invalidateQueries({ queryKey: ['admin', 'featureValidations', featureKey] })
  }

  async function withBusy(action: () => Promise<unknown>, successMessage: string) {
    setBusy(true)
    try {
      await action()
      toast.success(successMessage)
      invalidateAll()
    } catch (error) {
      toast.danger('Action failed', error instanceof Error ? error.message : undefined)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {status === 'draft' && (
          <Button size="sm" loading={busy} onClick={() => withBusy(() => adminPlatformApi.submitFeature(featureKey), 'Submitted for review')}>
            Submit for review
          </Button>
        )}
        {status === 'in_review' && (
          <>
            <Button size="sm" loading={busy} onClick={() => withBusy(() => adminPlatformApi.approveFeature(featureKey, reviewer), 'Feature approved')}>
              Approve
            </Button>
            <Button
              size="sm"
              variant="danger"
              loading={busy}
              onClick={() => withBusy(() => adminPlatformApi.rejectFeature(featureKey, reviewer), 'Feature rejected')}
            >
              Reject
            </Button>
          </>
        )}
        {(status === 'active' || status === 'approved') && (
          <Button size="sm" variant="secondary" loading={busy} onClick={() => withBusy(() => adminPlatformApi.deprecateFeature(featureKey), 'Feature deprecated')}>
            Deprecate
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          loading={busy}
          onClick={() => withBusy(() => adminPlatformApi.validateFeature(featureKey), 'Validation run recorded')}
        >
          Run validation
        </Button>
      </div>

      <Tabs defaultValue="quality">
        <TabsList>
          <TabsTrigger value="quality">Quality</TabsTrigger>
          <TabsTrigger value="usage">Usage</TabsTrigger>
          <TabsTrigger value="statistics">Statistics</TabsTrigger>
          <TabsTrigger value="health">Health</TabsTrigger>
          <TabsTrigger value="validations">Validations</TabsTrigger>
          <TabsTrigger value="consumers">Consumers</TabsTrigger>
        </TabsList>
        <TabsContent value="quality">
          <KeyValueGrid data={(qualityQuery.data as Record<string, unknown>) ?? {}} />
        </TabsContent>
        <TabsContent value="usage">
          <KeyValueGrid data={(usageQuery.data as Record<string, unknown>) ?? {}} />
        </TabsContent>
        <TabsContent value="statistics">
          <KeyValueGrid data={(statisticsQuery.data as Record<string, unknown>) ?? {}} />
        </TabsContent>
        <TabsContent value="health">
          <KeyValueGrid data={(healthQuery.data as Record<string, unknown>) ?? {}} />
        </TabsContent>
        <TabsContent value="validations">
          <div className="flex flex-col gap-2">
            {validationsQuery.data?.length === 0 && <p className="text-sm text-text-muted">No validation runs recorded.</p>}
            {(validationsQuery.data as Array<Record<string, unknown>> | undefined)?.map((v, i) => (
              <div key={i} className="rounded-md border border-border-subtle p-2">
                <KeyValueGrid data={v} />
              </div>
            ))}
          </div>
        </TabsContent>
        <TabsContent value="consumers">
          <div className="flex flex-col gap-3">
            <div className="flex gap-2">
              <Input placeholder="Consumer key" value={consumerKey} onChange={(e) => setConsumerKey(e.target.value)} />
              <Button
                size="sm"
                disabled={!consumerKey}
                onClick={() =>
                  withBusy(() => adminPlatformApi.registerFeatureConsumer(featureKey, consumerKey), 'Consumer registered').then(() =>
                    setConsumerKey(''),
                  )
                }
              >
                Register
              </Button>
            </div>
            <div className="flex flex-col gap-1">
              {(consumersQuery.data as Array<Record<string, unknown>> | undefined)?.map((c, i) => (
                <p key={i} className="font-mono text-xs text-text-secondary">
                  {JSON.stringify(c)}
                </p>
              ))}
              {consumersQuery.data?.length === 0 && <p className="text-sm text-text-muted">No registered consumers.</p>}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
