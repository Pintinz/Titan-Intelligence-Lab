import { useEffect, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Pin, PinOff } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { useUnreadAlertCount } from '@/lib/hooks/use-alerts'
import { NAV_GROUPS, BRAND } from '@/components/layout/nav-config'

const PIN_STORAGE_KEY = 'titaniq:sidebar-pinned'

function readPinnedPreference(): boolean {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(PIN_STORAGE_KEY) === '1'
}

/**
 * Infinity Sidebar — adaptive collapse like Linear/Notion's rail: expanded on first load,
 * collapses to icon-only once the cursor leaves, re-expands on hover, and can be pinned open
 * permanently (persisted). `expanded` is a separate piece of state from `pinned` rather than
 * derived only from hover, so "expanded because pinned" and "expanded because hovering" both
 * render identically — the width/label transition doesn't care which caused it.
 */
export function InfinitySidebar() {
  const role = useAuthStore((s) => s.profile?.role)
  const unreadAlerts = useUnreadAlertCount()
  const [pinned, setPinned] = useState(readPinnedPreference)
  const [expanded, setExpanded] = useState(true)

  useEffect(() => {
    window.localStorage.setItem(PIN_STORAGE_KEY, pinned ? '1' : '0')
  }, [pinned])

  const collapsed = !expanded && !pinned

  return (
    <aside
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => !pinned && setExpanded(false)}
      style={{ transition: 'width var(--infinity-motion-base)' }}
      className={cn(
        'hidden shrink-0 flex-col border-r border-infinity-border-hairline bg-infinity-ground-1 lg:flex',
        collapsed ? 'w-[68px]' : 'w-60',
      )}
    >
      <div className="flex h-14 items-center justify-between gap-2 border-b border-infinity-border-hairline px-4">
        <Link
          to="/"
          aria-label={`${BRAND.name} — back to the public site`}
          className="flex min-w-0 items-center gap-2 transition-opacity hover:opacity-80"
        >
          <span className="size-2 shrink-0 rounded-full bg-infinity-signal" aria-hidden="true" />
          <span
            className={cn(
              'truncate font-infinity-display text-sm font-semibold tracking-tight text-infinity-text-primary transition-opacity duration-150 motion-reduce:transition-none',
              collapsed ? 'w-0 opacity-0' : 'opacity-100',
            )}
          >
            {BRAND.name}
          </span>
        </Link>
        {!collapsed && (
          <button
            type="button"
            onClick={() => setPinned((p) => !p)}
            aria-label={pinned ? 'Unpin sidebar' : 'Pin sidebar open'}
            aria-pressed={pinned}
            title={pinned ? 'Unpin sidebar' : 'Pin sidebar open'}
            className={cn(
              'shrink-0 rounded-infinity-sm p-1.5 text-infinity-text-muted transition-colors hover:bg-infinity-ground-2 hover:text-infinity-text-primary',
              pinned && 'text-infinity-signal hover:text-infinity-signal',
            )}
          >
            {pinned ? <Pin className="size-3.5" aria-hidden="true" /> : <PinOff className="size-3.5" aria-hidden="true" />}
          </button>
        )}
      </div>
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-4" aria-label="Primary">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter((item) => !item.minRole || (role && isAtLeast(role, item.minRole)))
          if (items.length === 0) return null
          return (
            <div key={group.label} className="mb-5">
              <h2
                className={cn(
                  'truncate px-2.5 pb-1.5 font-infinity-body text-[11px] font-medium uppercase tracking-[0.08em] text-infinity-text-muted transition-opacity duration-150 motion-reduce:transition-none',
                  collapsed ? 'opacity-0' : 'opacity-100',
                )}
              >
                {collapsed ? ' ' : group.label}
              </h2>
              <ul className="flex flex-col gap-0.5">
                {items.map((item) => {
                  const badgeCount = item.href === '/app/notifications' ? unreadAlerts.data : undefined
                  return (
                    <li key={item.href}>
                      <NavLink
                        to={item.href}
                        end={item.href === '/app'}
                        title={collapsed ? item.label : undefined}
                        className={({ isActive }) =>
                          cn(
                            'relative flex items-center gap-2.5 border-l-2 px-2.5 py-1.5 font-infinity-body text-sm transition-colors duration-150',
                            isActive
                              ? 'border-infinity-signal bg-infinity-signal-muted text-infinity-text-primary'
                              : 'border-transparent text-infinity-text-secondary hover:bg-infinity-ground-2 hover:text-infinity-text-primary',
                          )
                        }
                      >
                        <span className="relative shrink-0">
                          <item.icon className="size-4" aria-hidden="true" />
                          {collapsed && !!badgeCount && (
                            <span
                              className="absolute -right-1.5 -top-1.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-infinity-live px-0.5 font-infinity-mono text-[9px] font-semibold leading-none text-infinity-ground-0"
                              aria-hidden="true"
                            >
                              {badgeCount > 9 ? '9+' : badgeCount}
                            </span>
                          )}
                        </span>
                        <span
                          className={cn(
                            'truncate transition-opacity duration-150 motion-reduce:transition-none',
                            collapsed ? 'w-0 opacity-0' : 'opacity-100',
                          )}
                        >
                          {item.label}
                        </span>
                        {item.live && !collapsed && (
                          <span className="ml-auto size-1.5 shrink-0 rounded-full bg-infinity-live" aria-label="Live" />
                        )}
                        {!!badgeCount && !collapsed && (
                          <span className="ml-auto shrink-0 rounded-full bg-infinity-live px-1.5 py-0.5 font-infinity-mono text-[10px] font-semibold leading-none text-infinity-ground-0">
                            {badgeCount > 9 ? '9+' : badgeCount}
                          </span>
                        )}
                      </NavLink>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </nav>
    </aside>
  )
}
