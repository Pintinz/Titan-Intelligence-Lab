import { NavLink, Outlet, Link } from 'react-router-dom'
import { CalendarDays, Users, User, Trophy, Hammer } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { Button } from '@/components/ui/button'

// Prediction Laboratory / News / Community stay real, routable pages (linked contextually from
// match/team pages) but aren't ready to carry primary navigation weight yet — pulled from the
// tab bar rather than left half-finished in front of every user. "Live" was pulled too
// (2026-08-23) — match-list-page.tsx already surfaces live fixtures via its own LiveRail + live
// KPI, so a separate primary "Live" destination was pure duplication (and the IA brief that
// shaped this app's primary nav explicitly said not to give Live its own destination). Matches
// is the index route now (see router.tsx's redirect) rather than a since-removed Live hub.
//
// Each tab carries its own accent (`activeColor`/`iconColor`) so the bar reads as four distinct
// destinations at a glance, not four identical pills differing only by label — the active pill
// tints with that tab's own color instead of one shared brand accent, so "which section" and
// "what's selected" are communicated by the same signal.
const TABS = [
  { label: 'Matches', to: 'matches', icon: CalendarDays, iconColor: 'var(--infinity-domain-football)', activeBg: 'var(--infinity-domain-football)' },
  { label: 'Teams', to: 'teams', icon: Users, iconColor: 'var(--infinity-domain-community)', activeBg: 'var(--infinity-domain-community)' },
  { label: 'Players', to: 'players', icon: User, iconColor: 'var(--infinity-signal)', activeBg: 'var(--infinity-signal)' },
  { label: 'Competitions', to: 'competitions', icon: Trophy, iconColor: 'var(--infinity-warning)', activeBg: 'var(--infinity-warning)' },
]

/**
 * Wraps every `/app/:sport/*` route. One shell serves all four Sport Intelligence Centers —
 * "only market types differ by sport" (brief) — so this is the template, not football-specific.
 */
export function SportShell() {
  const sport = useSportParam()
  const profile = useAuthStore((s) => s.profile)
  const isAdmin = !!profile && isAtLeast(profile.role, 'administrator')

  if (!sport) {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-center">
        <p className="font-display text-lg font-semibold text-text-primary">Unknown sport</p>
        <p className="text-sm text-text-secondary">TitanIQ covers Football, Basketball, Baseball, and Table Tennis.</p>
        <Button asChild variant="secondary" size="sm">
          <Link to="/app">Back to Dashboard</Link>
        </Button>
      </div>
    )
  }

  // Basketball/Baseball/Table Tennis are still under active development — same gate the backend
  // enforces server-side (sports_router.require_football_or_admin); a regular user reaching this
  // route directly (typed URL, stale link) sees an honest "not open yet" state instead of a
  // half-working shell whose data requests all silently 404.
  if (sport.code !== 'football' && !isAdmin) {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-center">
        <Hammer className="size-8 text-text-muted" aria-hidden="true" />
        <p className="font-display text-lg font-semibold text-text-primary">{sport.label} isn't open yet</p>
        <p className="max-w-sm text-sm text-text-secondary">
          We're still building out {sport.label} intelligence — Football is live today. Check back soon.
        </p>
        <Button asChild variant="secondary" size="sm">
          <Link to="/app/football">Go to Football</Link>
        </Button>
      </div>
    )
  }

  return (
    <div>
      {/* No horizontal padding here — InfinityAppShell's `main` (p-4 lg:p-6) already pads every
          /app/* page; stacking a second px-4/lg:px-8 here doubled the mobile side margins
          (32px wasted per side at 375px width) on every Sport Intelligence Center page. */}
      <div className="border-b border-border-subtle pt-5">
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Intelligence Center
        </p>
        <h1 className="mt-0.5 font-display text-xl font-semibold text-text-primary">{sport.label}</h1>
        <nav
          className="mt-4 flex w-fit max-w-full gap-0.5 overflow-x-auto rounded-full border border-border-subtle bg-bg-secondary p-1"
          aria-label={`${sport.label} sections`}
        >
          {TABS.map((tab) => (
            <NavLink
              key={tab.label}
              to={`/app/${sport.slug}/${tab.to}`}
              className={({ isActive }) =>
                cn(
                  'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors duration-200',
                  !isActive && 'text-text-secondary hover:text-text-primary',
                )
              }
              style={({ isActive }) =>
                isActive
                  ? {
                      backgroundColor: `color-mix(in srgb, ${tab.activeBg} 16%, transparent)`,
                      boxShadow: `0 0 0 1px color-mix(in srgb, ${tab.activeBg} 40%, transparent) inset`,
                      color: tab.activeBg,
                    }
                  : undefined
              }
            >
              <tab.icon className="size-3.5" aria-hidden="true" />
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="pt-4 lg:pt-8">
        <Outlet />
      </div>
    </div>
  )
}
