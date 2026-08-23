import { createClient } from '@supabase/supabase-js'
import { SecureStoragePlugin } from 'capacitor-secure-storage-plugin'
import { env } from '@/lib/env'
import { isNativePlatform } from '@/lib/capacitor'

const REMEMBER_ME_KEY = 'titaniq-remember-me'

/**
 * Real "remember me" (Milestone 10A) — not a cosmetic checkbox. Call before signInWithPassword.
 * `true` (default): session survives browser restarts (localStorage). `false`: session lasts
 * only for the current tab/browser session (sessionStorage) — cleared on tab close, same as
 * unchecking "remember me" on any other site's login form.
 *
 * Native builds have no equivalent "until the tab closes" concept (there's one long-lived app
 * process, not a closable tab), so both branches persist to Keychain/Keystore there — "remember
 * me: off" on native instead means "sign out clears it," handled by `removeItem` at sign-out, not
 * by choosing a shorter-lived store the way sessionStorage does on web.
 */
export function setRememberMe(remember: boolean) {
  window.localStorage.setItem(REMEMBER_ME_KEY, remember ? 'true' : 'false')
}

function rememberMe(): boolean {
  return window.localStorage.getItem(REMEMBER_ME_KEY) !== 'false'
}

// Web/PWA: unchanged from before — localStorage vs sessionStorage per the remember-me flag.
const webStorage = {
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

// Native: the session token (refresh token especially) is exactly the kind of long-lived bearer
// credential that belongs in Keychain (iOS) / Keystore (Android), not a WebView's localStorage —
// `capacitor-secure-storage-plugin` wraps both. Supabase's storage interface is synchronous
// (`getItem`/`setItem`/`removeItem` return strings, not promises) but every native secure-storage
// API is async, so `getItem` reads through an in-memory cache populated once at client
// construction (`primeNativeSessionCache` below, called before `createClient`) — Supabase only
// ever calls `getItem` synchronously during its own initial session hydration, which happens
// after that prime completes.
let nativeSessionCache: Record<string, string> = {}

async function primeNativeSessionCache(): Promise<void> {
  if (!isNativePlatform()) return
  try {
    const { value } = await SecureStoragePlugin.keys()
    const entries = await Promise.all(
      value.map(async (key) => {
        try {
          const { value: v } = await SecureStoragePlugin.get({ key })
          return [key, v] as const
        } catch {
          return null
        }
      }),
    )
    nativeSessionCache = Object.fromEntries(entries.filter((e): e is readonly [string, string] => e !== null))
  } catch {
    // First-ever launch, or the plugin genuinely has nothing stored yet — an empty cache is
    // correct here (means "no session," not an error), never a crash blocking app start.
    nativeSessionCache = {}
  }
}

const nativeStorage = {
  getItem: (key: string) => nativeSessionCache[key] ?? null,
  setItem: (key: string, value: string) => {
    nativeSessionCache[key] = value
    void SecureStoragePlugin.set({ key, value })
  },
  removeItem: (key: string) => {
    delete nativeSessionCache[key]
    void SecureStoragePlugin.remove({ key })
  },
}

const rememberAwareStorage = isNativePlatform() ? nativeStorage : webStorage

/** Must resolve before `supabase` below does anything session-dependent — call once at app
 * startup (see `main.tsx`). A no-op on web. */
export const nativeSessionReady = primeNativeSessionCache()

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
