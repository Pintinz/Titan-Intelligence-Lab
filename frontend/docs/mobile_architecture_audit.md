# TitanIQ Mobile Architecture Audit

Read directly from the repository this session — every claim below was verified by opening the
actual file, not assumed from convention. This is Phase 0 of the mobile conversion spec; no code
was changed to produce it.

## Environment (governs what Phases 15-18 can actually do here)

This session's environment: Windows, Node v24.18.0, npm 11.16.0. No Java, no Android SDK
(`ANDROID_HOME` unset, no `adb`), no Xcode/macOS. Concretely:

- Generating the `android/` and `ios/` Capacitor project folders: **possible** — `cap add` just
  copies template files, no SDK required for that step.
- Compiling an APK/AAB: **not possible here** — needs a JDK + Android SDK/Gradle.
- Compiling an IPA: **not possible on Windows at all** — Xcode is macOS-only, no substitute.
- Running the app on a real/simulated device, capturing device screenshots, testing native push
  delivery, testing real deep-link resolution: **not possible here** — all need a device or
  emulator/simulator this environment doesn't have.
- Submitting to Google Play / App Store: **not possible here** — needs the user's own developer
  accounts (Apple: paid, Google: paid), which this session has no credentials for regardless.

Everything below Phase 0 will be built as real, working code. Anything requiring the above will
be marked BLOCKED, not faked.

## Stack

