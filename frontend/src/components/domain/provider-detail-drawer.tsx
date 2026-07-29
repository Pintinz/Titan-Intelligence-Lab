import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { queryClient } from '@/lib/query-client'
import { toast } from '@/stores/toast-store'

export function ProviderDetailDrawer({ providerId, providerName }: { providerId: string; providerName: string }) {
  const [open, setOpen] = useState(false)
  const [checking, setChecking] = useState(false)

  const summaryQuery = useQuery({
    queryKey: ['admin', 'providerHealth', 'summary', providerId],
    queryFn: () => adminPlatformApi.providerHealthSummary(providerId),
    enabled: open,
  })
  const trendQuery = useQuery({
    queryKey: ['admin', 'providerHealth', 'trend', providerId],
    queryFn: () => adminPlatformApi.providerHealthTrend(providerId),
    enabled: open,
  })
  const incidentsQuery = useQuery({
    queryKey: ['admin', 'providerHealth', 'incidents', providerId],
    queryFn: () => adminPlatformApi.providerIncidents(providerId),
    enabled: open,
  })
  const diagnosticsQuery = useQuery({
    queryKey: ['admin', 'providerHealth', 'diagnostics', providerId],
    queryFn: () => adminPlatformApi.providerDiagnostics(providerId),
    enabled: open,
  })

  async function handleActivate() {
    try {
      await adminPlatformApi.activateProvider(providerId)
      toast.success('Provider activated')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'providers'] })
    } catch (error) {
      toast.danger('Activation failed', error instanceof Error ? error.message : undefined)
    }
  }

  async function handleManualCheck(success: boolean) {
    setChecking(true)
    try {
      await adminPlatformApi.recordProviderHealthCheck(providerId, { success })
      toast.success('Health check recorded')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'providerHealth', 'summary', providerId] })
    } catch (error) {
      toast.danger('Could not record health check', error instanceof Error ? error.message : undefined)
    } finally {
      setChecking(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          Details
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{providerName}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={handleActivate}>
            Activate
          </Button>
          <Button size="sm" variant="secondary" loading={checking} onClick={() => handleManualCheck(true)}>
            Record success check
          </Button>
          <Button size="sm" variant="danger" loading={checking} onClick={() => handleManualCheck(false)}>
            Record failure check
          </Button>
        </div>
        <Tabs defaultValue="summary">
          <TabsList>
            <TabsTrigger value="summary">Summary</TabsTrigger>
            <TabsTrigger value="trend">Trend</TabsTrigger>
            <TabsTrigger value="incidents">Incidents</TabsTrigger>
            <TabsTrigger value="diagnostics">Diagnostics</TabsTrigger>
          </TabsList>
          <TabsContent value="summary">
            <KeyValueGrid data={(summaryQuery.data as Record<string, unknown>) ?? {}} />
          </TabsContent>
          <TabsContent value="trend">
            <div className="flex max-h-64 flex-col gap-1 overflow-y-auto">
              {(trendQuery.data as Array<Record<string, unknown>> | undefined)?.map((point, i) => (
                <div key={i} className="rounded-md border border-border-subtle p-2">
                  <KeyValueGrid data={point} />
                </div>
              ))}
              {trendQuery.data?.length === 0 && <p className="text-sm text-text-muted">No trend data recorded yet.</p>}
            </div>
          </TabsContent>
          <TabsContent value="incidents">
            <div className="flex max-h-64 flex-col gap-1 overflow-y-auto">
              {(incidentsQuery.data as Array<Record<string, unknown>> | undefined)?.map((incident, i) => (
                <div key={i} className="rounded-md border border-border-subtle p-2">
                  <KeyValueGrid data={incident} />
                </div>
              ))}
              {incidentsQuery.data?.length === 0 && <p className="text-sm text-text-muted">No incidents recorded.</p>}
            </div>
          </TabsContent>
          <TabsContent value="diagnostics">
            <KeyValueGrid data={(diagnosticsQuery.data as Record<string, unknown>) ?? {}} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
