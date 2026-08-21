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
}
