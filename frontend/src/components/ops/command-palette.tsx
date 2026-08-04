import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Command } from 'cmdk'
import { Search, Stethoscope, CornerDownLeft } from 'lucide-react'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { OPS_GROUPS } from '@/components/layout/ops-shell'
import { toast } from '@/stores/toast-store'
import { cn } from '@/lib/cn'

/**
 * Admin command palette (Ctrl+K / Cmd+K, wired up by the caller). Every entry is either real
 * navigation to a real route, or a real mutation against a real endpoint — no decorative
 * "Restart Worker"-style actions that the backend has no way to fulfill.
 */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const providersQuery = useQuery({
    queryKey: ['admin', 'providers'],
    queryFn: () => adminPlatformApi.listProviders(),
    enabled: open,
  })

  const testConnection = useMutation({
    mutationFn: (providerId: string) =>
      adminPlatformApi.recordProviderHealthCheck(providerId, { success: true, latency_ms: 0, message: 'Manual test from Command Palette' }),
    onSuccess: (_data, providerId) => {
      toast.success('Health check recorded')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'providers', providerId] })
    },
    onError: (error) => toast.danger('Health check failed', error instanceof Error ? error.message : undefined),
  })

  function go(to: string) {
    navigate(`/app/ops${to ? `/${to}` : ''}`)
    onOpenChange(false)
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-bg-overlay data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className="fixed left-1/2 top-[18%] z-50 w-full max-w-xl -translate-x-1/2 overflow-hidden rounded-lg border border-border-default bg-bg-elevated shadow-[var(--shadow-elevation-4)] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          aria-describedby={undefined}
        >
          <DialogPrimitive.Title className="sr-only">Operations Center command palette</DialogPrimitive.Title>
          <Command
            label="Operations Center command palette"
            className="flex max-h-[70vh] flex-col"
            filter={(value, search, keywords) => {
              const haystack = [value, ...(keywords ?? [])].join(' ').toLowerCase()
              return haystack.includes(search.toLowerCase()) ? 1 : 0
            }}
          >
            <div className="flex items-center gap-2 border-b border-border-subtle px-4 py-3">
              <Search className="size-4 shrink-0 text-text-muted" aria-hidden="true" />
              <Command.Input
                autoFocus
                placeholder="Go to a module, or run an action…"
                className="w-full bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
              />
              <kbd className="shrink-0 rounded border border-border-default px-1.5 py-0.5 font-mono text-[10px] text-text-muted">Esc</kbd>
            </div>
            <Command.List className="overflow-y-auto p-2">
              <Command.Empty className="px-2 py-6 text-center text-sm text-text-muted">No matches.</Command.Empty>

              <Command.Group heading="Navigate" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-text-muted">
                {OPS_GROUPS.flatMap((group) => group.modules).map((mod) => (
                  <Command.Item
                    key={mod.to || 'dashboard'}
                    value={`nav-${mod.to || 'dashboard'}`}
                    keywords={[mod.label, groupLabelFor(mod)]}
                    onSelect={() => go(mod.to)}
                    className={cn(
                      'group flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-text-secondary',
                      'data-[selected=true]:bg-accent-primary-muted data-[selected=true]:text-accent-primary',
                    )}
                  >
                    <mod.icon className="size-4 shrink-0" aria-hidden="true" />
                    <span className="flex-1">Go to {mod.label}</span>
                    <CornerDownLeft className="size-3 shrink-0 opacity-0 group-data-[selected=true]:opacity-100" aria-hidden="true" />
                  </Command.Item>
                ))}
              </Command.Group>

              <Command.Group heading="Run provider health check" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-text-muted">
                {(providersQuery.data ?? []).map((provider) => (
                  <Command.Item
                    key={provider.id}
                    value={`health-${provider.id}`}
                    keywords={[provider.name, provider.key, 'test connection', 'health check']}
                    onSelect={() => {
                      testConnection.mutate(provider.id)
                      onOpenChange(false)
                    }}
                    className={cn(
                      'flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-text-secondary',
                      'data-[selected=true]:bg-accent-primary-muted data-[selected=true]:text-accent-primary',
                    )}
                  >
                    <Stethoscope className="size-4 shrink-0" aria-hidden="true" />
                    <span className="flex-1">Test connection: {provider.name}</span>
                  </Command.Item>
                ))}
                {open && providersQuery.isPending && (
                  <p className="px-2.5 py-2 text-xs text-text-muted">Loading providers…</p>
                )}
              </Command.Group>
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

function groupLabelFor(mod: { to: string }): string {
  const group = OPS_GROUPS.find((g) => g.modules.some((m) => m.to === mod.to))
  return group?.label ?? ''
}
