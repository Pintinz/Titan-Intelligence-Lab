# TitanIQ — User Flows

Status: Live as of Milestone 10. Golden paths through the frontend, verified in-browser against
the live Supabase project (signup/login flows) and via the backend's own test suite (data flows —
see the M10 STOP-GATE for what was and wasn't exercised together live).

## 1. Sign-up → first dashboard view

1. Landing page (`/`) → "Sign in" → Login page (`/login`) → "Sign up" → Signup page (`/signup`).
2. Email/password (or Google/GitHub OAuth) via Supabase Auth directly from the browser.
3. Email/password signups require email confirmation (Supabase default) — the page shows
   "Check your email" rather than logging the user in immediately.
4. On first authenticated API call, `IdentityService.ensure_provisioned` creates the
   `identity.users` shadow row (role defaults to `Role.FREE`).
5. `ProtectedRoute` admits the user into `/app`; `Topbar`'s user menu and `Sidebar`'s nav both
   reflect the resolved role immediately (RBAC-filtered nav — Model/Experiment/Feature/Admin
   Center stay hidden below `administrator`).

## 2. Forgot password → reset

`/forgot-password` → `resetPasswordForEmail` → emailed link → `/reset-password` (Supabase's
`detectSessionInUrl` exchanges the recovery token before the page even mounts) → `updateUser`
with the new password → redirected to `/app`.

## 3. Exploring a prediction

Prediction Center (`/app/predictions`) → pick a production market from the dropdown → grid of
`PredictionCard`s, each expandable to the full confidence breakdown (10 factors) and explanation
(SHAP-or-heuristic top features, KG/news/community contribution text) → click through to
`/app/predictions/:id` for the single-prediction detail + subject history timeline.

## 4. Browsing sports data

Match/Competition/Team/Player Centers all follow the same shape: a `SportTabs` switcher
(Football/Basketball/Baseball/Table Tennis) → a grid of summary cards → click through to a detail
page (fixture info, competition standings/fixtures tabs, team roster + recent fixtures, player
profile).

## 5. Global search (Cmd/Ctrl+K)

Opens a command palette offering, in order: navigation shortcuts (always available, filtered by
role), market name/key matches (client-filtered from one cached market list fetch), and live news
search results (`intelligence_router`'s `query` param) once 2+ characters are typed. Does **not**
offer knowledge-graph or sports-entity text search — see docs/frontend_architecture.md §7 for why.

## 6. Admin: promoting a champion model

Requires `administrator`+ (`RoleRoute`). Model Center (`/app/models`) → select a market → Model
Center lists every model version registered for it (draft/candidate/champion/challenger/retired/
rejected, algorithm, framework, deployment mode). The actual build-dataset → validate → approve →
select-champion → promote-champion workflow is exposed via `mlPlatformApi` but the multi-step
wizard UI for it is not yet built (see STOP-GATE — the read/list side of Model/Experiment/Feature
Center is complete; the admin *action* forms for that workflow are a follow-up).

## 7. Live activity

Notifications (`/app/notifications`) subscribes to four Realtime-published tables (predictions,
prediction_audits, sync_runs, provider_incidents) and renders every change as a timeline entry for
the current browser session — there is no persisted/cross-session notification history (no
backend entity for one exists yet, see Known Limitations).
