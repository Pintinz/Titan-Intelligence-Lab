# Milestone 11 — Live Multi-Sport Intelligence Integration Report

**Date**: July 30, 2026
**Scope**: Connect the Milestone 10.3 frontend to the live FastAPI backend; verify every integration; no backend contract changes; no page redesigns.

## Executive summary

The premise of this milestone — that the frontend was still running on mock/illustrative data and needed wiring to a backend — was **only partially true**. A full audit (a dedicated read-only pass across every authenticated page, plus getting the actual backend running locally and hitting it with real HTTP requests) found:

- **Already fully live before this milestone**: all 4 Sport Intelligence Centers (12 pages), News Intelligence, Community Intelligence, TitanIQ Insights, Knowledge Graph exploration, and 3 of 8 Operations Center modules. These call real `useQuery`/`useMutation` hooks against real API client methods — no hardcoded arrays.
- **Genuinely missing and built in this milestone**: the Dashboard (`/app` index) didn't exist as a page at all — just a placeholder. Realtime infrastructure existed in `lib/realtime.ts` but was wired into zero pages. 5 of 8 Operations Center tabs were visually indistinguishable from the 3 truly-live ones despite routing to placeholders.
- **Genuinely blocked, not a code problem**: no sports reference data (teams/fixtures/competitions) exists in the local dev database, because that only arrives via provider ingestion, which requires provider API keys that are not present in this environment. This is expected, correctly handled (real empty states, not fake data), and outside what a frontend integration pass can fix.

Everything below is backed by an actual running local backend (SQLite dev database, real FastAPI process on `127.0.0.1:8000`) and real HTTP requests — not inferred from reading code.

---

## 1. What was already connected (verified by prior audit + this session)

| Area | Pages | Backend calls |
|---|---|---|
| Football/Basketball/Baseball/Table Tennis hubs, match list/detail, teams, players, competitions, prediction lab, news, community | 12 files under `src/pages/sports/` | `sportsApi`, `marketsApi`, `predictionsApi`, `intelligenceApi` |
| News Intelligence | `src/pages/intelligence/news-intelligence-page.tsx` | `intelligenceApi.searchNews`, `.impact`, `.newsTimeline` — real `<a href={article.url}>` attribution, no full-text reproduction |
| Learning Intelligence | `src/pages/intelligence/learning-intelligence-page.tsx` | `predictionsApi.monitoringSummary` (the 6-step pipeline diagram is explanatory copy, not data — correctly static) |
| TitanIQ Insights | `src/pages/insights/insights-page.tsx` | `sportsApi`, `marketsApi`, `predictionsApi.history/.compare`, `intelligenceApi.communityTopics` |
| Knowledge Graph | `src/pages/knowledge-graph-page.tsx` | `adminPlatformApi.kgNode` |
| Operations Center (partial) | Executive Dashboard, Provider Management, Feature Flags | `adminPlatformApi`, `adminPredictionsApi` — full CRUD on flags/providers |

No changes were made to any of the above — they were correct going in.

---

## 2. What this milestone built

### 2.1 Live Dashboard (`/app` index) — new
`src/pages/dashboard-page.tsx`. Previously a `RebuildingPage` placeholder; the most visible gap in the whole app (the first screen after login). Built using **only already-proven, already-used API client methods** — no new endpoints, no new client code:

- `sportsApi.listFixtures` × 4 sports (via `useQueries`) → live/today match tiles, per-sport, with real `FixtureCard`
- `predictionsApi.monitoringSummary()` → prediction tracking stat + full breakdown via `KeyValueGrid`
- `graphApi.statistics()` → Knowledge Graph node count (this client existed, fully typed, and was **entirely unused** anywhere in the app until now)
- `intelligenceApi.analytics()` → news/community processing stats
- Quick-links to News, Learning, Insights, Knowledge Graph

All four data sources are **not** admin-gated, so this works for every signed-in user, not just administrators — verified directly against the running backend with a free-tier test token (see §5).

### 2.2 Realtime wiring — new
`lib/realtime.ts` + `lib/hooks/use-realtime-invalidate.ts` existed, fully built and unit-tested, subscribing to 12 real Supabase Realtime-published tables — but were called from **zero** pages before this milestone. Wired into the two highest-value cases:

