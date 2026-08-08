# Mission Control — Command Deck Redesign (Shaped Brief)

## 1. Job and audience

`/app` (home-page.tsx) is the first screen every authenticated user sees after login — currently
on the Infinity visual world, a "dashboard preview" IA (Live/Today/Trending/AI Picks/Breaking
News/Continue Watching/small Assistant teaser). Visitors arrive mid-session, most days, wanting a
five-second read on: what deserves attention right now, which matches are ready for real AI
intelligence, what changed since their last visit, and where TitanIQ wants them to go next.
Mode: **Operate** (task completion, not persuasion — the visitor is already a logged-in user).

## 2. Outcome and proof

Primary action: identify one thing worth a click (a live match, an AI-ready fixture, a strong
pick, a followed team's update) and act on it — Generate Intelligence, View Match, Follow, or open
a deeper page. Every number, card, and status on the page traces to a real, already-existing
backend endpoint; nothing is fabricated, and an honest empty/degraded state always beats an
invented one. This mirrors every Command Deck surface already shipped (Match Discovery Center, AI
Picks) — same discipline, now applied to the page users see first and most often.

## 3. Selected direction

**Visual authority**: Command Deck (`tokens.command-deck.css`, `.command-deck` wrapper) — the
established second world, already proven across Match Intelligence, Match Discovery, and AI
Picks. This page **migrates off Infinity onto Command Deck entirely** (full replacement, not a
hybrid) — graphite ground, indigo accent reserved for live/active state, tabular numerals for
telemetry, card-bounded panels, dot+label live status. No new visual-world decisions to make; this
is composition/IA work inside an already-settled world.

**Structural thesis**: ten sequential sections, each a bounded instrument panel, capped at 6 cards
where the brief specifies a card grid — Mission Hero → AI Operations Overview → Live Intelligence
→ AI Ready Fixtures → Today's Top AI Intelligence → Intelligence Feed → Competitions Under Watch →
Recently Completed Intelligence → Following → TitanIQ Workspace.

**Implementation consequence — reuse over rebuild**: several sections already exist as proven
Command Deck components elsewhere in the app and get reused/generalized here rather than rebuilt:
- **Today's Top AI Intelligence** = the exact `AiPickCard` + fixture-dedup logic just shipped for
  `/app/picks` (one card per fixture, highest-confidence market only, 5-tier badge, real
  `ai_explanation`). Fetch a wider pool, dedupe, cap at 6, sort by confidence descending.
- **Recently Completed Intelligence** = `recently-completed-intelligence.tsx`, currently
  single-sport-scoped on the Match Discovery page — generalized here to loop across all four
  sports the way this page's existing Live/Today sections already do (`useQueries` over
  `SPORT_SLUGS`), capped at 6 combined.
- **Live Intelligence / AI Ready Fixtures** = this page's own existing cross-sport Live/Today
  fetch pattern (`liveQueries`/`todayQueries` over `SPORT_SLUGS`), restyled onto
  `DiscoveryMatchCard`'s cinematic card language instead of `InfinityMatchCard`.
- **Following** = `useWatchlist()` already returns all entity types (`WatchlistEntityType = 'team'
  | 'competition' | 'fixture' | 'prediction'`) — today's page only ever displays fixture follows;
  this section surfaces team and competition follows too, which is genuinely new composition, not
  new backend.

**Net-new composition** (no existing component, real data, frontend-only):
- **Competitions Under Watch**: no cross-sport "competitions with live/upcoming counts" view
  exists yet (the current `/app/competitions` is a single-sport-at-a-time switcher). Build a
  horizontal card row aggregating `sportsApi.listCompetitions` per sport against the already-
  fetched cross-sport Live/Today queries for real per-competition live/upcoming counts — same
  "derive from an already-fetched query, no N+1" discipline as `CompetitionExplorer`.
- **Intelligence Feed**: no single endpoint merges breaking/trending/news. Compose client-side
  from three real, already-proven endpoints, each feed item honestly tagged by its real source
  type rather than forced into one fake homogeneous shape: `intelligenceApi.searchNews()` (real
  articles — headline, competition via affected entity if resolvable, published time, external
  link), `intelligenceApi.communityTopics()` (topic_label + momentum = the "trending" signal),
  `intelligenceApi.impact()` (impact_score = the "importance" signal, affected_teams/
  affected_competitions = "related"). Interleave by recency, cap at 6.
- **System status** (Hero panel + Overview's "System Health" tile): no admin-only Ops Center
  telemetry (AI Models Online / Prediction Engine Healthy) is exposed to a non-admin user, and
  building that exposure is out of scope (never modify backend). Per your direction, derive an
  honest lightweight status instead: "Prediction Engine" reads Healthy when the AI Picks/
  monitoring-summary query just returned real published data (Degraded/checking otherwise), "Live
  Monitoring" reads Connected when the live-fixtures query succeeded (regardless of whether any
  match is live right now — connectivity ≠ live count), "Last Data Sync" shows the most recent
  `generated_at`/`published_at` timestamp already present across this page's own fetched data
  (freshest of: latest pick, latest news article, latest fixture update) — no new endpoint, every
  value traceable to a query already on the page.
- **TitanIQ Workspace teaser**: per your direction, suggested-action chips are fully dynamic, not
  hardcoded example copy — built from real data fetched on this page: "Predict {today's earliest
  AI-ready fixture}" (links to that real Match Intelligence page), "Today's strongest AI picks"
  (links to `/app/picks`), "Compare {two real followed teams, or the two teams in today's highest-
  confidence pick if nothing is followed}" (links to Insights with both pre-pinned), "Open
  Knowledge Graph" (→ `/app/graph`), "Review Prediction Evidence" (→ Insights, general). Requires
  one small, frontend-only addition to `insights-page.tsx`: a second URL-param pattern
  (`?pin_type=team&pin_id=...&pin_id_2=...`, or two repeated `pin_id` params) so a "Compare" chip
  can genuinely pre-pin two real teams — mirrors the existing single-fixture cross-link exactly,
  no backend change.

