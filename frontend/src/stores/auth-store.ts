import { create } from 'zustand'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '@/lib/supabase'
import { identityApi } from '@/lib/api/identity'
import type { UserDto } from '@/lib/api/types'

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
supabase.auth.onAuthStateChange((_event, session) => {
  useAuthStore.setState({ session, status: session ? 'authenticated' : 'unauthenticated' })
  if (session) {
    void useAuthStore.getState().refreshProfile()
  } else {
    useAuthStore.setState({ profile: null })
  }
})
