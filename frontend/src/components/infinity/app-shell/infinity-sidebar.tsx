import { useEffect, useRef, useState, type FocusEvent } from 'react'
import { Link, NavLink } from 'react-router-dom'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Pin, PinOff, Settings, CreditCard, HelpCircle, UserCircle, LogOut } from 'lucide-react'
import { cn } from '@/lib/cn'
import logoUrl from '@/assets/logo.png'
import logoMarkUrl from '@/assets/logo-mark.png'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { useUnreadAlertCount } from '@/lib/hooks/use-alerts'
import { getDisplayNameFromUser } from '@/lib/user-display-name'
import { NAV_GROUPS, BRAND } from '@/components/layout/nav-config'

const PIN_STORAGE_KEY = 'titaniq:sidebar-pinned'
const COLLAPSED_WIDTH = 68
const EXPANDED_WIDTH = 248
const COLLAPSE_DELAY_MS = 320

function readPinnedPreference(): boolean {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(PIN_STORAGE_KEY) === '1'
}

const PROFILE_MENU_ITEM_CLASS =
  'flex items-center gap-2.5 px-3 py-2 font-infinity-body text-sm text-infinity-text-secondary outline-none transition-colors data-[highlighted]:bg-infinity-ground-1 data-[highlighted]:text-infinity-text-primary'

/**
 * Infinity Sidebar — a fixed-width collapsed rail (always 68px in the real page flow, via the
 * spacer div below) with a `position: fixed` floating panel that widens on hover/focus/pin.
 * Because the flex layout only ever sees the 68px spacer, expanding the rail overlays real page
 * content instead of reflowing it — no chart, table, or card ever jumps. Collapse is debounced
 * (a short delay, cancelled if the cursor returns) so brushing past the rail edge doesn't flicker
 * it open and shut. Keyboard users get the same expand/collapse via real focus/blur, not just
 * hover, so Tabbing into the rail is never stuck in icon-only mode.
 */
