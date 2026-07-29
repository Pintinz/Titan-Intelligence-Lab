import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'

/**
 * Landing page for OAuth and magic-link redirects. Supabase's `detectSessionInUrl` handles the
 * token exchange automatically; this page just waits for the resulting auth-state change and
 * then routes on, so there is nothing here to fetch or render beyond a loading state.
 */
export function AuthCallbackPage() {
  const navigate = useNavigate()
  const status = useAuthStore((s) => s.status)

  useEffect(() => {
    if (status === 'authenticated') navigate('/app', { replace: true })
    if (status === 'unauthenticated') navigate('/login', { replace: true })
  }, [status, navigate])

  return (
    <main className="flex min-h-svh items-center justify-center bg-bg-primary text-sm text-text-muted">
      Signing you in…
    </main>
  )
}