- **`match-detail-page.tsx`**: subscribes to the `sports.matches` table filtered to the open fixture's id; any row change invalidates that fixture's query, so score/status updates push in with no manual refresh. Added a small "● updating live" indicator when the fixture is in progress.
- **`dashboard-page.tsx`**: subscribes to `sports.matches` unfiltered, invalidating all 4 sports' dashboard fixture queries — live scores across every sport update the Dashboard without a reload.

Not wired (explicitly scoped out, see §7): predictions/confidence realtime, Knowledge Graph update events, news/community realtime, notifications. These either have no existing GET-by-entity query to attach an invalidation to (would require new frontend query wiring beyond "connect existing"), or weren't the highest-value 1–2 cases the task called for.

### 2.3 Operations Center honesty fix
`components/layout/ops-shell.tsx`. The `LIVE_MODULES` tab bar listed 8 modules as equally "live" — Executive Dashboard, Provider Management, Feature Flags (genuinely live) alongside Data Pipeline, Feature Store, Prediction Engine, ML Operations, Knowledge Graph (all 5 route to `RebuildingPage`). A user had no visual signal before clicking that 5 of 8 tabs were placeholders.

Fixed by splitting into three honestly-labeled tiers: **Live** (3), **Backend ready — frontend pending** (5, with a distinct warning-colored badge and its own aria-label), **Planned** (7, unchanged — no backend module exists yet for these). The "backend ready" label is not a guess — I confirmed all 5 corresponding endpoint families exist in the live OpenAPI schema (`/api/v1/admin/sync/*`, `/api/v1/admin/features/*`, `/api/v1/admin/predictions/*` + `/api/v1/markets`, `/api/v1/admin/ml/*`, `/api/v1/admin/graph/*`).

---

## 3. Getting the backend actually running (for real verification, not inference)

The repo ships a complete FastAPI backend at `backend/` with a matching module for every frontend API client (sports, predictions, intelligence, graph, admin, billing, tenancy, webhooks, identity). It was not running. To verify anything for real rather than reading code and hoping, I:

1. Found `backend/.env` has `TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db` (local file, zero shared-state risk) and `TITANIQ_REDIS_URL=redis://localhost:6379/0` — confirmed both are local before touching anything.
2. Found and fixed a real local-dev friction point: `DatabaseSettings` (pydantic-settings, prefix `TITANIQ_DB_`) reads from process environment, not from `.env` automatically — `.env` has to be sourced into the shell before `uvicorn` starts, or every DB-touching route 500s with a Pydantic "field required" error. Not a bug in the backend (the fail-fast-on-missing-config is intentional, documented in code comments), just an easy step to miss. Started uvicorn correctly with the env sourced: `apps.api.main:app` on `127.0.0.1:8000`, using the existing `.venv`.
3. Confirmed `dev.db` already exists (prior migrations applied) with 86 tables; `sports`/`teams`/`fixtures`/`competitions`/`players` are all empty (0 rows) — no provider ingestion has ever run against this database. `prediction_markets` has 1 seeded row (`scripts/seed_local_market.py`, pre-existing).
4. Used the backend's own documented **offline auth path** (`/api/v1/auth/register` + `/api/v1/auth/login`, explicitly built "to let a client authenticate... without a live Supabase project" per its own docstring) to get a real bearer token for a free-tier test user, entirely local, no real Supabase account touched.

---

## 4. Provider status

**No external sports/news/odds provider API keys are configured** anywhere in this environment — `backend/.env` contains only infrastructure credentials (DB, Redis, encryption key, Supabase project URL, CORS). None of API-Football, API-Basketball, API-Baseball, the table tennis provider, news providers, Gemini, or odds providers have keys set.

This is the direct cause of every sports page currently rendering an empty state instead of real fixtures — **the plumbing is correct and verified** (endpoints return proper `200` with `[]`, not errors; the frontend correctly shows `EmptyState` components, not broken UI or fake data), but there is no real match data to display anywhere in the app until real provider credentials are supplied.

**This is not something I can or should fix from the frontend.** Per the brief's own instructions: never hardcode credentials, never fabricate provider connectivity. Supplying real API keys is a business/procurement decision, not an engineering one. Operations Center's Provider Management page (already live) is exactly where these would be configured once obtained — it correctly shows an empty provider list right now, which is the honest state.

