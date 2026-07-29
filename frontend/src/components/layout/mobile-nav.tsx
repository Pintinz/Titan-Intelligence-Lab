import { useState } from 'react'
import { Menu } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { VisuallyHidden } from '@radix-ui/react-visually-hidden'
import { Button } from '@/components/ui/button'
import { NAV_GROUPS } from '@/components/layout/nav-config'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { cn } from '@/lib/cn'

export function MobileNav() {
  const [open, setOpen] = useState(false)
  const role = useAuthStore((s) => s.profile?.role)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">
        <Menu className="h-5 w-5" />
      </Button>
      <DialogContent className="left-0 top-0 h-svh max-w-72 -translate-x-0 -translate-y-0 rounded-none border-r border-l-0 border-t-0 border-b-0 p-0">
        <VisuallyHidden>
          <DialogTitle>Navigation</DialogTitle>
        </VisuallyHidden>
        <nav className="flex h-full flex-col gap-5 overflow-y-auto p-4 pt-6">
          <span className="px-2 font-display text-sm font-semibold text-text-primary">TitanIQ</span>
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
                      onClick={() => setOpen(false)}
                      className={({ isActive }) =>
                        cn(
                          'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-text-secondary transition-colors',
                          'hover:bg-bg-secondary hover:text-text-primary',
                          isActive && 'bg-bg-secondary font-medium text-text-primary',
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
      </DialogContent>
    </Dialog>
  )
}
