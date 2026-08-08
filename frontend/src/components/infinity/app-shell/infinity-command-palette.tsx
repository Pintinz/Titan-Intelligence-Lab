import { useNavigate } from 'react-router-dom'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Command } from 'cmdk'
import { Search, Sun, Moon, LogOut, CornerDownLeft } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { useThemeStore } from '@/stores/theme-store'
import { useWorkspaceCommandStore } from '@/stores/workspace-command-store'
import { isAtLeast } from '@/lib/api/types'
import { NAV_GROUPS } from '@/components/layout/nav-config'
import { cn } from '@/lib/cn'

/**
 * Global app command palette (Ctrl+K / Cmd+K). Every entry is real: navigation to a
 * real role-filtered route, or a real store action (theme toggle, sign out) — same "no
 * decorative actions" discipline as the Ops Center's Command Palette (Milestone 11A).
 * No entity search (matches/teams/players) is wired here — no cross-entity search
 * endpoint exists in the backend yet, and fabricating results would violate the
 * project's "no fake data" rule; navigation + account actions are what's genuinely
 * available today.
 */
export function InfinityCommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const role = useAuthStore((s) => s.profile?.role)
  const signOut = useAuthStore((s) => s.signOut)
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const workspaceCommands = useWorkspaceCommandStore((s) => s.commands)

  const visibleGroups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.minRole || (role && isAtLeast(role, item.minRole))),
  })).filter((group) => group.items.length > 0)

  function go(href: string) {
    navigate(href)
    onOpenChange(false)
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-[overlay-fade-in_var(--infinity-motion-base)_ease-out]" />
        <DialogPrimitive.Content
          className="fixed left-1/2 top-[16%] z-50 w-full max-w-xl -translate-x-1/2 overflow-hidden rounded-infinity-md border border-infinity-border-default bg-infinity-ground-2 shadow-[var(--infinity-elevation-2)] data-[state=open]:animate-[dialog-content-in_var(--infinity-motion-hold)_ease-out]"
          aria-describedby={undefined}
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <Command
            label="Command palette"
            className="flex max-h-[70vh] flex-col"
            filter={(value, search, keywords) => {
              const haystack = [value, ...(keywords ?? [])].join(' ').toLowerCase()
              return haystack.includes(search.toLowerCase()) ? 1 : 0
            }}
          >
            <div className="flex items-center gap-2 border-b border-infinity-border-hairline px-4 py-3">
              <Search className="size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
              <Command.Input
                autoFocus
                placeholder="Go to a page, or run a command…"
                className="w-full bg-transparent font-infinity-body text-sm text-infinity-text-primary placeholder:text-infinity-text-muted focus:outline-none"
              />
              <kbd className="shrink-0 rounded border border-infinity-border-default px-1.5 py-0.5 font-infinity-mono text-[10px] text-infinity-text-muted">
                Esc
              </kbd>
            </div>
            <Command.List className="overflow-y-auto p-2">
              <Command.Empty className="px-2 py-6 text-center font-infinity-body text-sm text-infinity-text-muted">No matches.</Command.Empty>

              {visibleGroups.map((group) => (
                <Command.Group
                  key={group.label}
                  heading={group.label}
                  className="mb-1 [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-infinity-body [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-infinity-text-muted"
                >
                  {group.items.map((item) => (
                    <Command.Item
                      key={item.href}
                      value={`nav-${item.href}`}
                      keywords={[item.label]}
                      onSelect={() => go(item.href)}
                      className={cn(
                        'group flex cursor-pointer items-center gap-2.5 rounded-infinity-sm px-2.5 py-2 font-infinity-body text-sm text-infinity-text-secondary',
                        'data-[selected=true]:bg-infinity-signal-muted data-[selected=true]:text-infinity-text-primary',
                      )}
                    >
                      <item.icon className="size-4 shrink-0" aria-hidden="true" />
                      <span className="flex-1">Go to {item.label}</span>
                      <CornerDownLeft className="size-3 shrink-0 opacity-0 group-data-[selected=true]:opacity-100" aria-hidden="true" />
                    </Command.Item>
                  ))}
                </Command.Group>
              ))}

              {workspaceCommands.length > 0 && (
                <Command.Group
                  heading="Intelligence Workspace"
                  className="mb-1 [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-infinity-body [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-infinity-text-muted"
                >
                  {workspaceCommands.map((cmd) => (
                    <Command.Item
                      key={cmd.id}
                      value={`workspace-${cmd.id}`}
                      keywords={[cmd.label]}
                      onSelect={() => {
                        cmd.run()
                        onOpenChange(false)
                      }}
                      className={cn(
                        'group flex cursor-pointer items-center gap-2.5 rounded-infinity-sm px-2.5 py-2 font-infinity-body text-sm text-infinity-text-secondary',
                        'data-[selected=true]:bg-infinity-signal-muted data-[selected=true]:text-infinity-text-primary',
                      )}
                    >
                      <cmd.icon className="size-4 shrink-0" aria-hidden="true" />
                      <span className="flex-1">{cmd.label}</span>
                      <CornerDownLeft className="size-3 shrink-0 opacity-0 group-data-[selected=true]:opacity-100" aria-hidden="true" />
                    </Command.Item>
                  ))}
                </Command.Group>
              )}

              <Command.Group
                heading="Account"
                className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-infinity-body [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-infinity-text-muted"
              >
                <Command.Item
                  value="toggle-theme"
                  keywords={['dark', 'light', 'appearance']}
                  onSelect={() => {
                    toggleTheme()
                    onOpenChange(false)
                  }}
                  className={cn(
                    'flex cursor-pointer items-center gap-2.5 rounded-infinity-sm px-2.5 py-2 font-infinity-body text-sm text-infinity-text-secondary',
                    'data-[selected=true]:bg-infinity-signal-muted data-[selected=true]:text-infinity-text-primary',
                  )}
                >
                  {theme === 'dark' ? <Sun className="size-4 shrink-0" aria-hidden="true" /> : <Moon className="size-4 shrink-0" aria-hidden="true" />}
                  <span className="flex-1">Switch to {theme === 'dark' ? 'light' : 'dark'} theme</span>
                </Command.Item>
                <Command.Item
                  value="sign-out"
                  keywords={['logout', 'log out']}
                  onSelect={() => {
                    onOpenChange(false)
                    void signOut()
                  }}
                  className={cn(
                    'flex cursor-pointer items-center gap-2.5 rounded-infinity-sm px-2.5 py-2 font-infinity-body text-sm text-infinity-danger',
                    'data-[selected=true]:bg-infinity-danger/10',
                  )}
                >
                  <LogOut className="size-4 shrink-0" aria-hidden="true" />
                  <span className="flex-1">Sign out</span>
                </Command.Item>
              </Command.Group>
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
