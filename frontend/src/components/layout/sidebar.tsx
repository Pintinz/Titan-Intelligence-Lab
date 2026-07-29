import { NavLink } from 'react-router-dom'
import { NAV_GROUPS } from '@/components/layout/nav-config'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { cn } from '@/lib/cn'

export function Sidebar() {
  const role = useAuthStore((s) => s.profile?.role)

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border-subtle bg-bg-secondary px-3 py-4 lg:flex">
      <div className="px-2 pb-4">
        <span className="font-display text-sm font-semibold tracking-wide text-text-primary">TitanIQ</span>
      </div>
      <nav className="flex flex-1 flex-col gap-5 overflow-y-auto">
        {NAV_GROUPS.map((group) => {
          const visibleItems = group.items.filter((item) => !item.minRole || (role && isAtLeast(role, item.minRole)))
          if (visibleItems.length === 0) return null
          return (
            <div key={group.label}>
              <p className="px-2 pb-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">{group.label}</p>
              <div className="flex flex-col gap-0.5">
                {visibleItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/app'}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-text-secondary transition-colors',
                        'hover:bg-bg-elevated hover:text-text-primary',
                        isActive && 'bg-bg-elevated font-medium text-text-primary',
                      )
                    }
                  >
                    <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {item.label}
                  </NavLink>
                ))}
              </div>
            </div>
          )
        })}
      </nav>
    </aside>
  )
}
