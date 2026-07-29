const required = (key: string, value: string | undefined): string => {
  if (!value) {
    throw new Error(`Missing required env var ${key} — set it in .env.local (see .env.example)`)
  }
  return value
}

export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  supabaseUrl: required('VITE_SUPABASE_URL', import.meta.env.VITE_SUPABASE_URL),
  supabaseAnonKey: required('VITE_SUPABASE_ANON_KEY', import.meta.env.VITE_SUPABASE_ANON_KEY),
}
