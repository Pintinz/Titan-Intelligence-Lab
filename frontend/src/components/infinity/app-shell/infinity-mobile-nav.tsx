import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import logoUrl from '@/assets/logo.png'
import { NAV_GROUPS, BRAND } from '@/components/layout/nav-config'

/** Infinity Mobile Nav — same drawer pattern and NAV_GROUPS data as the legacy
 * `MobileNav`, restyled. Kept as a Radix Dialog (not reinvented) since the modal
 * focus-trap/escape/overlay behavior it provides is exactly what a slide-out nav needs,
 * and Phase 11.0 didn't rebuild dialog primitives. */
export function InfinityMobileNav({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const role = useAuthStore((s) => s.profile?.role)

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-40 bg-black/60 lg:hidden',
            'data-[state=open]:animate-[overlay-fade-in_var(--infinity-motion-base)_ease-out]',
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            'fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r lg:hidden',
            // Same Level 2 glass the desktop sidebar's own expanded panel uses
            // (infinity-sidebar.tsx) — this drawer is that panel's mobile equivalent, so it
            // carries the same translucent-surface/backdrop-blur/elevation treatment rather than
            // a flat, opaque fill.
            'border-[var(--infinity-glass-2-border)] bg-[var(--infinity-glass-2-bg)] shadow-[var(--infinity-elevation-2)] backdrop-blur-[var(--infinity-glass-2-blur)]',
            'data-[state=open]:animate-[dialog-content-in_var(--infinity-motion-hold)_ease-out]',
          )}
        >
          <DialogPrimitive.Title className="sr-only">Navigation</DialogPrimitive.Title>
          <div className="flex h-14 items-center justify-between border-b border-infinity-border-hairline px-5">
            <Link
              to="/"
              aria-label={`${BRAND.name} — back to the public site`}
              onClick={() => onOpenChange(false)}
              className="opacity-100 transition-opacity hover:opacity-80"
            >
              <img src={logoUrl} alt={BRAND.name} className="h-7 w-auto" />
            </Link>
            <DialogPrimitive.Close aria-label="Close navigation menu" className="text-infinity-text-secondary">
              <X className="size-4" />
            </DialogPrimitive.Close>
          </div>
          <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Primary">
            {NAV_GROUPS.map((group) => {
              const items = group.items.filter((item) => !item.minRole || (role && isAtLeast(role, item.minRole)))
              if (items.length === 0) return null
              return (
                <div key={group.label} className="mb-5">
                  <h2 className="px-2.5 pb-1.5 font-infinity-body text-[11px] font-medium uppercase tracking-[0.08em] text-infinity-text-muted">
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
                              'flex items-center gap-2.5 border-l-2 px-2.5 py-1.5 font-infinity-body text-sm transition-colors duration-150',
                              isActive
                                ? 'border-infinity-signal bg-infinity-signal-muted text-infinity-text-primary'
                                : 'border-transparent text-infinity-text-secondary hover:bg-infinity-ground-2 hover:text-infinity-text-primary',
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
