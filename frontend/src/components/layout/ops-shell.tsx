import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/cn'

/**
 * Operations Center shell — a two-tier nav distinguishing live admin modules
 * (built in Phase 6 with real backend endpoints) from planned modules (Phase 7+
 * or no backend — Users, Billing/Revenue, Security, Audit Center, Logs, Alerts).
 * "Planned" doesn't mean "stub pages" — it means we know they're coming but the
 * backend work hasn't landed yet, so honest labeling beats pretend-ready.
 */

const LIVE_MODULES = [
  { label: 'Executive Dashboard', to: '' },
  { label: 'Provider Management', to: 'providers' },
  { label: 'Feature Flags', to: 'flags' },
  { label: 'Data Pipeline', to: 'pipeline' },
  { label: 'Feature Store', to: 'features' },
  { label: 'Prediction Engine', to: 'markets' },
  { label: 'ML Operations', to: 'ml' },
  { label: 'Knowledge Graph', to: 'graph' },
]

const PLANNED_MODULES = [
  { label: 'Users & Roles', to: 'planned/users' },
  { label: 'Organizations', to: 'planned/organizations' },
  { label: 'Billing & Revenue', to: 'planned/billing' },
  { label: 'Security & Compliance', to: 'planned/security' },
  { label: 'Audit Center', to: 'planned/audit' },
  { label: 'Logs & Debugging', to: 'planned/logs' },
  { label: 'Alerts & Monitoring', to: 'planned/alerts' },
]

export function OpsShell() {
  return (
    <div>
      <div className="border-b border-border-subtle px-4 pt-5 lg:px-8">
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Administration
        </p>
        <h1 className="mt-0.5 font-display text-xl font-semibold text-text-primary">Operations Center</h1>

        <div className="mt-4 space-y-4">
          <nav className="flex flex-wrap gap-1 overflow-x-auto" aria-label="Live admin modules">
            {LIVE_MODULES.map((mod) => (
              <NavLink
                key={mod.to}
                to={`/app/ops${mod.to ? `/${mod.to}` : ''}`}
                end={mod.to === ''}
                className={({ isActive }) =>
                  cn(
                    'shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'border-accent-primary text-text-primary'
                      : 'border-transparent text-text-secondary hover:text-text-primary',
                  )
                }
              >
                {mod.label}
              </NavLink>
            ))}
          </nav>

          <div className="border-t border-border-subtle pt-3">
            <p className="mb-2 font-telemetry text-xs text-text-muted">Planned modules</p>
            <nav className="flex flex-wrap gap-1 overflow-x-auto" aria-label="Planned admin modules">
              {PLANNED_MODULES.map((mod) => (
                <NavLink
                  key={mod.to}
                  to={`/app/ops/${mod.to}`}
                  className="shrink-0 whitespace-nowrap rounded-md border border-border-subtle px-2.5 py-1 text-xs font-medium text-text-muted opacity-50 cursor-not-allowed"
                >
                  {mod.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </div>
      </div>
      <div className="p-4 lg:p-8">
        <Outlet />
      </div>
    </div>
  )
}
