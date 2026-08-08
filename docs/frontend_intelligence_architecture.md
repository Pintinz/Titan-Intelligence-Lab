# TitanIQ — Frontend Intelligence Architecture

**Status**: Live. Per-page reference for every AI/intelligence-facing surface — purpose, real API
calls, components, data-fetching pattern, and UI states. Complements
[`frontend_architecture.md`](frontend_architecture.md) (stack/folder/pattern level, not
per-page) and [`user_flows.md`](user_flows.md) (cross-page journeys, not a per-page reference) —
this is the page-by-page layer neither of those covers.

## Page inventory

| Product name | Real file | Route | Depth |
|---|---|---|---|
| Mission Control | `pages/home-page.tsx` | `/app` (index) | Full — the richest page, 9 `useQuery` sites |
| Match Intelligence | `pages/sports/match-detail-page.tsx` | `/app/:sport/matches/:matchId` | Full — 7 `useQuery` sites |
| Team Intelligence | `pages/sports/team-detail-page.tsx` | `/app/:sport/teams/:teamId` | Full — 11 `useQuery` sites, the largest detail page |
| Competition Intelligence | `pages/sports/competition-detail-page.tsx` | `/app/:sport/competitions/:competitionId` | Thin — 3 `useQuery` sites |
| Player Intelligence | `pages/sports/player-detail-page.tsx` | `/app/:sport/players/:playerId` | Thin — 1 `useQuery` site |
| Prediction Laboratory | `pages/sports/prediction-lab-page.tsx` | `/app/:sport/lab` | Full, but currently unlinked from the primary sidebar nav |
| News Intelligence | `pages/intelligence/news-intelligence-page.tsx` | `/app/news` | Full, deliberately unlinked from primary nav — surfaced contextually inside Match/Team/Competition/AI Picks/Assistant instead |
| Knowledge Graph | `pages/knowledge-graph-page.tsx` | `/app/graph` | **Placeholder** — see below |
| Assistant | `pages/insights/insights-page.tsx` | `/app/insights` | Full — labeled "TitanIQ Assistant" in nav |

## Mission Control (`home-page.tsx`)

