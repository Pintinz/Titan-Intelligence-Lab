import { create } from 'zustand'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '@/lib/supabase'
import { identityApi } from '@/lib/api/identity'
import type { UserDto } from '@/lib/api/types'
import { queryClient } from '@/lib/query-client'

interface AuthState {
  session: Session | null
  profile: UserDto | null
  status: 'loading' | 'authenticated' | 'unauthenticated'
  refreshProfile: () => Promise<void>
  signOut: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  session: null,
  profile: null,
  status: 'loading',

  refreshProfile: async () => {
    try {
      const profile = await identityApi.me()
      set({ profile })
    } catch {
      set({ profile: null })
    }
  },

  signOut: async () => {
    await supabase.auth.signOut()
    set({ session: null, profile: null, status: 'unauthenticated' })
  },
}))

// Supabase's own listener is the single source of truth for session state — it fires immediately
// with the persisted session on load (event INITIAL_SESSION) and on every subsequent
// sign-in/refresh/sign-out, so nothing else in the app should call supabase.auth.getSession()
// directly for UI state (only the API client does, per-request, for the bearer token itself).
//
// React Query's cache is keyed by query shape (e.g. ['predictions', 'entitlement']), never by
// user — nothing scoped it per-user, so signing out and signing back in as someone else in the
// same tab (no full page reload) kept serving the previous user's cached prediction credits,
// watchlist, alerts, etc. until each query happened to refetch on its own. Clearing the cache
// whenever the authenticated user id actually changes (sign-out -> null, or a genuine account
// switch) closes that gap; a token refresh for the SAME user must NOT clear it — that would just
// be wasted refetches on an interval that has nothing to do with identity changing.
let lastUserId: string | null = null
supabase.auth.onAuthStateChange((_event, session) => {
  const nextUserId = session?.user.id ?? null
  if (nextUserId !== lastUserId) {
    queryClient.clear()
  }
  lastUserId = nextUserId

  useAuthStore.setState({ session, status: session ? 'authenticated' : 'unauthenticated' })
  if (session) {
    void useAuthStore.getState().refreshProfile()
  } else {
    useAuthStore.setState({ profile: null })
  }
})
