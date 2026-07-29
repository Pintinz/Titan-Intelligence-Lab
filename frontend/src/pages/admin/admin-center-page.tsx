import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { StatusDot } from '@/components/ui/status-dot'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { RegeneratePredictionForm } from '@/components/domain/regenerate-prediction-form'
import { RollbackModelForm } from '@/components/domain/rollback-model-form'
import { PredictionMarketWorkbench } from '@/components/domain/prediction-market-workbench'
import { ProviderDetailDrawer } from '@/components/domain/provider-detail-drawer'
import { FlagCreateForm } from '@/components/domain/flag-create-form'
import { IngestionSyncPanel } from '@/components/domain/ingestion-sync-panel'
import { KgNodeLookup } from '@/components/domain/kg-node-lookup'
import { VirtualTable } from '@/components/domain/virtual-table'
import { Switch } from '@/components/ui/switch'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { adminPredictionsApi } from '@/lib/api/admin-predictions'
import { queryClient } from '@/lib/query-client'
import { toast } from '@/stores/toast-store'

export default function AdminCenterPage() {
  const providersQuery = useQuery({ queryKey: ['admin', 'providers'], queryFn: () => adminPlatformApi.listProviders() })
  const flagsQuery = useQuery({ queryKey: ['admin', 'flags'], queryFn: () => adminPlatformApi.listFlags() })
  const syncStatusQuery = useQuery({ queryKey: ['admin', 'syncStatus'], queryFn: () => adminPlatformApi.syncStatus({ limit: 200 }) })
  const redisHealthQuery = useQuery({ queryKey: ['admin', 'redisHealth'], queryFn: () => adminPlatformApi.redisHealth() })
  const marketsHealthQuery = useQuery({ queryKey: ['admin', 'marketsHealth'], queryFn: () => adminPredictionsApi.marketsHealth() })
  const alertsQuery = useQuery({ queryKey: ['admin', 'alerts'], queryFn: () => adminPredictionsApi.alerts() })
  const [rolloutDrafts, setRolloutDrafts] = useState<Record<string, number>>({})

  async function toggleFlag(key: string, enabled: boolean) {
    if (enabled) await adminPlatformApi.disableFlag(key)
    else await adminPlatformApi.enableFlag(key)
    void queryClient.invalidateQueries({ queryKey: ['admin', 'flags'] })
  }

  async function setRollout(key: string) {
    const percentage = rolloutDrafts[key]
    if (percentage === undefined) return
    try {
      await adminPlatformApi.setFlagRollout(key, percentage)
      toast.success('Rollout updated', `${key} · ${percentage}%`)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'flags'] })
    } catch (error) {
      toast.danger('Could not update rollout', error instanceof Error ? error.message : undefined)
    }
  }

  async function handleEvaluate(key: string) {
    try {
      const result = await adminPlatformApi.evaluateFlag(key)
      toast.show('Flag evaluation', `${key} → ${result.enabled ? 'enabled' : 'disabled'} for anonymous context`, result.enabled ? 'success' : 'default')
    } catch (error) {
      toast.danger('Evaluation failed', error instanceof Error ? error.message : undefined)
    }
  }

  return (
    <div data-dashboard-accent="admin" className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Admin Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Admin Center</h1>
      </div>

      <Tabs defaultValue="providers">
        <TabsList>
          <TabsTrigger value="providers">Providers</TabsTrigger>
          <TabsTrigger value="apikeys">API Keys</TabsTrigger>
          <TabsTrigger value="flags">Feature Flags</TabsTrigger>
          <TabsTrigger value="sync">Ingestion Sync</TabsTrigger>
          <TabsTrigger value="predictions">Prediction Markets</TabsTrigger>
          <TabsTrigger value="system">System Health</TabsTrigger>
        </TabsList>

        <TabsContent value="providers">
          <Card>
            <CardHeader>
              <CardTitle>Provider Management</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {providersQuery.data?.map((provider) => (
                <div key={provider.id} className="flex items-center justify-between border-b border-border-subtle py-2 last:border-0">
                  <div>
                    <p className="text-sm text-text-primary">{provider.name}</p>
                    <p className="text-xs text-text-muted">{provider.category}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusDot tone={provider.status === 'active' ? 'success' : 'neutral'} label={provider.status} />
                    <ProviderDetailDrawer providerId={provider.id} providerName={provider.name} />
                  </div>
                </div>
              ))}
              {providersQuery.data?.length === 0 && <p className="text-sm text-text-muted">No providers registered.</p>}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="apikeys">
          <div className="flex flex-col gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Configured providers</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {providersQuery.data?.map((provider) => (
                  <div key={provider.id} className="flex items-center justify-between border-b border-border-subtle py-2 last:border-0">
                    <div>
                      <p className="text-sm text-text-primary">{provider.name}</p>
                      <p className="font-mono text-xs text-text-muted">{provider.key} · priority {provider.priority}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="neutral">{provider.category}</Badge>
                      <StatusDot tone={provider.status === 'active' ? 'success' : 'neutral'} label={provider.status} />
                      <ProviderDetailDrawer providerId={provider.id} providerName={provider.name} />
                    </div>
                  </div>
                ))}
                {providersQuery.data?.length === 0 && <p className="text-sm text-text-muted">No providers registered.</p>}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Credential management</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-text-secondary">
                  Adding, rotating, or connection-testing API keys (API-Football, Gemini, SMTP, Redis, Storage) is reserved
                  for Milestone 15&apos;s dedicated Admin UI — the backend service that will power it
                  (<code className="font-mono text-xs">ProviderManagementService.add_credential</code> /{' '}
                  <code className="font-mono text-xs">rotate_credential</code>) exists but has no API route wired to it yet, by
                  design. Credential values are never exposed to the browser — only the reliability score of an existing
                  credential can be queried once one exists. This page shows real provider status, priority, and health only.
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="flags">
          <div className="flex flex-col gap-4">
            <FlagCreateForm />
            <Card>
              <CardHeader>
                <CardTitle>Feature Flags</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {flagsQuery.data?.map((flag) => {
                  const key = flag.key as string
                  return (
                    <div key={flag.id as string} className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle py-2 last:border-0">
                      <div>
                        <p className="text-sm text-text-primary">{flag.name as string}</p>
                        <p className="font-mono text-xs text-text-muted">{key} · rollout {flag.rollout_percentage as number}%</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Input
                          type="number"
                          min={0}
                          max={100}
                          className="h-8 w-20"
                          value={rolloutDrafts[key] ?? (flag.rollout_percentage as number)}
                          onChange={(e) => setRolloutDrafts({ ...rolloutDrafts, [key]: Number(e.target.value) })}
                        />
                        <Button size="sm" variant="secondary" onClick={() => setRollout(key)}>
                          Set
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleEvaluate(key)}>
                          Evaluate
                        </Button>
                        <Switch checked={flag.enabled as boolean} onCheckedChange={() => toggleFlag(key, flag.enabled as boolean)} />
                      </div>
                    </div>
                  )
                })}
                {flagsQuery.data?.length === 0 && <p className="text-sm text-text-muted">No feature flags created.</p>}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="sync">
          <div className="flex flex-col gap-4">
            <IngestionSyncPanel />
            <Card>
              <CardHeader>
                <CardTitle>Sync Runs</CardTitle>
              </CardHeader>
              <CardContent>
                <VirtualTable
                  rows={(syncStatusQuery.data as Array<Record<string, unknown>> | undefined) ?? []}
                  getRowId={(run) => `${run.sport_code}-${run.entity_kind}-${run.started_at}`}
                  emptyMessage="No sync runs recorded."
                  columns={[
                    {
                      key: 'entity',
                      header: 'Entity',
                      render: (run) => `${run.sport_code as string} · ${run.entity_kind as string}`,
                    },
                    {
                      key: 'status',
                      header: 'Status',
                      width: '120px',
                      render: (run) => (
                        <Badge variant={run.status === 'succeeded' ? 'success' : run.status === 'failed' ? 'danger' : 'neutral'}>
                          {run.status as string}
                        </Badge>
                      ),
                    },
                  ]}
                />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="predictions">
          <div className="grid gap-6 lg:grid-cols-2">
            <PredictionMarketWorkbench />
            <Card>
              <CardHeader>
                <CardTitle>Markets health</CardTitle>
              </CardHeader>
              <CardContent>
                <KeyValueGrid data={(marketsHealthQuery.data as Record<string, unknown>) ?? {}} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Alerts</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {(alertsQuery.data as Array<Record<string, unknown>> | undefined)?.map((alert, i) => (
                  <div key={i} className="rounded-md bg-warning-muted p-2 text-xs text-warning">
                    {JSON.stringify(alert)}
                  </div>
                ))}
                {(alertsQuery.data as unknown[] | undefined)?.length === 0 && (
                  <p className="text-sm text-text-muted">No active alerts.</p>
                )}
              </CardContent>
            </Card>
            <RegeneratePredictionForm />
            <RollbackModelForm />
          </div>
        </TabsContent>

        <TabsContent value="system">
          <div className="flex flex-col gap-4">
            <Card className="max-w-md">
              <CardHeader>
                <CardTitle>Redis health</CardTitle>
              </CardHeader>
              <CardContent>
                <KeyValueGrid data={(redisHealthQuery.data as Record<string, unknown>) ?? {}} />
              </CardContent>
            </Card>
            <KgNodeLookup />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
