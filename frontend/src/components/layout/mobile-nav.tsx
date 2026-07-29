import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { NAV_GROUPS, BRAND } from './nav-config'

export function MobileNav({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const role = useAuthStore((s) => s.profile?.role)

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-40 bg-bg-overlay lg:hidden',
            'data-[state=open]:animate-[overlay-fade-in_var(--motion-duration-fast)_var(--motion-easing-standard)]',
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            'fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-bg-secondary lg:hidden',
            'data-[state=open]:animate-[dialog-content-in_var(--motion-duration-base)_var(--motion-easing-decelerate)]',
          )}
        >
          <DialogPrimitive.Title className="sr-only">Navigation</DialogPrimitive.Title>
          <div className="flex h-14 items-center justify-between border-b border-border-subtle px-5">
            <span className="font-display text-sm font-semibold text-text-primary">{BRAND.name}</span>
            <DialogPrimitive.Close aria-label="Close navigation menu" className="text-text-secondary">
              <X className="size-4" />
            </DialogPrimitive.Close>
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
                          onClick={() => onOpenChange(false)}
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
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