export function InfinitySidebar() {
  const profile = useAuthStore((s) => s.profile)
  const session = useAuthStore((s) => s.session)
  const signOut = useAuthStore((s) => s.signOut)
  const role = profile?.role
  const unreadAlerts = useUnreadAlertCount()
  const [pinned, setPinned] = useState(readPinnedPreference)
  const [expanded, setExpanded] = useState(false)
  const collapseTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    window.localStorage.setItem(PIN_STORAGE_KEY, pinned ? '1' : '0')
  }, [pinned])

  useEffect(() => () => clearCollapseTimer(), [])

  function clearCollapseTimer() {
    if (collapseTimer.current) {
      clearTimeout(collapseTimer.current)
      collapseTimer.current = undefined
    }
  }

  function handleEnterOrFocus() {
    clearCollapseTimer()
    setExpanded(true)
  }

  function handleLeave() {
    if (pinned) return
    clearCollapseTimer()
    collapseTimer.current = setTimeout(() => setExpanded(false), COLLAPSE_DELAY_MS)
  }

  function handleBlur(e: FocusEvent<HTMLElement>) {
    if (pinned) return
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
    clearCollapseTimer()
    setExpanded(false)
  }

  const collapsed = !expanded && !pinned
  const displayName = getDisplayNameFromUser(session?.user)
  const initial = (displayName ?? profile?.email ?? '?').charAt(0).toUpperCase()
  const navGroups = NAV_GROUPS.filter((g) => g.label !== 'Account')

  return (
    <>
      {/* Reserves real layout space at a constant width so the floating rail below never shifts
          the application canvas — this div, not the rail itself, is what the flex layout sees. */}
      <div className="hidden shrink-0 lg:block" style={{ width: COLLAPSED_WIDTH }} aria-hidden="true" />

      <aside
        onMouseEnter={handleEnterOrFocus}
        onMouseLeave={handleLeave}
        onFocus={handleEnterOrFocus}
        onBlur={handleBlur}
        style={{ width: collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH, transition: 'width 200ms ease-out' }}
        className={cn(
          'fixed inset-y-0 left-0 z-40 hidden flex-col overflow-hidden border-r lg:flex',
          // Collapsed rail: Level 1 glass (persistent chrome). Expanded floating panel: Level 2
          // (more separation from the page it's now overlaying) plus the existing elevation glow.
          collapsed
            ? 'border-[var(--infinity-glass-1-border)] bg-[var(--infinity-glass-1-bg)] backdrop-blur-[var(--infinity-glass-1-blur)]'
            : 'border-[var(--infinity-glass-2-border)] bg-[var(--infinity-glass-2-bg)] shadow-[var(--infinity-elevation-2)] backdrop-blur-[var(--infinity-glass-2-blur)]',
        )}
      >
        <div className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-infinity-border-hairline px-4">
          <Link
            to="/"
            aria-label={`${BRAND.name} — back to the public site`}
            className="relative h-7 shrink-0 overflow-hidden opacity-100 transition-opacity duration-150 hover:opacity-80 motion-reduce:transition-none"
            style={{ width: collapsed ? 28 : 78 }}
          >
            {/* Collapsed: just the mark. Expanded: the full lockup. Cross-faded via opacity only
                (no width transition — that's a layout property, left to snap instantly since the
                sidebar's own 200ms width animation already carries the motion the eye tracks). */}
            <img
              src={logoMarkUrl}
              alt=""
              className={cn(
                'absolute inset-y-0 left-0 h-7 w-auto transition-opacity duration-150 motion-reduce:transition-none',
                collapsed ? 'opacity-100' : 'opacity-0',
              )}
            />
            <img
              src={logoUrl}
              alt={BRAND.name}
              className={cn(
                'absolute inset-y-0 left-0 h-7 w-auto transition-opacity duration-150 motion-reduce:transition-none',
                collapsed ? 'opacity-0' : 'opacity-100',
              )}
            />
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
          {navGroups.map((group) => {
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
                  {collapsed ? ' ' : group.label}
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

        {profile && (
          <div className="shrink-0 border-t border-infinity-border-hairline p-3">
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  type="button"
                  aria-label="Account menu"
                  className={cn(
                    'flex w-full items-center gap-2.5 rounded-infinity-sm p-1.5 text-left transition-colors hover:bg-infinity-ground-2',
                    collapsed && 'justify-center',
                  )}
                >
                  <span
                    className="flex size-7 shrink-0 items-center justify-center rounded-full bg-infinity-signal-muted font-infinity-mono text-xs font-medium text-infinity-signal"
                    aria-hidden="true"
                  >
                    {initial}
                  </span>
                  {!collapsed && (
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-infinity-body text-[13px] font-medium text-infinity-text-primary">
                        {displayName ?? profile.email}
                      </span>
                      <span className="block truncate font-infinity-mono text-[10.5px] capitalize text-infinity-text-muted">
                        {profile.role.replace('_', ' ')}
                      </span>
                    </span>
                  )}
                </button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  side="right"
                  align="end"
                  sideOffset={8}
                  className="z-50 w-52 overflow-hidden rounded-infinity-md border border-infinity-border-default bg-infinity-ground-2 py-1 shadow-[var(--infinity-elevation-2)] data-[state=open]:animate-[popover-content-in_var(--infinity-motion-base)_ease-out]"
                >
                  <DropdownMenu.Item asChild>
                    <Link to="/app/profile" className={PROFILE_MENU_ITEM_CLASS}>
                      <UserCircle className="size-4" aria-hidden="true" /> Profile
                    </Link>
                  </DropdownMenu.Item>
                  <DropdownMenu.Item asChild>
                    <Link to="/app/settings" className={PROFILE_MENU_ITEM_CLASS}>
                      <Settings className="size-4" aria-hidden="true" /> Settings
                    </Link>
                  </DropdownMenu.Item>
                  <DropdownMenu.Item asChild>
                    <Link to="/app/billing" className={PROFILE_MENU_ITEM_CLASS}>
                      <CreditCard className="size-4" aria-hidden="true" /> Upgrade
                    </Link>
                  </DropdownMenu.Item>
                  <DropdownMenu.Item asChild>
                    <Link to="/app/help" className={PROFILE_MENU_ITEM_CLASS}>
                      <HelpCircle className="size-4" aria-hidden="true" /> Help
                    </Link>
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    onSelect={() => void signOut()}
                    className="flex items-center gap-2.5 px-3 py-2 font-infinity-body text-sm text-infinity-danger outline-none transition-colors data-[highlighted]:bg-infinity-danger/10"
                  >
                    <LogOut className="size-4" aria-hidden="true" /> Sign out
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        )}
      </aside>
    </>
  )
}