- **Purpose**: the cross-sport landing dashboard — what's live now, top picks, recent news, graph statistics.
- **API**: `sportsApi.listFixturesPaged`, `marketsApi.list`, `predictionsApi.picks`, `predictionsApi.monitoringSummary`, `graphApi.statistics`, `intelligenceApi.searchNews`.
- **Components**: `InfinityPanel`, `InfinityMatchCard`, `InfinityPredictionCard`, `InfinitySkeleton`, `InfinityEmptyState`.
- **React Query**: `useQuery`/`useQueries`, 9 call sites — the heaviest fan-out of any page (multiple independent sport/market queries in parallel).
- **Caching**: standard React Query defaults; no custom `staleTime` overrides found beyond the query-key structure itself.
- **Loading**: `InfinitySkeleton` per section.
- **Empty states**: `InfinityEmptyState` per section (no live fixtures / no picks / no news, handled independently so one empty section doesn't block the others rendering).
- **Responsive**: `sm:grid-cols-2/4`, `lg:grid-cols-3/4`.

## Match Intelligence (`match-detail-page.tsx`)

- **Purpose**: the single-fixture prediction surface — the primary place "Generate Intelligence" is invoked for a specific match.
- **API**: `sportsApi`, `marketsApi`, `predictionsApi`, `graphApi`.
- **React Query**: 7 `useQuery` sites, including the KG lookup chain: `kgNodeQuery` (`graphApi.getEntity`) → `kgContextQuery` (`graphApi.context`, `enabled: !!kgNodeQuery.data`) — a dependent-query pattern, not two independent fetches.
- **Loading / empty states**: present per section.
- **Responsive**: `lg:block`, `lg:col-span-1/2`, `lg:flex-row`.

## Team Intelligence (`team-detail-page.tsx`)

- **Purpose**: the team profile and season-analytics surface — Hero command-center, season analytics, statistics, squad, fixtures, news, knowledge graph, all for one team.
- **API**: `sportsApi`, `marketsApi`, `intelligenceApi`, `graphApi` — the most API-surface-diverse detail page.
- **React Query**: 11 `useQuery` sites — the heaviest single-page fan-out of any detail page (recent/upcoming fixtures, standings, players, statistics, markets, news, sentiment, KG node, KG context).
- **Components**: this session built a distinct card-shell system for this page specifically (`TeamCard` with `record`/`metric`/`list`/`activity`/`graph` variants — see the design-system doc's Card System section) rather than reusing `InfinityPanel`'s corner-tick shell, since this page's cards read as evidence-dense analytics, not discovery cards.
- **Loading / empty states**: present per section, including honest "not tracked yet" states for DNA axes with no real backing data (pressing intensity, counter-attack frequency).
- **Responsive**: `lg:flex-row`, `lg:grid-cols-2/3/4`; verified down to mobile this session (record cards stack, statistics cards stack, no clipping).

## Competition Intelligence (`competition-detail-page.tsx`)

- **Purpose**: standings and fixtures for one competition.
- **API**: `sportsApi` only — the thinnest API surface of the sport-entity detail pages.
- **React Query**: 3 `useQuery` sites.
- **Responsive**: `sm:grid-cols-2`, `lg:grid-cols-3`.

## Player Intelligence (`player-detail-page.tsx`)

- **Purpose**: a single player's profile.
- **API**: `sportsApi` only, single `useQuery` site — the thinnest page in the whole inventory.
- **Note**: no distinct empty-state markup found (only loading-skeleton references) — a real gap if a player record is ever missing/malformed, worth closing before this page carries more weight.
- **Responsive**: `sm:grid-cols-3`.

## Prediction Laboratory (`prediction-lab-page.tsx`)

- **Purpose**: a market-exploration surface — pick a sport/market and inspect candidate predictions before committing to a specific fixture.
- **API**: `sportsApi`, `marketsApi`, `predictionsApi`.
- **React Query**: 3 `useQuery` sites.
- **Status**: real, routed page, but currently not linked from the primary sidebar — reachable only by direct URL. Worth a deliberate decision (link it, or confirm it's intentionally soft-launched) rather than leaving it in limbo.
- **Responsive**: `sm:grid-cols-2`, `sm:w-96`.

## News Intelligence (`news-intelligence-page.tsx`)

- **Purpose**: a standalone news/sentiment browser.
- **API**: `intelligenceApi` only.
- **React Query**: 3 `useQuery` sites.
- **Status**: deliberately unlinked from the primary sidebar by design (per `nav-config.ts`'s own comment) — news surfaces contextually inside Match/Team/Competition/AI Picks/Assistant instead, and this standalone page/route remains reachable directly. This is an intentional information-architecture choice, not an oversight (unlike Prediction Laboratory above, which has no such documented rationale).
- **Responsive**: `sm:grid-cols-2`, `lg:p-8`.

## Knowledge Graph (`knowledge-graph-page.tsx`)

- **Purpose**: entity/relationship exploration.
- **API**: `graphApi.getEntity()` (consolidated onto this single endpoint this session — previously called an admin-only duplicate).
- **React Query**: 1 `useQuery` site, keyed on the search input.
- **Honest status**: **this is an admitted placeholder**, by its own source comment: *"A real KG visualization would use D3 or Cytoscape; for now, this is a text-based explorer... The real graph UI is a follow-up feature."* It does not visually render the graph — it's a search-and-inspect form (type `team:Arsenal`, see that node's type/ref/attributes as text). Distinct from the embedded KG context panels inside Match/Team Intelligence, which show real connected-entity summaries without claiming to be a graph visualizer.
- **Components**: plain `ui/` primitives (`Card`, `Input`, `Skeleton`, `ErrorState`, `EmptyState`) — notably **not** the `Infinity*` design system used everywhere else in this inventory, a visual-consistency gap worth closing whenever the real graph UI work happens.
- **Responsive**: `lg:p-8` only — the least responsive-tuned page in this inventory.

## Assistant (`insights-page.tsx`, "TitanIQ Assistant")

- **Purpose**: a turn-based conversational interface over the platform's real data — history lookups, comparisons, sentiment pulses, relationship queries, note-taking.
- **API**: `sportsApi` only, directly — turn types (`history`/`compare`/`pulse`/`relationships`/`note`) are rendered via `insights-turns.tsx`, which itself calls `graphApi.getEntity()` for entity-comparison turns.
- **React Query**: 3 `useQuery` sites at the page level, plus dependent per-turn queries inside `insights-turns.tsx`.
- **Responsive**: `lg:grid-cols-*`, `lg:sticky`, `xl:grid-cols-*`.

## Shared API client layer

`frontend/src/lib/api/` — one client file per backend module: `admin-platform.ts`, `admin-predictions.ts`, `alerts.ts`, `billing.ts`, `graph.ts`, `identity.ts`, `intelligence.ts`, `markets.ts`, `ml-platform.ts`, `predictions.ts`, `sports.ts`, `tenancy.ts`, `watchlist.ts`, `webhooks.ts`, plus shared `client.ts` (fetch wrapper) and `types.ts` (response DTOs). Every intelligence page in this inventory composes calls from this shared layer — no page has its own bespoke fetch logic outside it.

## Cross-cutting patterns confirmed real (this session's audit)

- **No client/server state duplication**: watchlist follow/unfollow state lives entirely in React Query (`use-watchlist.ts` is a plain hook, not a Zustand store); the one plausible risk (auth profile) has exactly one fetch path by construction. See `decisions.md` for the full state-management audit if one gets written up separately.
- **Frontend types are actively reconciled against real backend responses**, not aspirational — `types.ts` carries inline comments recording past drift fixes (e.g. a feature-contribution tuple-vs-object mismatch that once crashed `PredictionPanel`).

## What this document does not cover

Visual design language (cards, gradients, glassmorphism, hero sections, icons) →
[`design_system.md`](design_system.md) and [`ui_components.md`](ui_components.md). Cross-page
user journeys → [`user_flows.md`](user_flows.md). The backend flow these pages consume →
[`ai_intelligence_flow.md`](ai_intelligence_flow.md).
