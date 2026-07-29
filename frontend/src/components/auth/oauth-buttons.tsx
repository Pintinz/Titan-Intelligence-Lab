import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { supabase } from '@/lib/supabase'
import { toast } from '@/stores/toast-store'

const PROVIDERS = [
  { id: 'google', label: 'Continue with Google' },
  { id: 'github', label: 'Continue with GitHub' },
] as const

export function OAuthButtons() {
  const [loadingProvider, setLoadingProvider] = useState<string | null>(null)

  async function handleOAuth(provider: 'google' | 'github') {
    setLoadingProvider(provider)
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    })
    if (error) {
      toast.danger('Sign-in failed', error.message)
      setLoadingProvider(null)
    }
    // On success the browser navigates away to the provider immediately — no further state
    // update needed here; the flow completes at /auth/callback via onAuthStateChange.
  }

  return (
    <div className="flex flex-col gap-2">
      {PROVIDERS.map((provider) => (
        <Button
          key={provider.id}
          type="button"
          variant="secondary"
          loading={loadingProvider === provider.id}
          disabled={loadingProvider !== null}
          onClick={() => handleOAuth(provider.id)}
        >
          {provider.label}
        </Button>
      ))}
    </div>
  )
}
