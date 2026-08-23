import { App as CapacitorApp, type URLOpenListenerEvent } from '@capacitor/app'
import { Browser } from '@capacitor/browser'
import type { NavigateFunction } from 'react-router-dom'
import { supabase } from '@/lib/supabase'

/** `titaniq://` — registered as a URL scheme in both `android/app/src/main/AndroidManifest.xml`
 * and `ios/App/App/Info.plist` (host `auth`, matching the redirect path below). Must also be
 * added to the Supabase project's Auth > URL Configuration > Redirect URLs allowlist
 * (dashboard-only config this build cannot perform). */
const NATIVE_SCHEME = 'titaniq://'
const NATIVE_REDIRECT_URL = `${NATIVE_SCHEME}auth/callback`

/**
 * Native Google sign-in: Google blocks OAuth consent inside an embedded WebView (Capacitor's
 * runtime), so this opens the system browser (`@capacitor/browser` — an in-app Custom Tab/
 * SFSafariViewController, not a second WebView) instead of the web flow's plain redirect.
 * `skipBrowserRedirect: true` makes Supabase return the consent URL instead of navigating the
 * (non-existent, on native) current page to it.
 */
export async function signInWithGoogleNative(returnTo: string): Promise<{ error: string | null }> {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: `${NATIVE_REDIRECT_URL}?returnTo=${encodeURIComponent(returnTo)}`,
      skipBrowserRedirect: true,
    },
  })
  if (error || !data?.url) return { error: error?.message ?? 'Could not start Google sign-in.' }
  await Browser.open({ url: data.url, presentationStyle: 'popover' })
  return { error: null }
}

/**
 * Catches the OS handing the `titaniq://` deep link back to the app after Google consent, and
 * routes its path/query/hash into the SPA's existing `/auth/callback` route — reusing
 * `AuthCallbackPage`'s already-built, already-tested session-exchange logic (via Supabase's
 * `detectSessionInUrl`, which reads `window.location` regardless of whether that location was
 * reached by a real page load or a router push) rather than a second, native-only copy of it.
 * Call once near the app root (see `App.tsx`) with the router's `navigate`.
 */
export function initNativeOAuthListener(navigate: NavigateFunction) {
  const handle = CapacitorApp.addListener('appUrlOpen', (event: URLOpenListenerEvent) => {
    if (!event.url.startsWith(NATIVE_SCHEME)) return
    void Browser.close().catch(() => {
      // Already closed, or the system browser instance is gone — nothing to recover from.
    })
    // "titaniq://auth/callback?returnTo=...#access_token=..." -> "/auth/callback?returnTo=...#access_token=..."
    navigate(`/${event.url.slice(NATIVE_SCHEME.length)}`, { replace: true })
  })
  return () => {
    void handle.then((h) => h.remove())
  }
}
