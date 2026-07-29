# TitanIQ — Frontend Architecture

Status: Live as of Milestone 10. React 19 + TypeScript + Vite, built as a strict presentation
layer over the existing backend (`backend/apps/api`) — no frontend-only data shapes invented, no
backend architecture/API/DTO/business-logic changes beyond what this milestone's own audit
required (see §7).

## 1. Stack

| Concern | Choice | Why |
|---|---|---|
| Framework | React 19 + TypeScript, Vite 8 | Fast dev server, native ESM, first-class TS |
| Routing | React Router 7 (`createBrowserRouter`, nested layout routes) | Data-router APIs, per-route code splitting via `React.lazy` |
| Server state | TanStack Query 5 | Caching, retry/backoff, realtime-triggered invalidation (§5) |
| Client state | Zustand (`src/stores/`) | Minimal boilerplate for auth/theme/toast/command-palette/active-org state |
| Styling | Tailwind CSS v4 (`@tailwindcss/vite`) + CSS variables | Design tokens as CSS custom properties (`src/styles/tokens.css`) mapped into Tailwind's `@theme`, so `bg-bg-primary` etc. repaint automatically on theme change — no React re-render needed for color |
| Accessible primitives | Radix UI (`@radix-ui/react-*`) | Unstyled, WAI-ARIA-compliant behavior for Dialog/DropdownMenu/Select/Tabs/Toast/etc.; TitanIQ supplies all visual styling |
| Forms | react-hook-form + zod (`@hookform/resolvers/zod`) | Schema-validated forms (auth, market/feature admin forms) |
| Command palette | cmdk | Cmd/Ctrl+K global search shell (`src/components/ui/command-palette.tsx`) |
| Virtualization | `@tanstack/react-virtual` | Row-virtualized tables for large lists (`src/components/domain/virtual-table.tsx`) |
| Charts | Recharts | Named in docs/ui_design_system.md; not yet wired to a real page — every current analytics endpoint returns aggregate scalars, not a time series (see §7) |
| Auth/Realtime backend | `@supabase/supabase-js` | Direct Supabase Auth (production credential store) + Supabase Realtime subscriptions on the 12 published tables |
| Icons | lucide-react | |

## 2. Directory layout

```
frontend/src/
  components/
    ui/           Foundational, backend-agnostic primitives (Button, Card, Dialog, Select, …)
    domain/        TitanIQ-specific composites (PredictionCard, MatchCard, ConfidenceMeter,
                    KnowledgeGraphViewer, VirtualTable, …) — consume typed DTOs from lib/api
    layout/        AppShell, Sidebar, Topbar, MobileNav, nav-config, PageLoader
    auth/           OAuthButtons
    search/         GlobalSearch (wires CommandPalette to real endpoints)
  pages/            One file per route, grouped by domain (predictions/, sports/, intelligence/,
                    graph/, analytics/, ml/, admin/, settings/, notifications/, help/)
  routes/            ProtectedRoute, RoleRoute — route-level auth/RBAC guards
  stores/           Zustand stores: auth, theme, toast, command-palette, active-org
  lib/
    api/             Typed client (client.ts) + one module per backend router (identity.ts,
                       tenancy.ts, billing.ts, webhooks.ts, graph.ts, intelligence.ts,
                       predictions.ts, markets.ts, admin-predictions.ts, ml-platform.ts,
                       admin-platform.ts, sports.ts) + types.ts (hand-written DTOs, see §3)
    hooks/           use-realtime-invalidate.ts
    validation/       zod schemas (auth-schemas.ts)
    realtime.ts       Supabase Realtime table registry + subscribeToTable()
    supabase.ts       Single Supabase client (Auth + Realtime)
    query-client.ts   TanStack Query client (retry policy skips 401/403/404/409/422)
    cn.ts             clsx + tailwind-merge
  styles/tokens.css   Design tokens (CSS variables, dark + light)
  router.tsx          Route tree, lazy-loaded leaf pages
  App.tsx             Providers: QueryClientProvider, TooltipProvider, Toaster
  main.tsx            Entry point
```

## 3. Typed API layer

The backend defines no Pydantic *response* models — every route returns a hand-built dict via a
local `_serialize_*` function (see the Milestone 10 backend audit). `src/lib/api/types.ts`
mirrors those dict shapes by hand, one interface per `_serialize_*`, kept in sync against the
router source rather than codegen'd. `src/lib/api/client.ts` normalizes the backend's two
response shapes — success `{data, meta, error}` vs. error `{detail}` (no shared exception handler
unifies them on the backend) — into a single `ApiError` on the failure path.

Every backend router has a matching frontend module with one function per endpoint (e.g.
`predictionsApi.generate()`, `marketsApi.approve()`), attaching the current Supabase session's
JWT as a Bearer token on every request.

## 4. Authentication

Production auth is Supabase Auth directly from the browser (`supabase.auth.signInWithPassword` /
`signInWithOAuth` / `signInWithOtp` / `resetPasswordForEmail` — see `src/pages/login-page.tsx`,
`signup-page.tsx`, `forgot-password-page.tsx`, `reset-password-page.tsx`,
`auth-callback-page.tsx`), matching docs/authentication.md's documented split: FastAPI's own
`/api/v1/auth/register`/`/login` are the offline/mock test path, not the production one.
`src/stores/auth-store.ts` subscribes to `supabase.auth.onAuthStateChange` as the single source
of truth for session state, then calls `GET /api/v1/users/me` to hydrate the platform role/
profile (this is also what triggers `IdentityService.ensure_provisioned` on the backend, creating
the `identity.users` shadow row on first authenticated call).

