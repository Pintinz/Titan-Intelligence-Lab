const required = (key: string, value: string | undefined): string => {
  if (!value) {
    throw new Error(`Missing required env var ${key} — set it in .env.local (see .env.example)`)
  }
  return value
}

// A production build with VITE_API_BASE_URL accidentally unset must fail loudly, not silently
// ship pointing at localhost (Production Readiness Audit §8) — the same required() guard the
// Supabase vars already use, just scoped to dev so local workflow keeps its zero-config default.
const apiBaseUrl = import.meta.env.DEV
  ? (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000')
  : required('VITE_API_BASE_URL', import.meta.env.VITE_API_BASE_URL)

export const env = {
  apiBaseUrl,
  supabaseUrl: required('VITE_SUPABASE_URL', import.meta.env.VITE_SUPABASE_URL),
  supabaseAnonKey: required('VITE_SUPABASE_ANON_KEY', import.meta.env.VITE_SUPABASE_ANON_KEY),
  // Mobile V1 monetization (AdMob rewarded predictions) — deliberately NOT `required()`. There is
  // no real AdMob account/app in this environment to issue production IDs from, and Google's own
  // policy requires test ads whenever a real ID isn't genuinely configured for release — so
  // `RewardedAdService` (lib/ads/) falls back to Google's official public test ad unit IDs when
  // these are unset, rather than crashing the build or (worse) silently shipping without ads.
  // REQUIRES EXTERNAL CONFIGURATION before a real release build: set all four in the native
  // build's environment (see docs/mobile_admob_configuration.md).
  admobAndroidAppId: import.meta.env.VITE_ADMOB_ANDROID_APP_ID as string | undefined,
  admobIosAppId: import.meta.env.VITE_ADMOB_IOS_APP_ID as string | undefined,
  admobAndroidRewardedAdUnitId: import.meta.env.VITE_ADMOB_ANDROID_REWARDED_AD_UNIT_ID as string | undefined,
  admobIosRewardedAdUnitId: import.meta.env.VITE_ADMOB_IOS_REWARDED_AD_UNIT_ID as string | undefined,
}
