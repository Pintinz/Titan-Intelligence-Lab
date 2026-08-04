import { Outlet } from 'react-router-dom'
import { SiteHeader } from './site-header'
import { SiteFooter } from './site-footer'

/** Shared chrome for every logged-out informational/legal page — mega-menu header, enterprise footer. */
export function MarketingShell() {
  return (
    <div className="flex min-h-svh flex-col bg-bg-primary">
      <SiteHeader />
      <main className="flex-1">
        <Outlet />
      </main>
      <SiteFooter />
    </div>
  )
}
