import { createClient } from '@supabase/supabase-js'
import { env } from '@/lib/env'

const REMEMBER_ME_KEY = 'titaniq-remember-me'

/**
 * Real "remember me" (Milestone 10A) — not a cosmetic checkbox. Call before signInWithPassword.
 * `true` (default): session survives browser restarts (localStorage). `false`: session lasts
 * only for the current tab/browser session (sessionStorage) — cleared on tab close, same as
 * unchecking "remember me" on any other site's login form.
 */
export function setRememberMe(remember: boolean) {
  window.localStorage.setItem(REMEMBER_ME_KEY, remember ? 'true' : 'false')
}

function rememberMe(): boolean {
  return window.localStorage.getItem(REMEMBER_ME_KEY) !== 'false'
}

// Storage adapter that picks localStorage vs sessionStorage per-call based on the remember-me
// flag recorded at the most recent sign-in — lets a single Supabase client instance honor a
// per-login "remember me" choice instead of a client-construction-time-only setting.
const rememberAwareStorage = {
  getItem: (key: string) => window.localStorage.getItem(key) ?? window.sessionStorage.getItem(key),
  setItem: (key: string, value: string) => {
    if (rememberMe()) {
      window.localStorage.setItem(key, value)
      window.sessionStorage.removeItem(key)
    } else {
      window.sessionStorage.setItem(key, value)
      window.localStorage.removeItem(key)
    }
  },
  removeItem: (key: string) => {
    window.localStorage.removeItem(key)
    window.sessionStorage.removeItem(key)
  },
}

// Single Supabase client for the whole app — Auth (JWT session, OAuth) + Realtime (Postgres
// changes on the 12 published tables, docs/rls.md §8). REST/RPC against the schemas themselves
// goes through the FastAPI backend (apps/api), not PostgREST — RLS is defense in depth there,
// not this app's primary data path.
export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
    storage: rememberAwareStorage,
  },
})
