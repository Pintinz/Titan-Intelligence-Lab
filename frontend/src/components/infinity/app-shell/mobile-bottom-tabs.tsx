import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutGrid, CalendarDays, Newspaper, Search, Menu } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useCommandPaletteStore } from '@/stores/command-palette-store'
import { MobileMoreSheet } from './mobile-more-sheet'

/**
 * Native bottom-tab bar (Home/Matches/Context/Search/More) — the real "5 fixed tabs always
 * visible" pattern a native app needs, replacing the responsive drawer only inside the Capacitor
 * shell (gated by `isNativePlatform()` in the parent shell, never rendered on web/PWA). The three
 * link tabs read the exact same routes `NAV_GROUPS` already points at (`/app`, `/app/matches`,
 * `/app/context`) — no second nav data source. Search opens the one real Command Palette this app
 * already has (quick actions/navigation today, not cross-entity search — no fabricated search
 * result surface was added here). More opens a bottom sheet listing every other real destination.
 *
 * `pb-[env(safe-area-inset-bottom)]` respects the home-indicator/gesture-bar safe area on iOS and
 * gesture-nav Android — untestable in a browser (the env() var is 0 outside a real device), but
 * required for a real device to not clip the bar under the OS's own gesture chrome.
 */
export function MobileBottomTabs() {
  const [moreOpen, setMoreOpen] = useState(false)
  const togglePalette = useCommandPaletteStore((s) => s.toggle)

  return (
    <>
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-40 flex h-14 items-stretch border-t border-infinity-border-hairline bg-infinity-ground-0 pb-[env(safe-area-inset-bottom)]"
      >
        <TabLink to="/app" end icon={LayoutGrid} label="Home" />
        <TabLink to="/app/matches" icon={CalendarDays} label="Matches" />
        <TabLink to="/app/context" icon={Newspaper} label="Context" />
        <TabButton icon={Search} label="Search" onClick={togglePalette} />
        <TabButton icon={Menu} label="More" onClick={() => setMoreOpen(true)} active={moreOpen} />
      </nav>
      <MobileMoreSheet open={moreOpen} onOpenChange={setMoreOpen} />
    </>
  )
}

function TabLink({ to, end, icon: Icon, label }: { to: string; end?: boolean; icon: typeof LayoutGrid; label: string }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          'flex flex-1 flex-col items-center justify-center gap-0.5 font-infinity-body text-[10px] font-medium transition-colors',
          isActive ? 'text-infinity-signal' : 'text-infinity-text-secondary',
        )
      }
    >
      <Icon className="size-5" aria-hidden="true" />
      {label}
    </NavLink>
  )
}

function TabButton({ icon: Icon, label, onClick, active }: { icon: typeof LayoutGrid; label: string; onClick: () => void; active?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-1 flex-col items-center justify-center gap-0.5 font-infinity-body text-[10px] font-medium transition-colors',
        active ? 'text-infinity-signal' : 'text-infinity-text-secondary',
      )}
    >
      <Icon className="size-5" aria-hidden="true" />
      {label}
    </button>
  )
}
