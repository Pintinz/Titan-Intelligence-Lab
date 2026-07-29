import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { NAV_GROUPS, BRAND } from './nav-config'

export function Sidebar() {
  const role = useAuthStore((s) => s.profile?.role)

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border-subtle bg-bg-secondary lg:flex">
      <div className="flex h-14 items-center gap-2 border-b border-border-subtle px-5">
        <span className="size-2 rounded-full bg-accent-primary" aria-hidden="true" />
        <span className="font-display text-sm font-semibold tracking-tight text-text-primary">
          {BRAND.name}
        </span>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Primary">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter((item) => !item.minRole || (role && isAtLeast(role, item.minRole)))
          if (items.length === 0) return null
          return (
            <div key={group.label} className="mb-5">
              <h2 className="px-2 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-text-muted">
                {group.label}
              </h2>
              <ul className="flex flex-col gap-0.5">
                {items.map((item) => (
                  <li key={item.href}>
                    <NavLink
                      to={item.href}
                      end={item.href === '/app'}
                      className={({ isActive }) =>
                        cn(
                          'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors',
                          isActive
                            ? 'bg-accent-primary-muted text-accent-primary'
                            : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary',
                        )
                      }
                    >
                      <item.icon className="size-4 shrink-0" aria-hidden="true" />
                      <span className="truncate">{item.label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </nav>
    </aside>
  )
}
