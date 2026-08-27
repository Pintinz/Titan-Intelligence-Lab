import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Menu, Search, Sun, Moon, Bell, LogOut, Settings, HelpCircle, ChevronDown } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { useThemeStore } from '@/stores/theme-store'
import { useCommandPaletteStore } from '@/stores/command-palette-store'
import { useUnreadAlertCount } from '@/lib/hooks/use-alerts'
import { isNativePlatform } from '@/lib/capacitor'
import logoUrl from '@/assets/logo.png'
import { BRAND } from '@/components/layout/nav-config'
import { InfinityAppBreadcrumbs } from './infinity-breadcrumbs'
import { InfinityCommandPalette } from './infinity-command-palette'

/**
 * Infinity Topbar — search trigger (opens the real Command Palette, not a dead input),
 * theme toggle (reuses `useThemeStore` — no new theme state introduced), notifications
 * (links to `/app/notifications`, now a real Alert Center — the unread badge reflects
 * `GET /api/v1/alerts/unread-count`, polled every 30s), and a real profile menu (email,
 * role, settings, help, sign out) sourced from `useAuthStore`.
 *
 * The brand mark (`lg:hidden`, same breakpoint the hamburger button itself uses) covers the one
 * gap `InfinitySidebar`'s own logo doesn't: below `lg`, the sidebar is hidden entirely (mobile
 * drawer takes over instead), so without this the topbar carried no brand presence at all until
 * a user opened the drawer. The topbar's own glass treatment (this header's own background/
 * backdrop-blur below, `--infinity-glass-1-*`) already applies at every width — only the
 * sidebar's logo+glass are what disappear below `lg`.
 */
export function InfinityTopbar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const paletteOpen = useCommandPaletteStore((s) => s.open)
  const setPaletteOpen = useCommandPaletteStore((s) => s.setOpen)
  const togglePalette = useCommandPaletteStore((s) => s.toggle)
  const profile = useAuthStore((s) => s.profile)
  const signOut = useAuthStore((s) => s.signOut)
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const unreadCount = useUnreadAlertCount()

  const initial = (profile?.email ?? '?').charAt(0).toUpperCase()

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        togglePalette()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [togglePalette])

  return (
    <>
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--infinity-glass-1-border)] bg-[var(--infinity-glass-1-bg)] px-4 backdrop-blur-[var(--infinity-glass-1-blur)] lg:px-6">
        <button
          type="button"
          className={`text-infinity-text-secondary lg:hidden ${isNativePlatform() ? 'hidden' : ''}`}
          onClick={onOpenMobileNav}
          aria-label="Open navigation menu"
        >
          <Menu className="size-4.5" />
        </button>

        <Link to="/" aria-label={`${BRAND.name} — back to the public site`} className="shrink-0 lg:hidden">
          <img src={logoUrl} alt={BRAND.name} className="h-6 w-auto" />
        </Link>

        <div className="hidden lg:block">
          <InfinityAppBreadcrumbs />
        </div>

        <div className="flex-1" />

        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="flex w-56 items-center gap-2 rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-1 px-2.5 py-1.5 text-infinity-text-muted transition-colors duration-150 hover:border-infinity-border-strong hover:text-infinity-text-secondary"
        >
          <Search className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="flex-1 truncate text-left font-infinity-body text-[13px]">Search…</span>
          <kbd className="shrink-0 rounded border border-infinity-border-subtle px-1 py-0.5 font-infinity-mono text-[10px]">Ctrl K</kbd>
        </button>

        <button
          type="button"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          className="flex size-8 items-center justify-center rounded-infinity-sm text-infinity-text-secondary transition-colors duration-150 hover:bg-infinity-ground-1 hover:text-infinity-text-primary"
        >
          {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>

        <Link
          to="/app/notifications"
          aria-label={unreadCount.data ? `Notifications, ${unreadCount.data} unread` : 'Notifications'}
          className="relative flex size-8 items-center justify-center rounded-infinity-sm text-infinity-text-secondary transition-colors duration-150 hover:bg-infinity-ground-1 hover:text-infinity-text-primary"
        >
          <Bell className="size-4" />
          {!!unreadCount.data && (
            <span className="absolute right-1 top-1 flex size-3.5 items-center justify-center rounded-full bg-infinity-signal font-infinity-mono text-[9px] font-semibold text-infinity-ground-0">
              {unreadCount.data > 9 ? '9+' : unreadCount.data}
            </span>
          )}
        </Link>

        {profile && (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button
                type="button"
                className="flex items-center gap-1.5 rounded-infinity-sm border-l border-infinity-border-hairline py-1 pl-3 text-infinity-text-secondary transition-colors duration-150 hover:text-infinity-text-primary"
              >
                <span
                  className="flex size-7 items-center justify-center rounded-full bg-infinity-signal-muted font-infinity-mono text-xs font-medium text-infinity-signal"
                  aria-hidden="true"
                >
                  {initial}
                </span>
                <ChevronDown className="size-3.5" aria-hidden="true" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                sideOffset={8}
                className="z-50 w-56 overflow-hidden rounded-infinity-md border border-infinity-border-default bg-infinity-ground-2 py-1 shadow-[var(--infinity-elevation-2)] data-[state=open]:animate-[popover-content-in_var(--infinity-motion-base)_ease-out]"
              >
                <div className="border-b border-infinity-border-hairline px-3 py-2.5">
                  <p className="truncate font-infinity-body text-sm font-medium text-infinity-text-primary">{profile.email}</p>
                  <p className="mt-0.5 font-infinity-mono text-[11px] capitalize text-infinity-text-muted">{profile.role.replace('_', ' ')}</p>
                </div>
                <DropdownMenu.Item asChild>
                  <Link
                    to="/app/settings"
                    className="flex items-center gap-2.5 px-3 py-2 font-infinity-body text-sm text-infinity-text-secondary outline-none transition-colors data-[highlighted]:bg-infinity-ground-1 data-[highlighted]:text-infinity-text-primary"
                  >
                    <Settings className="size-4" aria-hidden="true" /> Settings
                  </Link>
                </DropdownMenu.Item>
                <DropdownMenu.Item asChild>
                  <Link
                    to="/app/help"
                    className="flex items-center gap-2.5 px-3 py-2 font-infinity-body text-sm text-infinity-text-secondary outline-none transition-colors data-[highlighted]:bg-infinity-ground-1 data-[highlighted]:text-infinity-text-primary"
                  >
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
        )}
      </header>

      <InfinityCommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </>
  )
}
