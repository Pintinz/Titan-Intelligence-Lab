import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { WifiOff } from 'lucide-react'
import { Sidebar } from '@/components/layout/sidebar'
import { Topbar } from '@/components/layout/topbar'
import { GlobalSearch } from '@/components/search/global-search'
import { ErrorBoundary } from '@/components/layout/error-boundary'
import { useOnlineStatus } from '@/lib/hooks/use-online-status'
import { pageTransition } from '@/lib/motion'

export function AppShell() {
  const location = useLocation()
  const online = useOnlineStatus()

  return (
    <div className="flex h-svh bg-bg-primary">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        {!online && (
          <div className="flex items-center justify-center gap-2 bg-warning-muted px-4 py-1.5 text-xs font-medium text-warning">
            <WifiOff className="h-3.5 w-3.5" aria-hidden="true" />
            You're offline — showing cached data until the connection returns.
          </div>
        )}
        <main className="flex-1 overflow-y-auto">
          <ErrorBoundary>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={location.pathname}
                variants={pageTransition}
                initial="initial"
                animate="animate"
                exit="exit"
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </ErrorBoundary>
        </main>
      </div>
      <GlobalSearch />
    </div>
  )
}
