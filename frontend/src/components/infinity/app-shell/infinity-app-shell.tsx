import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { ErrorBoundary } from '@/components/layout/error-boundary'
import { InfinitySidebar } from './infinity-sidebar'
import { InfinityMobileNav } from './infinity-mobile-nav'
import { InfinityTopbar } from './infinity-topbar'

/**
 * Infinity AppShell — Phase 11.1. Structurally identical to the legacy `AppShell`
 * (sidebar + mobile drawer + topbar + `<Outlet />` wrapped in the same `ErrorBoundary`,
 * reused verbatim rather than rebuilt), restyled with the Infinity token system. Built
 * alongside the legacy shell, not in place of it — see DESIGN_INFINITY.md for the
 * migration plan. Every child route (Dashboard, Sport Intelligence Centers, Operations
 * Center, etc.) is untouched by this phase; they simply render inside whichever shell
 * wraps `/app`.
 */
export function InfinityAppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="flex h-svh bg-infinity-ground-0">
      <InfinitySidebar />
      <InfinityMobileNav open={mobileNavOpen} onOpenChange={setMobileNavOpen} />
      <div className="flex min-w-0 flex-1 flex-col">
        <InfinityTopbar onOpenMobileNav={() => setMobileNavOpen(true)} />
        <main className="flex-1 overflow-y-auto">
          {/* Mobile keeps only a few px of side margin (px-2) so cards/tables reach near the
              screen edge instead of the old p-4 (16px) eating usable width on a 375px viewport —
              lg:p-6 (desktop) is unchanged, it already had room to spare. */}
          <div className="mx-auto max-w-[1600px] px-2 py-4 lg:p-6">
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  )
}