| | Found |
|---|---|
| React | 19.2.7 |
| TypeScript | 6.0.2 |
| Vite | 8.1.1 |
| Router | react-router-dom 7.18.1 |
| State | Zustand 5.0.14 (`src/stores/auth-store.ts` — the only global store) |
| Data fetching | @tanstack/react-query 5.101.4 |
| Styling | Tailwind CSS 4.3.3 (`@tailwindcss/vite` plugin, no separate config file — v4's CSS-first config) |
| UI primitives | Radix UI (accordion, dialog, dropdown, popover, select, tabs, toast, tooltip, etc.) |
| Forms | react-hook-form 7 + zod 4 + @hookform/resolvers |
| Auth/Realtime | @supabase/supabase-js 2.110.8 |
| Charts | recharts 3.10.1 |
| Animation | framer-motion 12.42.2 |
| Package manager | npm (package-lock.json present, no yarn/pnpm lockfile) |

Build: `tsc -b && vite build`. Test: `vitest run` (unit) + `@playwright/test` (e2e, present but
not run as part of `npm run build`). Lint: `oxlint`.

## Environment variables (complete — confirmed against `.env.example`)

Exactly three, all consumed via `src/lib/env.ts`:

```
VITE_API_BASE_URL       — FastAPI backend base URL
VITE_SUPABASE_URL       — Supabase project URL
VITE_SUPABASE_ANON_KEY  — Supabase publishable/anon key (safe in a browser bundle — RLS enforces
                           access control server-side; confirmed in production_deployment.md)
```

`src/lib/env.ts` already fails loudly in a production build if `VITE_API_BASE_URL` is unset
(only falls back to `localhost:8000` when `import.meta.env.DEV` is true) — this same guard
protects a Capacitor build exactly the same way, since Capacitor bundles are still built by Vite.

**No API keys, database credentials, or provider secrets exist anywhere in the frontend** —
confirmed earlier this session by grepping the actual production `dist/` bundle output, not just
source. Gemini/sports-provider/database credentials live only in the backend's vault
(`backend/modules/admin`), never touch the frontend. Phase 14's "no secrets in mobile bundle"
requirement is already satisfied by the existing architecture; a Capacitor build changes nothing
about where secrets can leak from, since it ships the same JS bundle a browser would get.

## API client layer (`src/lib/api/`)

17 files, one per backend router, all going through a single `src/lib/api/client.ts`. This is
already the correct shape for Capacitor — nothing here talks to the network directly except this
one file, so pointing a native build at production is a single env var
(`VITE_API_BASE_URL=https://titan-intelligence-lab.onrender.com`), not a code change.

`client.ts` attaches the Supabase session's bearer token to every request (verified in an earlier
session's work on `frontend/src/lib/api/client.test.ts`). No separate mobile auth path needed.

## Authentication (`src/stores/auth-store.ts`, `src/lib/supabase.ts`)

Supabase JS's own `onAuthStateChange` listener is the single source of truth for session state —
confirmed no other code path calls `getSession()` for UI state. Google OAuth already wired
(`frontend/src/components/auth/auth-flow.tsx`, `google-signin-button.tsx`,
`frontend/src/pages/auth-callback-page.tsx` — all from earlier this session's work).

**Storage is the one real gap for native.** `src/lib/supabase.ts` defines a custom
`rememberAwareStorage` object that already abstracts session persistence behind `getItem`/
`setItem`/`removeItem` — currently backed by `window.localStorage`/`window.sessionStorage`. This
is exactly the extension point Phase 9 needs: swap the underlying storage for
`@capacitor/preferences` (or `@capacitor/secure-storage-plugin` for stronger guarantees) when
`Capacitor.isNativePlatform()` is true, keep the existing web behavior otherwise. This is a
~15-line change to one file, not a rewrite — the interface Supabase expects already matches what
exists.

Google OAuth's `redirectTo` (currently a same-origin web URL, `auth-callback-page.tsx`) needs a
second, native-specific value for Capacitor: either a custom URL scheme deep link
(`titaniq://auth/callback`) handled by `@capacitor/app`'s `appUrlOpen` listener, or Supabase's
own recommended pattern for mobile OAuth (opening the browser via `@capacitor/browser` and
capturing the redirect). Needs a real decision — see Phase 9 open questions below.

## Routing (`src/router.tsx`, 346 lines, 96 routes)

All routes are lazy-loaded (`lazyPage()`/`lazyPageWithProps()` helpers, confirmed from this
session's earlier bundle-size work) except `NotFoundPage`/`ServerErrorPage` and the new
`AuthCallbackPage`. This already benefits a Capacitor build the same way it benefits web — smaller
initial JS payload matters more, not less, on mobile networks (Phase 13's ask is already halfway
satisfied by existing work).

Route tree, by shell:
- **Marketing** (`marketing-shell.tsx`): landing, pricing, about, FAQ, trust center — desktop-first
  content pages, lowest mobile priority.
- **App** (`app-shell.tsx` + `sport-shell.tsx`): the actual product — `/app`, `/app/:sport/*`
  (matches, teams, players, competitions, prediction lab), `/app/watchlist`, `/app/ai-picks`,
  `/app/alerts`, `/app/insights` (Knowledge Graph), `/app/settings`. This is the surface Phases 4-7
  target.
- **Ops** (`ops-shell.tsx`): admin-only (Executive Dashboard, Provider Management, Feature Flags) —
  gated by `RoleRoute`, out of scope for a consumer mobile app per the spec's own "Profile" (not
  "Admin") primary destination; kept reachable for admins via the existing web-responsive nav, not
  worth a bottom-tab slot.

## Existing navigation — real finding, changes Phase 3's scope

**A mobile nav already exists, but it's the wrong pattern for what the spec asks for.**
`src/components/layout/mobile-nav.tsx` is a slide-out drawer (Radix Dialog, full-height, opens via
a hamburger button below the `lg` breakpoint) listing every `NAV_GROUPS` entry from
`nav-config.ts`, filtered by role by `isAtLeast()`. This is a **responsive web pattern** —
"hide the desktop sidebar behind a hamburger on small screens" — not a **native app pattern**
("5 fixed bottom tabs always visible"). The spec's Phase 3 (bottom tab bar: Home/Matches/
Intelligence/Predictions/Profile) is genuinely new work, not a duplicate of this — but the
underlying data it needs (`NAV_GROUPS`, `isAtLeast`, role-gating) already exists and should be
read from the same `nav-config.ts`, not redefined.

`SportSegmentedControl` (`command-deck/primitives/sport-segmented-control.tsx`) already reads
`useAvailableSports()` (the football-only-for-non-admins gate from this session's earlier work) —
any new mobile nav must call the same hook, not a second sport list, or a regular user would see
sports on mobile the web app already hides from them.

## Offline/network handling — partially exists

`src/lib/hooks/use-online-status.ts` already exists: a clean `navigator.onLine` +
`online`/`offline` event listener hook, directly reusable as-is. `navigator.onLine` works
identically inside a Capacitor WebView (it's a standard Web API, not something Capacitor
sandboxes), so **no native plugin is needed for basic connectivity detection** — Phase 11 can
build on this hook directly rather than introducing `@capacitor/network` as a hard requirement
(that plugin adds connection-type detail `navigator.onLine` doesn't, but isn't required for the
spec's actual ask: don't show stale data as live, show a "may be outdated" indicator).

No existing "stale data" / "last synchronized" UI component was found — this is real, new Phase 11
work, not a duplicate.

## Browser APIs in use that need native awareness (grepped `src/`, not guessed)

`localStorage`/`sessionStorage` direct usage found in 11 files beyond `supabase.ts`:
`team-detail-page.tsx`, `settings-page.tsx`, `press-kit-page.tsx`, `ops/data-pipeline-page.tsx`,
`insights/insights-page.tsx`, `use-online-status.ts` (via `navigator.onLine`, not storage),
`use-investigation-workspace.ts`, `infinity-sidebar.tsx`, `investigation-notebook.tsx`,
`investigation-context-rail.tsx`. All of these work unmodified inside a Capacitor WebView —
`localStorage` is fully available there, just not hardware-backed-secure the way Keychain/Keystore
is. Only the Supabase session token (already isolated behind one storage adapter, see above)
carries enough sensitivity to justify moving off it; the rest (UI preferences, workspace notes,
sidebar pin state) are fine to leave as-is.

No `navigator.geolocation`, no direct `fetch()` calls outside the API client layer, no
`window.matchMedia` usage beyond what Tailwind's own responsive utilities compile to.

## PWA configuration (`vite.config.ts`, `vite-plugin-pwa`)

Already real and complete: `registerType: 'autoUpdate'`, real manifest (name, short_name,
description, theme/background color, `display: 'standalone'`, shortcuts for Prediction Center/
Match Center/Notifications), deliberately empty `runtimeCaching` (API responses are per-user and
RBAC-gated — the existing code comment explains this was a considered decision, not an oversight,
and the same reasoning applies to a Capacitor build: don't cache prediction/market data offline).

**Icons are SVG-only** (`favicon.svg`, `pwa-icon.svg`, `icons.svg` — no PNG/raster anywhere in
`public/`). This is fine for a PWA (browsers rasterize SVG manifest icons fine) but **iOS and
Android app icons must be raster PNG at fixed sizes** — Capacitor's asset pipeline
(`@capacitor/assets`) generates the full icon/splash-screen set from a single source PNG, which
doesn't exist yet. Real, new Phase 1 work: export a high-resolution PNG from the existing
`pwa-icon.svg` design (same brand mark, not a new one) before running the asset generator.

## Responsive breakpoints already in use

Tailwind 4 defaults (`sm`/`md`/`lg`/`xl`/`2xl`), `lg` (1024px) is the app's own real breakpoint for
sidebar-vs-drawer nav (confirmed in `mobile-nav.tsx`/`app-shell.tsx`). A Capacitor WebView on a
phone renders at whatever the device's CSS viewport width is (same as a mobile browser — no
different breakpoint math needed), so the existing `sm`/`md` breakpoints apply unchanged; only the
*navigation chrome* (bottom tabs vs. drawer) needs new native-specific logic, not the content
breakpoints themselves.

## Desktop-only interactions identified (real, need mobile alternatives)

- `command-deck/workspace/investigation-notebook.tsx` and `investigation-context-rail.tsx` —
  multi-panel workspace layout, uses `localStorage` for panel state; built assuming desktop screen
  width. Needs a mobile-specific single-column/bottom-sheet variant, not a rewrite of the
  underlying data hook (`use-investigation-workspace.ts`).
- `infinity-sidebar.tsx` — persistent sidebar with pinned state in `localStorage`; the drawer
  pattern already used for `mobile-nav.tsx` is the right model to extend, not a new pattern.
- Recharts-based charts (correct-score grids, confidence breakdowns) — need touch-target and
  label-density review at phone widths; not audited row-by-row here, flagged for Phase 7.

## Components identified as reusable unchanged

Every Radix-based primitive (dialog, dropdown, popover, select, tabs, toast, tooltip, accordion) —
these already handle touch and keyboard identically; Radix has no desktop-only assumptions baked
in. `PageHero`, `Section`, `ValueCard`, `PricingTierCard`, `FaqAccordion` (marketing components,
confirmed present from earlier session work) — reusable as-is for any marketing screens shown
inside the native shell (e.g., a native onboarding/paywall screen). The entire `src/lib/api/*`
layer — zero changes needed, per the API client section above.

## Summary — what Phase 1+ actually needs to build

1. Install `@capacitor/core`, `@capacitor/cli`, `@capacitor/android`, `@capacitor/ios`; scaffold
   `android/`/`ios/` folders (achievable here).
2. Generate a raster app icon from the existing brand mark; run `@capacitor/assets` (achievable).
3. `capacitor.config.ts` pointing `webDir` at `dist`, real bundle ID (achievable).
4. A genuinely new bottom-tab navigation component (Home/Matches/Intelligence/Predictions/Profile),
   reading the existing `NAV_GROUPS`/`useAvailableSports()`/`isAtLeast()` — not a second nav data
   source (achievable, real new UI work).
5. Extend `rememberAwareStorage` in `src/lib/supabase.ts` for native secure storage (achievable,
   small real change).
6. Native Google OAuth redirect handling — needs a decision on deep-link scheme vs.
   `@capacitor/browser` pattern before implementation (open question, see Phase 9).
7. Push notification client plumbing (`@capacitor/push-notifications`) — achievable to wire up;
   actually *receiving* a real push needs a real Firebase/APNs project this session has no
   credentials for, so end-to-end delivery can't be verified here.
8. Everything from here down (Phases 15, 17, 18) needs a device/emulator or Mac this environment
   doesn't have — will be built as code, not verified by an actual run, and reported as such.
