import { useEffect } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { RouterProvider } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/toaster'
import { queryClient } from '@/lib/query-client'
import { router } from '@/router'
import { isNativePlatform } from '@/lib/capacitor'
import { initNativeOAuthListener } from '@/lib/native-oauth'

function App() {
  // Native Google OAuth return path (see lib/native-oauth.ts) — `router.navigate` is the same
  // imperative API `<RouterProvider>` itself uses internally, so this needs no route-tree
  // component of its own to call `useNavigate()` from; a no-op on web.
  useEffect(() => {
    if (!isNativePlatform()) return
    return initNativeOAuthListener(router.navigate)
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        <RouterProvider router={router} />
        <Toaster />
      </TooltipProvider>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  )
}

export default App
