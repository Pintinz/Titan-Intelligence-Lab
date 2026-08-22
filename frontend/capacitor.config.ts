import type { CapacitorConfig } from '@capacitor/cli'

// No existing bundle/application identifier was found anywhere in the repo (checked before
// choosing this) — com.titaniq.sports is a fresh identifier, per the spec's own suggested
// default. Changing it after a real store submission exists is effectively impossible (both
// stores treat the identifier as permanent), so this must be confirmed correct before any real
// release build — not just before the first `cap add`.
const config: CapacitorConfig = {
  appId: 'com.titaniq.sports',
  appName: 'TitanIQ',
  webDir: 'dist',
  server: {
    // Only used by `cap run` for live-reload against a dev server during local development —
    // production builds ship the built `dist/` output directly (server.url is unset in that
    // path), so this never points a shipped app at localhost. See docs/mobile_architecture_audit.md
    // for why VITE_API_BASE_URL (a separate, already-existing env var) is the real production
    // API target, unaffected by this block.
    androidScheme: 'https',
  },
}

export default config
