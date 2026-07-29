import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Flag, Plus } from 'lucide-react'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

interface Flag {
  key: string
  name: string
  description: string
  enabled: boolean
}

export default function FeatureFlags() {
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [formData, setFormData] = useState({ key: '', name: '', description: '', enabled: false })

  const flagsQuery = useQuery({
    queryKey: ['admin', 'flags'],
    queryFn: () => adminPlatformApi.listFlags() as unknown as Promise<Flag[]>,
  })

  const createFlag = useMutation({
    mutationFn: () =>
      adminPlatformApi.createFlag({
        key: formData.key,
        name: formData.name,
        description: formData.description,
        enabled: formData.enabled,
      }),
    onSuccess: () => {
      setFormData({ key: '', name: '', description: '', enabled: false })
      setShowCreateDialog(false)
      void flagsQuery.refetch()
    },
  })

  const toggleFlag = useMutation({
    mutationFn: (key: string) => {
      const flag = flagsQuery.data?.find((f) => f.key === key)
      return flag?.enabled ? adminPlatformApi.disableFlag(key) : adminPlatformApi.enableFlag(key)
    },
    onSuccess: () => void flagsQuery.refetch(),
  })

  const flags = flagsQuery.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
            Flags
          </p>
          <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">Feature Flags</h2>
          <p className="mt-1 text-sm text-text-secondary">Control feature rollout and A/B testing.</p>
        </div>
        <Button onClick={() => setShowCreateDialog(true)} size="sm" className="gap-1">
          <Plus className="size-3.5" /> New flag
        </Button>
      </div>

      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create feature flag</DialogTitle>
            <DialogDescription>Define a new feature flag for rollout control.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium text-text-primary">Key</label>
              <Input
                placeholder="feature_flag_key"
                value={formData.key}
                onChange={(e) => setFormData({ ...formData, key: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-text-primary">Name</label>
              <Input
                placeholder="Feature Flag Name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-text-primary">Description</label>
              <Input
                placeholder="What does this flag control?"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="mt-1"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox checked={formData.enabled} onCheckedChange={(c) => setFormData({ ...formData, enabled: !!c })} />
              <label className="text-sm font-medium text-text-primary">Enable immediately</label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setShowCreateDialog(false)}>
              Cancel
            </Button>
            <Button onClick={() => createFlag.mutate()} disabled={createFlag.isPending || !formData.key || !formData.name}>
              {createFlag.isPending ? 'Creating…' : 'Create flag'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {flagsQuery.isPending && (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {flagsQuery.isError && <ErrorState error={flagsQuery.error} onRetry={() => void flagsQuery.refetch()} />}

      {flags.length === 0 && !flagsQuery.isPending && (
        <EmptyState icon={Flag} title="No feature flags" description="Create your first feature flag to enable gradual rollout." />
      )}

      {flags.length > 0 && (
        <div className="space-y-2">
          {flags.map((flag) => (
            <Card key={flag.key} className="flex items-center justify-between p-4">
              <div className="min-w-0 flex-1">
                <p className="font-display text-sm font-semibold text-text-primary">{flag.name}</p>
                <p className="text-xs text-text-muted">{flag.key}</p>
                {flag.description && <p className="mt-1 text-xs text-text-secondary">{flag.description}</p>}
              </div>
              <Switch checked={flag.enabled} onCheckedChange={() => toggleFlag.mutate(flag.key)} disabled={toggleFlag.isPending} />
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
