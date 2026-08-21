import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { supabase } from '@/lib/supabase'
import { Button } from '@/components/ui/button'

/**
 * Lands here after a Supabase OAuth redirect (Google Sign-In — `AuthFlow.handleGoogleSignIn`).
 * `detectSessionInUrl: true` (lib/supabase.ts) means the Supabase client already exchanges the
 * URL's auth code for a session as soon as it loads on this page — this component's only job is
 * to wait for that to land (via `onAuthStateChange`, which fires once with the resolved session,
 * `null` included) and route onward. `returnTo` travels via the query string rather than router
 * state: this is a real cross-origin redirect through Google, not client-side navigation, so
 * whatever `AuthFlow` had in memory before the redirect is gone by the time we're back.
 */
export default function AuthCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [failed, setFailed] = useState(false)
  const settled = useRef(false)

  useEffect(() => {
    const returnTo = searchParams.get('returnTo') || '/'

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (settled.current) return
      settled.current = true
      if (session) {
        navigate(returnTo, { replace: true })
      } else {
        setFailed(true)
      }
    })

    // onAuthStateChange's first call can occasionally lag behind the URL-token exchange by more
    // than a moment (e.g. a slow network) — an honest timeout beats a spinner that never resolves.
    const timeout = window.setTimeout(() => {
      if (settled.current) return
      settled.current = true
      setFailed(true)
    }, 10_000)

    return () => {
      subscription.subscription.unsubscribe()
      window.clearTimeout(timeout)
    }
  }, [navigate, searchParams])

  if (failed) {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="font-display text-lg font-semibold text-text-primary">Sign-in didn't complete</p>
        <p className="max-w-sm text-sm text-text-secondary">
          Something went wrong finishing Google sign-in. Try again from the login page.
        </p>
        <Button asChild variant="secondary" size="sm">
          <a href="/login">Back to login</a>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <p className="text-sm text-text-muted">Signing you in…</p>
    </div>
  )
}