## 4. Scope and boundaries

**Fidelity/breadth**: full production-ready rewrite of `home-page.tsx`, one implementation pass
(per your direction), all ten sections, desktop + tablet + mobile.

**Named target**: `frontend/src/pages/home-page.tsx` (full rewrite, wrapped in `.command-deck`),
plus new components under `frontend/src/components/command-deck/mission-control/` for sections
without an existing reusable component (Competitions Under Watch, Intelligence Feed, cinematic
fixture-card variants if `DiscoveryMatchCard` needs a home-page-specific density), and the small
`insights-page.tsx` URL-param addition described above.

**Reused, not rebuilt**: `AiPickCard` + dedup logic, `RecentlyCompletedIntelligence` (generalized
to loop sports), `DiscoveryMatchCard`, `useWatchlist`, this page's existing `SPORT_SLUGS`
multi-query fetch pattern.

**Untouched**: every backend DTO, route, the Prediction Engine, the database, React Query cache
keys/contracts for existing queries. `/app/live`, `/app/competitions` (single-sport switcher),
`/app/picks`, `/app/watchlist`, Insights page's core turn-based interaction model — all keep
working exactly as they do today; Mission Control only previews and deep-links into them.

**Anti-goals** (named per the brief, not silently dropped): Knowledge Graph node counts,
"Predictions tracked" raw record counts, and any other internal/engineering metric that doesn't
help a user decide what to do next — removed from the Hero/Overview entirely. "Matches Today" and
"Predictions Tracked" tiles, the old "Continue Watching" name, "Trending Competitions" (legacy
today's-fixture-count version), the one-card-per-market legacy AI Picks shape, and the small
Assistant teaser panel are all replaced per the brief's REMOVE COMPLETELY list — not kept
alongside the new versions.

## 5. States and ranges

- **Live Intelligence**: 0 live fixtures is the common case (verified honest empty state already
  exists — "TitanIQ is monitoring every supported competition..." copy, never "No live matches").
  Up to 6 cards when live fixtures exist, cross-sport, sorted soonest/most-recently-started first.
- **AI Ready Fixtures**: today's non-live fixtures; falls back to soonest upcoming when nothing's
  scheduled today (existing fallback pattern in current home-page.tsx, preserved).
- **Today's Top AI Intelligence**: 0–6 cards; genuinely empty (not "no picks yet" apologetically)
  when no fixture's best market clears the AI Picks confidence floor — matches `/app/picks`'s
  current honest behavior exactly, same floor constant reused.
- **Intelligence Feed**: degrades per source — if news search returns nothing but community topics
  exist, show only the real topics; never pad with placeholder rows.
- **Competitions Under Watch**: a competition with 0 live and 0 upcoming fixtures this window still
  shows (real coverage, just quiet right now) — only fully absent when a sport has zero
  competitions synced at all, which gets the brief's specified premium placeholder, never "No
  competitions active."
- **Following**: 0 follows across all three entity types is the expected state for a new user —
  brief's exact empty-state copy applies.
- **Recently Completed Intelligence**: only fixtures with at least one resolved `PredictionOutcome`
  qualify (existing rule); most freshly-completed fixtures won't qualify yet — honest, not a bug.

## 6. Interaction and layout

- Section order fixed per the brief's sequence; each non-empty section shows a "View all →" link
  to its full dedicated page (mirroring the current page's pattern), max 6 cards per grid.
- Hero: full-width, quick search (reuses the existing global Command Palette's search capability
  rather than building a second search implementation) + quick-action links + the derived system
  status strip.
- Card hover elevation, skeleton loading per section (not a single page-level spinner), smooth
  section-level fade-in — consistent with Command Deck's established motion vocabulary
  (`--cd-motion-base`), reduced-motion respected.
- Lazy-load sections below the fold (React `lazy`/`Suspense` or an intersection-observer reveal) so
  first paint isn't gated on Intelligence Feed/Competitions/Following data.
- No duplicate network requests: sections that need the same underlying data (e.g. today's
  cross-sport fixtures feeding both AI Ready Fixtures and the system-status "last sync" timestamp)
  read from one shared React Query cache entry, never refetch.

## 7. Constraints and open decisions

- **Constraint**: never modify backend DTOs, routes, the Prediction Engine, the database, or
  existing React Query contracts (brief's explicit backend contract) — confirmed achievable for
  every section above using only already-existing endpoints.
- **Constraint**: max 6 cards per section, no unnecessary backend requests (brief's performance
  section) — addressed by the shared-cache/lazy-load approach above.
- **Open decision I'm resolving now, flagging for visibility**: the Intelligence Feed's exact
  per-source-type card sub-layout (article vs. community-topic vs. impact-event) isn't specified
  card-by-card in the master brief beyond the shared field list — I'll design one consistent card
  shell with a small source-type badge (News / Community / Impact) rather than three visually
  distinct card types, so the "premium magazine layout" reads as one feed, not three interleaved
  designs.
- **Builder must not invent**: the AI Picks confidence floor and tier thresholds (reused exactly
  from `ai-pick-card.tsx`'s existing constants), the Recently Completed Intelligence resolution
  rule (reused exactly), and the Insights page's existing pin/turn interaction model (extended via
  URL params only, never redesigned).