`ProtectedRoute` (`src/routes/protected-route.tsx`) gates the entire `/app/*` tree on
authentication; `RoleRoute` (`src/routes/role-route.tsx`) additionally gates Model/Experiment/
Feature/Admin Center routes on `Role.ADMINISTRATOR`, using the same `isAtLeast` ordinal
comparison as the backend's RBAC ladder (`src/lib/api/types.ts`).

## 5. Realtime

`src/lib/realtime.ts` enumerates all 12 Supabase-Realtime-published tables (migrations 0014 +
0019 — docs/rls.md §8 only documents 0014's 8; the frontend's registry includes all 12, see §7).
`useRealtimeInvalidate` (`src/lib/hooks/use-realtime-invalidate.ts`) subscribes a component to a
table and invalidates the given TanStack Query key(s) on any change — refetch-on-change rather
than hand-patching the cache from the raw row-diff payload, since the Realtime payload's columns
don't match the REST endpoint's computed/nested response shape (e.g. `predictions.confidence` is
flat JSON in the DB row but a structured object in the API response).

## 6. Design system implementation

See [design_system.md](design_system.md) for the token values and [ui_components.md](ui_components.md)
for the full component inventory. In brief: dark is the default/primary theme (light is a
first-class second mode, toggled via `useThemeStore`, persisted to `localStorage`, applied via a
`data-theme` attribute on `<html>` — never `prefers-color-scheme` alone, since dark stays default
even on a light-OS machine).

## 7. Known limitations (frontend-relevant backend gaps)

Discovered during the Milestone 10 backend audit and either closed or explicitly scoped around:

- **Sports read API** (competitions/teams/matches/players) didn't exist before this milestone —
  added as `apps/api/routers/sports_router.py` (12 endpoints, `get_current_user`-gated, free+),
  plus one additive repository method (`PlayerRepositoryPort.list_by_sport`).
- **News single-article lookup** didn't exist — added `GET /api/v1/intelligence/news/articles/{id}`.
- **~41 previously-unauthenticated endpoints** in `apps/api/main.py` (Provider Management,
  Feature Registration/Flags/Quality, Sync triggers, Redis/KG monitoring) are now
  `require_role(Role.ADMINISTRATOR)`-gated — user-approved security fix, see docs/security.md §8.
- **No free-text/fuzzy search exists anywhere in the Knowledge Graph module.**
  `SemanticSearchService` (Milestone 7) is named structured retrieval (`find_players_for_team`,
  `find_rivals`, etc.) over graph traversal primitives, not a text index. The Global Search
  command palette and Knowledge Graph Explorer are scoped honestly around this: navigation
  shortcuts, real news search (`/news/search?query=`), client-filtered market lists, and
  browse-by-type for the graph — no fabricated free-text KG search.
- **No "list my organizations" endpoint.** `tenancy_router.py` supports creating an organization
  and managing members/invitations once you have an org id, but nothing answers "which orgs am I
  in." Organization Settings (`src/pages/settings/organization-settings-page.tsx`) works around
  this by remembering the last-created/selected org client-side
  (`src/stores/active-org-store.ts`) — a real, honest workaround, not fabricated data.
- **No backend "notifications" entity.** Milestone 6 built audit logs and Session/Security
  Intelligence, not a generic notification feed. `src/pages/notifications/notifications-page.tsx`
  is the honest alternative: it turns the already-live Realtime table changes into a
  session-local activity feed rather than faking a notifications API.
- **`docs/rls.md` §8 undercounted the Realtime publication** (said 8 tables, citing only migration
  0014) — migration 0019 added 4 more (`predictions.predictions`, `prediction_markets`,
  `prediction_audits`, `features.feature_values_offline`), for 12 total live today. Corrected in
  this milestone; the frontend's `REALTIME_TABLES` registry matches the corrected count.

## 8. Landing Page redesign (Milestone 10.1)

The Landing Page (`src/pages/landing-page.tsx` and `src/pages/landing/*`) was rebuilt from scratch
against a new visual identity — see ADR-062/063/064 for the full rationale. Summary:

- **Scoping**: new tokens live in `src/styles/landing-tokens.css`, scoped under a `.titan-landing`
  class on the page's root element only. The rest of the app's design system (§6, ADR-060) is
  untouched — this is a deliberate boundary, not an oversight, pending a future milestone that
  reviews and promotes the new system app-wide.
- **Signature component**: `src/pages/landing/telemetry.tsx` exports `ConfidenceTelemetry`, a
  4-segment sector-timing bar (F1 broadcast-graphics lineage) that replaces plain percentage
  badges as the page's primary confidence display, plus shared section primitives
  (`SectionHeading`, `Section`, `IllustrativeTag`, `LiveDot`, `Hairline`).
- **Content**: `src/pages/landing/sample-data.ts` is illustrative-but-contract-accurate content
  (every sports/prediction/news/knowledge-graph endpoint requires an authenticated session, so a
  signed-out visitor never sees live data — unchanged from the previous milestone's honest
  posture). Every section rendering it carries a visible "Illustrative" marker. Note: this file's
  shapes are checked against the real backend `_serialize_*` functions directly, not
  `lib/api/types.ts` — `ConfidenceBreakdownDto`, `ExplanationBundleDto`, `NewsArticleDto`, and
  `CommunityTopicDto` have drifted from their router source and should be corrected in a follow-up
  pass (affects the authenticated Prediction Detail/News Center pages too, not just this one).
- **Sports shown**: Football, Basketball, Baseball, Table Tennis — the backend's real Phase One
  set (`docs/titaniq.md` §3), not the Tennis market list an earlier brief referenced (ADR-064).
- **Previous landing page**: archived at `src/pages/landing/_legacy/` for reference, not deleted.