**Recommendation for whoever owns provider procurement**: once keys exist, the ingestion pipeline (`backend/modules/ingestion/`, triggered via `adminPlatformApi.triggerSyncCountries/Teams/Fixtures/Standings` — already wired into no frontend page yet, since Provider Management's UI doesn't currently expose a "trigger sync" action) needs a first run per sport/competition to populate `sports`/`teams`/`competitions`/`fixtures`. That's a Milestone 12-scale task, not something to rush here.

---

## 5. Integration test results (against the real local backend)

Direct HTTP verification, not simulated:

| Test | Result |
|---|---|
| `GET /api/v1/health` | `200`, `{"status":"ok"}` |
| `POST /api/v1/auth/register` + `/login` (offline path) | `200`, real access token issued |
| `GET /api/v1/sports/football/teams` (unauthenticated) | `401 Missing or malformed Authorization header` — correct |
| `GET /api/v1/sports/football/teams` (authenticated, free role) | `404 sport 'football' not found` — correct given `sports` table is empty; not a crash |
| `GET /api/v1/markets` (authenticated) | `200`, 1 real row |
| `GET /api/v1/predictions?market_id=...` (authenticated) | `200`, 1 real prediction with full confidence/explanation payload |
| `GET /api/v1/predictions/monitoring/summary` (authenticated, free role) | `200`, real aggregate — used by the new Dashboard |
| `GET /api/v1/graph/statistics` (authenticated, free role) | `200`, real (zeroed) aggregate — used by the new Dashboard |
| `GET /api/v1/intelligence/analytics` (authenticated, free role) | `200`, real (zeroed) aggregate — used by the new Dashboard |
| `GET /api/v1/admin/providers` (authenticated, free role) | `403 Requires role >= administrator` — RBAC correctly enforced |
| `GET /app` while logged out (browser) | Redirects to `/login` — `ProtectedRoute` confirmed working |
| `tsc --noEmit` (full project, after every change in this milestone) | Clean |
| `npm run build` | Succeeds; new Dashboard/realtime/ops-shell code adds no bundle-size regression beyond its own small chunk |
| Impeccable design detector on all touched files | Zero findings |

### What I could not verify in-browser, and why

Full click-through (real signup → real login → see the live Dashboard render) was attempted but blocked by two independent, legitimate constraints, not code defects:

1. This project's hosted Supabase instance has **mandatory email verification** enabled (documented, intentional security setting) — a signup can never reach a usable session without access to a real inbox, which a sandboxed dev environment doesn't have.
2. Supabase's signup-email rate limit was hit during testing (`429 email rate limit exceeded`) after a small number of attempts, which also blocks creating a fresh account for roughly the standard cooldown window.

I verified the same functional surface a different, equally valid way instead: every backend endpoint the Dashboard and realtime code call was hit directly with a real bearer token and returned exactly the shape the frontend code expects (§5 table above); `ProtectedRoute`'s redirect behavior was confirmed live; and the Dashboard/match-detail code was read back end-to-end against those confirmed response shapes. I'm not claiming a browser screenshot of a logged-in Dashboard that I don't have — **recommend a quick manual click-through once the Supabase rate-limit cooldown passes**, which should take under two minutes and is the one piece of this milestone I couldn't close out myself.

---

## 6. Security verification

- No provider keys anywhere in frontend code or bundle (confirmed — none exist in this environment at all, so there was nothing to leak; the frontend has zero references to any provider name/key).
- No direct provider calls from the frontend — every data path goes through the FastAPI backend.
- RBAC preserved and actively verified: a free-tier token correctly gets `403` on every `/api/v1/admin/*` route tested; the new Dashboard deliberately uses only non-admin-gated aggregate endpoints so it works for every user tier without needing a role check of its own.
- No backend contract changes — zero files under `backend/` were modified. Every new frontend call uses an existing, already-shipped API client method against an existing, already-shipped endpoint.
- `client.ts`'s error handling (`ApiError`, parsed `detail` message, no raw stack/traceback surfaced) was reused as-is by all new code — no raw backend errors reach the UI.

---

## 7. Additive backend endpoints recommended (not implemented — genuinely additive, no contract changes)

