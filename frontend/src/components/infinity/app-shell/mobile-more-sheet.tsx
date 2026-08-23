import * as DialogPrimitive from '@radix-ui/react-dialog'
import { NavLink } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { Radio, Star, Bookmark, Bell, Compass, Trophy, UserRound, Users, Share2, ServerCog, FlaskConical, Settings, CreditCard, HelpCircle, UserCircle } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { useUnreadAlertCount } from '@/lib/hooks/use-alerts'

interface MoreItem {
  label: string
  href: string
  icon: LucideIcon
  minRole?: 'administrator'
  badge?: number
}

/** Every real destination that doesn't have its own bottom tab — reachable, never deleted, just
 * one level deeper (the same "demoted, not removed" precedent `nav-config.ts` already documents
 * for Live/AI Picks/Watchlist/Workspace on desktop). Teams/Players/Competitions/Knowledge Graph
 * come from the same `NAV_GROUPS` Explore group the desktop sidebar reads; this list only adds the
 * items `NAV_GROUPS` deliberately excludes (Live, AI Picks, Watchlist, Notifications, Workspace)
 * rather than inventing a second navigation model. */
function useMoreItems(): MoreItem[] {
  const unread = useUnreadAlertCount()
  return [
    { label: 'Live', href: '/app/live', icon: Radio },
    { label: 'AI Picks', href: '/app/picks', icon: Star },
    { label: 'Watchlist', href: '/app/watchlist', icon: Bookmark },
    { label: 'Notifications', href: '/app/notifications', icon: Bell, badge: unread.data },
    { label: 'Intelligence Workspace', href: '/app/insights', icon: Compass },
    { label: 'Teams', href: '/app/teams', icon: Users },
    { label: 'Players', href: '/app/players', icon: UserRound },
    { label: 'Competitions', href: '/app/competitions', icon: Trophy },
    { label: 'Knowledge Graph', href: '/app/graph', icon: Share2 },
    { label: 'Operations Center', href: '/app/ops', icon: ServerCog, minRole: 'administrator' },
    { label: 'Prediction Laboratory', href: '/app/football/lab', icon: FlaskConical, minRole: 'administrator' },
    { label: 'Upgrade', href: '/app/billing', icon: CreditCard },
    { label: 'Settings', href: '/app/settings', icon: Settings },
    { label: 'Help', href: '/app/help', icon: HelpCircle },
    { label: 'Profile', href: '/app/profile', icon: UserCircle },
  ]
}

export function MobileMoreSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const role = useAuthStore((s) => s.profile?.role)
  const items = useMoreItems().filter((item) => !item.minRole || (role && isAtLeast(role, item.minRole)))

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-40 bg-black/60',
            'data-[state=open]:animate-[overlay-fade-in_var(--infinity-motion-base)_ease-out]',
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            'fixed inset-x-0 bottom-0 z-50 max-h-[75svh] overflow-y-auto rounded-t-2xl border-t border-infinity-border-hairline bg-infinity-ground-1 pb-[env(safe-area-inset-bottom)]',
            'data-[state=open]:animate-[dialog-content-in_var(--infinity-motion-hold)_ease-out]',
          )}
        >
          <DialogPrimitive.Title className="sr-only">More</DialogPrimitive.Title>
          <div className="mx-auto mt-2.5 h-1 w-9 shrink-0 rounded-full bg-infinity-border-default" aria-hidden="true" />
          <ul className="grid grid-cols-3 gap-1 px-3 py-4">
            {items.map((item) => (
              <li key={item.href}>
                <NavLink
                  to={item.href}
                  onClick={() => onOpenChange(false)}
                  className={({ isActive }) =>
                    cn(
                      'relative flex flex-col items-center gap-1.5 rounded-lg px-2 py-3 text-center font-infinity-body text-[11px] transition-colors',
                      isActive ? 'bg-infinity-signal-muted text-infinity-text-primary' : 'text-infinity-text-secondary hover:bg-infinity-ground-2',
                    )
                  }
                >
                  <span className="relative">
                    <item.icon className="size-5" aria-hidden="true" />
                    {!!item.badge && (
                      <span className="absolute -right-1.5 -top-1.5 flex size-3.5 items-center justify-center rounded-full bg-infinity-danger text-[8px] font-semibold text-white">
                        {item.badge > 9 ? '9+' : item.badge}
                      </span>
                    )}
                  </span>
                  <span className="line-clamp-2 leading-tight">{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
