import { NavLink, Outlet, Link } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { useSportParam } from '@/lib/hooks/use-sport'
import { Button } from '@/components/ui/button'

const TABS = [
  { label: 'Live', to: '' },
  { label: 'Matches', to: 'matches' },
  { label: 'Teams', to: 'teams' },
  { label: 'Players', to: 'players' },
  { label: 'Competitions', to: 'competitions' },
  { label: 'Prediction Laboratory', to: 'lab' },
  { label: 'News', to: 'news' },
  { label: 'Community', to: 'community' },
]

/**
 * Wraps every `/app/:sport/*` route. One shell serves all four Sport Intelligence Centers —
 * "only market types differ by sport" (brief) — so this is the template, not football-specific.
 */
export function SportShell() {
  const sport = useSportParam()

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

  return (
    <div>
      <div className="border-b border-border-subtle px-4 pt-5 lg:px-8">
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Intelligence Center
        </p>
        <h1 className="mt-0.5 font-display text-xl font-semibold text-text-primary">{sport.label}</h1>
        <nav className="mt-4 flex gap-1 overflow-x-auto" aria-label={`${sport.label} sections`}>
          {TABS.map((tab) => (
            <NavLink
              key={tab.label}
              to={`/app/${sport.slug}${tab.to ? `/${tab.to}` : ''}`}
              end={tab.to === ''}
              className={({ isActive }) =>
                cn(
                  'shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'border-accent-primary text-text-primary'
                    : 'border-transparent text-text-secondary hover:text-text-primary',
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="p-4 lg:p-8">
        <Outlet />
      </div>
    </div>
  )
}