These are gaps I found but did **not** build around, because doing so honestly would require new backend surface, which is explicitly out of scope for this milestone:

1. **`PATCH /api/v1/users/me`** — Settings page's theme and notification-preference toggles are local `useState` only, with no persistence anywhere; there's no endpoint to save them to. Currently honest (no fake "saved" toast), but non-functional. Needs a small additive endpoint.
2. **A sport-scoped news filter** — `sport-news-page.tsx` and `sport-community-page.tsx` both work around the lack of one today (free-text search / client-side filtering by team name) with a code comment already documenting the gap. A `sport_code` query param on `intelligenceApi.searchNews`/`communityTopics` would remove both workarounds.
3. **A "trigger ingestion sync" action surfaced in Provider Management's UI** — the backend already has `triggerSyncCountries/Teams/Fixtures/Standings` admin endpoints and the frontend client already has the methods; no page calls them. Once provider keys exist, an admin needs a button somewhere to kick off the first sync rather than needing direct API access.
4. **Predictions-by-fixture / KG-update realtime hooks** — the `predictions` and `feature_values_offline` tables are already on the Realtime publication (`lib/realtime.ts`), but there's no existing "list predictions for this fixture" query to attach an invalidation to on `match-detail-page.tsx` (only a user-triggered generate mutation exists). Worth adding once a real GET-predictions-for-fixture pattern exists.

None of these were implemented here — flagging per the brief's explicit request, not building unrequested backend surface.

---

## 8. Performance observations

- No `refetchInterval` polling exists anywhere in the app (confirmed by the earlier audit) — every live-feeling update from here on is realtime-push (Supabase channel → `invalidateQueries`), not a timer. That's the right default; it avoids the "polling everything" trap the brief's Performance section warns against.
- The Dashboard's 4 parallel `sportsApi.listFixtures` calls (via `useQueries`) plus 3 aggregate calls run concurrently, not waterfalled — first render is bounded by the slowest single call, not the sum.
- New page (`dashboard-page.tsx`) is not manually lazy-split in `router.tsx` — it's the `/app` index, loaded on essentially every authenticated session anyway, so eager-loading it is correct; splitting it would just move the same bytes to a guaranteed-imminent second request.
- Production build after every change in this milestone: clean, no new warnings beyond the two pre-existing benign ones already known from Milestone 10.3 (main chunk size, and `not-found-page`/`server-error-page` being both statically and dynamically imported by design).

---

## 9. Outstanding items for Milestone 12

1. **Provider API keys** — the single blocker on nearly everything else in this report. Until real credentials exist for at least one sport's data provider, every Sport Intelligence Center will correctly show empty states rather than real matches, because there is no real match data to show.
2. **A one-time ingestion run** per sport/competition once keys exist, to populate `sports`/`teams`/`competitions`/`fixtures` — currently zero rows across all of them.
3. **Manual Dashboard click-through** once the Supabase signup rate-limit cooldown passes (§5) — the one verification step this session couldn't close.
4. **The 4 additive backend endpoints in §7**, prioritized: settings persistence first (currently silently non-functional UI), then the sport-scoped news/community filter (removes two documented workarounds), then a sync-trigger UI action, then predictions/KG realtime.
5. **The 5 "backend ready" Operations Center pages** (Data Pipeline, Feature Store, Prediction Engine, ML Operations, Knowledge Graph monitoring) — real frontend build-out, now honestly labeled rather than silently missing. Each is its own multi-page effort against already-existing, already-confirmed-live admin endpoints; not attempted here to avoid shipping 5 shallow, unverified pages under time pressure.
6. Consider whether `graphApi` (now used once, by the Dashboard) should also replace `adminPlatformApi.kgNode` on the standalone Knowledge Graph page for consistency, or whether the admin-gated node-lookup path there is intentional.

---

## Files changed this milestone

**Created**: `frontend/src/pages/dashboard-page.tsx`
**Modified**: `frontend/src/router.tsx` (Dashboard wired to `/app` index), `frontend/src/pages/sports/match-detail-page.tsx` (realtime), `frontend/src/components/layout/ops-shell.tsx` (honest three-tier labeling)
**Backend**: no files modified. Backend was run locally for verification only.
