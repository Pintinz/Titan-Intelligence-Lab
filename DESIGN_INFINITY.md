# TitanIQ Infinity Design System — Phase 11.0 (Foundation) + Phase 11.1 (App Shell)

**Status**: Phase 11.0 (foundation) and Phase 11.1 (global app shell) both complete and
migrated. Every `/app/*` page — Dashboard, all four Sport Intelligence Centers, News/
Learning/Insights/Analytics/Knowledge Graph, Operations Center, Settings, Notifications,
Help — now renders inside the Infinity AppShell. No page's own content was redesigned;
see [Phase 11.1](#phase-111--global-app-shell--navigation) below. Per the brief, this is
where work stops and waits for approval before Phase 11.2 (Match Intelligence).

> **This status line is now stale — migration continued well past Phase 11.1.** Kept verbatim
> below as the accurate record of what Phase 11.0/11.1 themselves delivered (tokens, primitives,
> app shell), but content page-migration work has since shipped real Infinity-native pages and
> components beyond what "Honest scope" below lists as not-yet-built, including (non-exhaustive):
> Match Intelligence Hero + Prediction Center, real cross-links (Related Matches, Knowledge Graph
> context panel), Home Mission Control, Watchlist (follow/unfollow across match/team cards),
> Live/Competitions/Teams cross-sport pages, the premium `InfinityMatchCard` visual variant, and —
> most recently — a from-scratch Team Intelligence card system (`TeamCard` with `record`/`metric`/
> `list`/`activity`/`graph` variants replacing the corner-tick shell for that page's evidence-dense
> cards, plus a status-tinted top edge added to `InfinityMatchCard` itself). None of these are
> catalogued individually here — this file documents the *foundation* (tokens/primitives/shell);
> per-page build notes live in their own session history, not retrofitted into this document.
> Treat the token/primitive/component reference sections below as current; treat the phase-gate
> framing and "not built this pass" lists as a snapshot of Phase 11.1's specific delivery, not of
> where the system is today.

---

## Direction contract

**THESIS**: TitanIQ predicts by showing its evidence, the way a match official reviews
a decision — not a black-box score, a reviewable one. The category default this refuses
is "AI dashboard with a confidence bar"; the opposite rut it also refuses is generic
dark-terminal-plus-neon-accent.

**OWN-WORLD**: Broadcast officiating-review technology — goal-line tech, ball-tracking
overlays, VAR freeze-frame review panels, offside-line graphics. Cool broadcast-monitor
black (not pure black), one electric "review" cyan as the single signal color, hairline
borders with corner-tick calibration marks instead of rounded card chrome, uppercase
tracked micro-labels like broadcast lower-thirds, monospace telemetry numerals. Fourteen
domain hues form one calibrated wheel at matched saturation/lightness.

**STORY**: A user reads any TitanIQ surface the way they'd read a review overlay during
a match — here is the call, here is the evidence, here is how confident the system is,
and here is why. Trust comes from legibility of the reasoning, not polish alone.

**FIRST VIEWPORT**: N/A by design — this phase ships no page, only the foundation every
future page composes. The verification fixture is `/__infinity-showcase` (dev-only).

**FORM**: No new-work.md surface-concept roll was run for this phase — there is no first
surface to seed a composition for in a tokens-and-primitives pass. The world above was
chosen directly and disclosed to the user as a substitution at the start of the build,
per the skill's own transparency rule for exactly this case.

**FINISH**: kept — see [Verification](#verification-performed).

---

## Coexistence with the legacy system

This is an **additive, parallel system**, not a replacement of `tokens.css` or
`components/ui/*`. Confirmed with the user before writing any code:

- All new tokens live in `frontend/src/styles/tokens.infinity.css`, prefixed
  `--infinity-*` — a distinct namespace from the legacy `--color-*`/`--space-*` tokens
  every shipped page (Landing, Match Intelligence, Football Intelligence, Operations
  Center, TitanIQ Assistant) already reads. Loading this file changes nothing visually
  anywhere until a component is written to consume `--infinity-*` specifically.
- A second `@theme` block in `index.css` maps these to Tailwind utilities under the
  `infinity-*` prefix (`bg-infinity-ground-1`, `text-infinity-signal`, etc.), separate
  from the existing `bg-bg-primary`-style utility set.
- Every component lives under `frontend/src/components/infinity/` — new files, nothing
  in `components/ui/` was modified.
- **Migration order** (per the user's brief, for future phases — not started here):
  Global Design Tokens (this phase) → Layout Shell → Match Intelligence → Sport
  Intelligence Centers → Landing Page → TitanIQ Assistant → Operations Center →
  Remaining Pages. Only one flagship page migrates at a time; legacy tokens/components
  are removed only once every page has migrated off them.

---

## Token reference (`tokens.infinity.css`)

| Group | Tokens | Notes |
|---|---|---|
| Ground | `--infinity-ground-0..3` | Cool broadcast-monitor black, 4 elevation steps |
| Border | `--infinity-border-hairline/default/strong/signal` | Hairline-first; glow is reserved for live/signal states |
| Text | `--infinity-text-primary/secondary/muted/inverse` | |
| Signal | `--infinity-signal(-hover/-muted/-strong)` | The one interactive accent — electric cyan, distinct from legacy teal |
| Domain wheel | `--infinity-domain-{football,basketball,baseball,table-tennis,predictions,knowledge-graph,learning,news,community,operations,infrastructure,alerts,security}` | 13 hues, matched saturation/lightness in each theme — one calibrated wheel, not 13 unrelated picks |
| Confidence | `--infinity-confidence-{high,medium,low}(-muted)` | 3-step scale; high = signal cyan |
| Semantic | `--infinity-{success,warning,danger,info,live}(-muted)` | Status, distinct from domain/confidence |
| Elevation | `--infinity-elevation-{0,1,2,signal,live}` | Flat at rest; glow communicates "live/active," not generic depth |
| Glass | `--infinity-glass-bg(-strong)`, `--infinity-glass-border`, `--infinity-blur-{sm,md,lg}` | |
| Typography | `--infinity-font-{display,telemetry,body,mono}`, `--infinity-text-{display-2xl,display-xl,section-title,card-title,body,body-sm,metadata,stat-lg,stat-md,telemetry,code}` | Reuses the 3 already-installed fonts (Space Grotesk/Barlow Condensed/Inter) + system monospace — see [Typography](#typography) below |
| Spacing/grid | `--infinity-space-{1..20}`, `--infinity-container-{lg,xl,ultrawide}` | 4px base, matches legacy scale for muscle-memory continuity |
| Radius | `--infinity-radius-{sm,md,lg,full}` | Tighter than legacy (4/8/12px vs 6/10/16px) — closer to broadcast chrome |
| Motion | `--infinity-motion-{snap,base,hold,scrub}`, `--infinity-motion-sweep-duration` | Named for what they communicate, not just duration — see [Motion](#motion) |
| Breakpoints | `--infinity-breakpoint-{sm,md,lg,xl,2xl,ultrawide}` | Adds a named ultrawide step (1920px) the legacy scale lacks |

All of the above are defined for `:root` (dark, default), `[data-theme="light"]`, and
`[data-theme="high-contrast"]`, and collapse motion durations to `0ms` under
`prefers-reduced-motion: reduce`.

### Typography

No new font files were added. Operate-mode surfaces (which is what this foundation
primarily serves — cards, panels, forms, data-dense UI) are "well served by system
stacks and workhorse UI faces," and the three already-installed, already-fitting
typefaces (Space Grotesk display, Barlow Condensed telemetry, Inter body) already carry
the broadcast/precision character this world wants. What's new is the **role scale** —
eleven named roles with concrete size/line-height/tracking (see table above), replacing
ad hoc Tailwind `text-*` usage. Telemetry/code numerals use the system monospace stack
(`ui-monospace, "SF Mono", ...`) rather than a fourth webfont — zero added network
weight, in service of the brief's own "fast first paint" requirement.

### Motion

Named for what each duration communicates, not just its length:

- **snap** (100ms) — an instant state change, e.g. a button press confirming an action.
- **base** (200ms) — ordinary UI transitions (hover, focus).
- **hold** (420ms, decelerate-heavy easing) — a deliberate pause before revealing, used
  by the confidence ring/telemetry fill so a reading feels "found," not just animated.
- **scrub** (320ms) — smooth timeline/seek motion.
- **sweep** (1600ms, `InfinitySkeleton`) — the loading-state scan line, echoing a
  ball-tracking reticle.

All collapse to `0ms` under `prefers-reduced-motion: reduce`.

---

## Component library (`components/infinity/`)

### Primitives (`primitives/`)

| Component | Purpose | Variants/states | A11y | Constraints |
|---|---|---|---|---|
| `InfinityPanel` | The signature surface — hairline border + 4 corner-calibration ticks. Composed by nearly every other component. | `tone` (any CSS color, typically a domain/status token), `glow` (adds ambient box-shadow), `as` (div/article/section) | Purely presentational; consumers add their own `role`/`aria-*` | Corner ticks are `aria-hidden`; don't nest two panels without visual separation (ticks will visually collide) |
| `InfinityLabel` | Uppercase tracked micro-label — every panel eyebrow/section tag | `tone` override | Plain text, inherits consumer's heading structure | Never use as the only heading for a section — pair with a real heading for screen readers when it's the sole label |
| `InfinityButton` | Tactile button, 100ms snap motion + 1px active-state translate | `primary/secondary/ghost/outline/danger/success` × `sm/md/lg/icon` | Full keyboard support (native `<button>`), signal-cyan focus ring | — |
| `InfinityBadge` | Broadcast lower-third status/domain tag — dot + label, never a filled pill | `domain` (resolves via `DOMAIN_COLOR_VAR`) or `tone` (raw color) | Color is never the only signal — always paired with text | — |
| `InfinityInput` / `InfinitySearchInput` | Hairline-bordered fields | Standard input props pass through | Native `<input>`, label association is the consumer's responsibility | — |
| `InfinityTabs*` | Underline-style tabs (signal-cyan bottom bar) | Wraps Radix Tabs — same API | Full Radix a11y (roving tabindex, ARIA) | — |
| `InfinityEmptyState` | Never a generic illustration — explains, guides, recommends | `icon`, `title`, `description`, optional `action` | Icon is `aria-hidden`; heading text carries meaning | Always write a concrete `description` — never ship with placeholder copy |
| `InfinitySkeleton` | "Sweep" loading block — signal-cyan scan line, not a flat pulse | `className` for sizing | Collapses to static under reduced motion | Caller must size via `className` (no intrinsic size) |

### Cards (`cards/`)

Eight of the thirteen card types the brief named were built as dedicated components —
`InfinityMatchCard`, `InfinityPredictionCard`, `InfinityPlayerCard`, `InfinityTeamCard`,
`InfinityNewsCard`, `InfinityMetricCard`, `InfinityProviderCard`, `InfinityOperationsCard`.
All compose `InfinityPanel` + `InfinityLabel`/`InfinityBadge`, take typed props (no `any`),
and use `tabular-nums` on every numeral. **Not built this pass** (see
[Honest scope](#honest-scope--what-this-phase-did-not-build)): Competition Card,
Community Card, Knowledge Card, Model Card, Learning Card.

### Signature components

- **`InfinityConfidenceTelemetry`** (`confidence-telemetry.tsx`) — a continuous
  review-meter track (not the legacy 4-segment F1 bar) with a primary marker at the
  confidence value, reference ticks at 25/50/75%, secondary ticks per contributing
  model (clustering = agreement, spread = disagreement — visible without a separate
  number), and a trend arrow. Supports probability, confidence, model agreement,
  calibration, and trend in one component, per the brief's "Confidence Telemetry 2.0"
  requirement list.
- **`InfinityIntelligenceRail`** (`intelligence-rail.tsx`) — horizontal scroll of
  status-edge-marked chips. Supports all 7 statuses the brief named (live, upcoming,
  completed, high-confidence, learning, alert, breaking); only `live` items pulse.

### Charts (`charts/`)

Five of the twelve chart types the brief named were fully implemented, each with a
distinct rationale for its visual form (see in-file docblocks): `InfinityConfidenceRing`
(sweep-dial arc), `InfinityMomentumCurve` (shared-zero-line filled area), `InfinityRadarChart`
(targeting-reticle rings, not a filled-polygon-only radar), `InfinityPredictionEvolution`
(step-line — predictions jump on evidence, they don't drift), `InfinityHeatmap`
(cyan-interpolated intensity grid). **Not built this pass**: Timeline, Learning Pipeline,
Relationship Graph, Distribution, Comparison Bars, Telemetry (line), Trend — these are
straightforward extensions of the same visual language (hairline grid, signal-cyan
primary series, `tabular-nums` monospace labels) but weren't implemented as components.

### Navigation (`nav/nav-primitives.tsx`)

`InfinityNavItem` (left signal-bar active state), `InfinityBreadcrumbs` (chevron +
uppercase-tracked), `InfinitySportSwitcher` (segmented control, domain-colored
underline), `InfinityHeaderShell` (chrome slot), `InfinityCommandPaletteShell`
(visual-only — not wired to a real keyboard listener or router in this phase).
**Not built this pass**: Quick Actions, Context Actions, Profile Menu, Notifications
panel, Workspace Switcher — all straightforward compositions of the primitives above,
not attempted given the phase's "foundation, not page" scope.

### Icons

No custom-drawn icon set was produced. The brief's "unified icon language" is satisfied
by a **usage discipline** on top of the already-integrated `lucide-react` library
(already used consistently across the whole app): `size-3.5`–`size-4` inline with text,
`size-4`–`size-5` standalone, always `aria-hidden="true"` when paired with visible text,
domain color applied via `style={{ color: DOMAIN_COLOR_VAR[domain] }}` rather than a
Tailwind class (so it stays theme-reactive). Hand-drawing a full custom SVG icon system
was judged out of proportion to a foundation-only phase and not attempted.

---

## Hero surfaces and gradient/glow accents (added post-Phase-11.1, documented here retroactively)

Two real, shipped patterns not covered by the original Phase 11.0/11.1 scope above, since they
emerged from later per-page work (Match/Team Intelligence Hero) rather than the foundation pass:

- **Immersive hero pattern**: a full-bleed, forced-dark backdrop (ignores the active site theme —
  a hero reads as a photograph, not a themed panel) composited from: a procedural, code-drawn
  atmosphere layer (no fetched hero image exists in this system, so one is never faked — see
  `StadiumBackdrop`/`StadiumSvg` in `team-detail-page.tsx` for the reference implementation:
  floodlight glow, stand-bowl silhouettes, pitch perspective lines, all pure SVG), a scroll-linked
  parallax drift (±20px, disabled under `prefers-reduced-motion`), and glass-panel content cards
  (`bg-white/[0.06-0.11]` + `backdrop-blur-xl`) laid over it — never `InfinityPanel`'s corner-tick
  shell, which reads as an evidence panel, not an identity moment. Ambient tint is sampled from
  the subject's own real artwork (crest-color extraction via an offscreen canvas) rather than a
  hardcoded per-entity color table, so it scales honestly to entities with no curated brand color.
- **Corner-glow / gradient accent**: a 2px linear-gradient top edge (`tone → transparent`) plus a
  radial-gradient blur bloom anchored at one corner, opacity 0 at rest and animated to ~0.15–0.4 on
  hover/emphasis — the accent language for cards that represent a single strongly-toned entity
  (e.g. a Home/Away record card, tinted by the team's own crest-sampled color). Distinct from
  `--infinity-elevation-signal`'s fixed-cyan glow (§ Token reference above), which signals
  "interactive/selected" generically — this pattern's color is always the *subject's* real tone,
  never the system accent. **Refuse**: a plain flat `border-left`/`border-right` above 1px as a
  substitute for this — a thin gradient top edge or a genuine corner bloom reads as intentional
  accent language; a thick flat side-border reads as a lazy default.

---

## Honest scope — what this phase did not build

Per the project's established practice of never overclaiming completeness:

- **5 of 13 named card types** not built (Competition, Community, Knowledge, Model,
  Learning) — same pattern as the 8 that were, straightforward to add.
- **7 of 12 named chart types** not built (Timeline, Learning Pipeline, Relationship
  Graph, Distribution, Comparison Bars, Telemetry line, Trend).
- **5 of 11 named nav components** not built (Quick Actions, Context Actions, Profile
  Menu, Notifications, Workspace Switcher).
- **Forms**: only text Input/Search built. Textarea, Select, Checkbox, Radio, Toggle,
  Slider, OTP, Date/Time pickers not built.
- **Data components**: Tables, Lists, Timeline, Activity Feed, Comparison Grid,
  Leaderboards, Expandable Panels, Tree Views, Relationship Panels not built.
- **No custom icon set** — see [Icons](#icons) above for the substituted approach.
- **No formal new-work.md concept-seed roll** — see [FORM](#direction-contract) above
  for why, disclosed at the start of the build rather than silently skipped.
- **No page migration** — by explicit brief instruction ("do not continue to page
  redesigns... stop after the design system is complete").

None of the above blocks Phase 11.1 — they're straightforward extensions of an
established pattern (every file in this system follows the same
Panel/Label/Badge/token composition), not open design questions.

---

## Verification performed

- `tsc --noEmit` — clean, throughout the build and at the end.
- `npm run build` — production build succeeds (caught and fixed one real bug this way:
  a missing `ChartTile` helper that `tsc --noEmit -p tsconfig.json` alone didn't catch
  but `tsc -b` project-build mode did).
- Impeccable mechanical detector run over all 23 new files — **zero findings**.
- **Live browser verification** at `/__infinity-showcase` (dev-only route, gated by
  `import.meta.env.DEV`, unlinked from any nav): every primitive, all 8 cards, both
  signature components, all 5 charts, and every nav primitive rendered and inspected.
  One real bug found and fixed this way — `InfinityHeatmap`'s CSS grid had no explicit
  cell sizing (`1fr` tracks with no intrinsic content collapse to near-zero), so the
  heatmap rendered as an invisible 10×6px block until `cellSize` was made an explicit
  pixel prop. `tsc`/build/detector could not have caught this — only rendering it did.
- Light theme spot-checked via `data-theme="light"` — every token resolves correctly,
  same AA-contrast-deepening discipline as the legacy token system. Hover states
  verified across buttons, inputs (focus ring), nav items, command palette rows, and
  the sport switcher/tabs (confirmed via computed style: inactive-tab hover transitions
  exact match from `--infinity-text-muted` to `--infinity-text-secondary`).
- **Keyboard navigation & accessibility pass** — two real, systemic bugs found and fixed:
  1. `InfinitySportSwitcher` used `role="tablist"`/`role="tab"`/`aria-selected` (the ARIA
     APG tabs pattern) but implemented none of the pattern's required keyboard behavior —
     every tab had `tabIndex={0}` (so Tab moved between them one at a time, wrong) and
     Left/Right/Home/End did nothing. A screen reader user would hear "tab" semantics
     that don't work like a tab. Fixed with proper roving tabindex (only the active tab
     is `tabIndex 0`) and Left/Right/Home/End handlers that move focus and selection
     together, per the ARIA APG tabs pattern. Verified via dispatched `keydown` events
     confirming both focus and `aria-selected` moved correctly, not just the visual style.
  2. `--infinity-text-muted` — the color `InfinityLabel`, metadata, and timestamps render
     by default — only reached **3.38:1** contrast against `--infinity-ground-1` in dark
     theme (**3.71:1** in light theme), failing WCAG AA's 4.5:1 requirement for the small
     text it's universally used as. This wasn't visible from a screenshot; it required
     computing actual rendered contrast ratios. Fixed to `#77849a` (dark, 5.11:1/5.33:1)
     and `#5c6572` (light, 5.45:1/5.90:1) — both comfortably clear AA while staying
     visually "muted" relative to `--infinity-text-secondary`.
  - Also confirmed clean: full keyboard Tab order through every primitive (buttons,
    inputs, `InfinityTabs`) with correct skip of the `disabled` button; visible
    focus-visible ring (signal cyan, 4px, properly offset) confirmed via computed
    `box-shadow`, not just `outline`; disabled buttons correctly excluded from tab order;
    all tested domain badges pass AA (5.28–9.29:1); button/body text pass comfortably
    (11.11:1, 17.32:1). The Command Palette shell intentionally carries **no** ARIA role
    on its items (plain `<div>`s) — consistent with it being visual-only and not yet
    keyboard-operable, so it makes no false affordance to assistive tech, unlike the
    Sport Switcher bug above.
- **Performance & code splitting pass**:
  - **JS isolation confirmed exact**: `grep`'d the whole `src/` tree for any import of
    `components/infinity/*` outside the showcase page itself — none exist. A clean
    production build's main bundle is **1,351,504 bytes**, byte-for-byte identical to
    the pre-Phase-11.0 build — confirming zero JS weight added to any existing page.
    All 23 component files + the showcase page bundle into exactly one lazy chunk,
    `infinity-showcase-page-*.js` (34.6 kB / 8.5 kB gzip), loaded only if a browser
    navigates to the dev-only `/__infinity-showcase` route.
  - **CSS cost measured, not assumed**: `tokens.infinity.css` is global (CSS custom
    properties can't be code-split the way `import()` splits JS — they ship in the one
    stylesheet every page loads). Measured with a real before/after build rather than
    estimating from the source file's own size: **+1.58 kB gzip** to the app-wide CSS
    bundle (16.42 kB → 18.00 kB). This is real, unavoidable-with-this-architecture
    overhead every visitor pays today for a foundation zero pages yet consume — small,
    but worth naming rather than hiding. It amortizes as pages start adopting the system
    in Phase 11.1+.
  - **One real bug found via code review, not the build**: `InfinityMomentumCurve`'s
    `<linearGradient>` used a static `id="infinity-momentum-pos"`. SVG ids are
    document-global — a second mounted instance (e.g. home vs. away momentum rendered
    side by side, an entirely plausible real usage) would collide, and the browser
    resolves `fill="url(#...)"` to whichever element wins the duplicate id, silently
    breaking the fill on at least one instance. Fixed with `useId()` for a stable,
    per-instance, SSR-safe id. Verified by rendering the chart and confirming via
    `document.querySelectorAll('linearGradient')` that the id is now uniquely
    namespaced (`infinity-momentum-pos-_r_4_`), not by inspection alone.
  - **No heavy chart library pulled in**: all 5 charts are hand-rolled inline SVG, not
    recharts (already a dependency, used elsewhere) or a new library — zero bytes of
    charting-library weight added by this system at all, isolated or otherwise.
  - Motion respects `prefers-reduced-motion` (confirmed earlier in the design contract);
    no `Math.random()`/timers driving continuous re-renders anywhere in the system —
    every animation is CSS-driven (transitions/keyframes), not JS-interval-driven, so
    there's no idle CPU cost for a mounted-but-static Infinity component.

- **Mobile (375px) pass** — one real bug found and fixed: the showcase page's own
  domain-wheel demo grid (`grid-cols-4` with no mobile override) caused adjacent color
  labels ("infrastructure"/"alerts") to overlap at mobile width. Fixed to
  `grid-cols-2 sm:grid-cols-4 lg:grid-cols-7` with `truncate` safety on labels. This was
  a showcase-page layout choice, not a defect in any reusable component. Confirmed via
  `document.body.scrollWidth === window.innerWidth` (no horizontal overflow anywhere on
  the page) after the fix. Cards, charts, forms, Intelligence Rail (horizontal scroll),
  and Command Palette all confirmed responsive with no other issues.
- Console checked on a fresh tab load — zero errors.
- Confirmed via `git status` and manual review that **no existing page, route, or
  `components/ui/*` file was modified** — the only pre-existing files touched are
  `index.css` (new import + new parallel `@theme` block, additive) and `router.tsx`
  (new dev-only route + one new lazy import, additive).

---

## Phase 11.1 — Global App Shell & Navigation

**Scope, per the user's brief**: build the Infinity AppShell (sidebar, top navigation,
header, search, command palette, notifications, user menu, breadcrumbs, responsive
layout) as a controlled infrastructure migration, not a page redesign. Every existing
page keeps its content and functionality unchanged; they simply render inside the new
shell. Zero regressions — every commit compiles, type-checks, and passes the existing
test suite.

### What was built (`components/infinity/app-shell/`)

| Component | Real data source | Notes |
|---|---|---|
| `InfinitySidebar` | `NAV_GROUPS` (`layout/nav-config.ts`, unchanged) + `useAuthStore` role gating via `isAtLeast` | Same nav structure as the legacy `Sidebar`, restyled — left signal-bar active state instead of a filled pill |
| `InfinityMobileNav` | Same `NAV_GROUPS`/role gating | Radix Dialog drawer — reused Radix for the focus-trap/escape/overlay behavior rather than rebuilding it; Phase 11.0 didn't rebuild dialog primitives |
| `InfinityTopbar` | `useAuthStore` (real profile/sign-out), `useThemeStore` (real theme toggle) | Search trigger opens the real Command Palette; notifications link to `/app/notifications` with **no fabricated unread badge** (that page is itself still a Phase 7 placeholder — a fake number would be worse than no badge) |
| `InfinityCommandPalette` | `NAV_GROUPS` (role-filtered), `useAuthStore`, `useThemeStore` | Ctrl+K / Cmd+K. Every entry is real navigation or a real store action — no entity search (matches/teams/players), since no cross-entity search endpoint exists in the backend; fabricating results would violate the project's no-fake-data discipline |
| `InfinityAppBreadcrumbs` | `useLocation()` + `ALL_NAV_ITEMS` | Deliberately shallow — resolves only the current route's top-level nav match (longest `href` prefix). Never fabricates sub-page crumbs (a specific match, a specific provider); those pages own their own detail titles |
| `InfinityAppShell` | — | Structurally identical to the legacy `AppShell` (sidebar + mobile drawer + topbar + `<Outlet/>`), reuses the existing `ErrorBoundary` verbatim rather than rebuilding it |

### Migration approach actually taken

The brief asked for incremental migration with a verification gate before touching the
real route. Because the app's `/app/*` tree has exactly **one** shared layout component
wrapping it (not a per-page shell), "incremental" was implemented as two gates rather
than a page-by-page split (which the architecture doesn't support — a single `<Outlet/>`
subtree is inherently all-or-nothing for its wrapper):

1. **Isolation gate**: built `InfinityAppShell` alongside the legacy `AppShell` (untouched,
   still imported by the pre-existing `/__shell-preview` dev route), verified at a new
   `/__infinity-shell-preview` dev-only route (same `import.meta.env.DEV` gating
   convention already established) — desktop, mobile, dark/light theme, Command Palette,
   profile menu, mobile drawer — before the real route was touched.
2. **Migration gate**: only after (1) passed, swapped the single `element: <AppShell />`
   line in `router.tsx` to `<InfinityAppShell />` for the `/app` route, then re-verified
   with real pages (Dashboard, Operations Center) rendering inside it, real auth data, and
   the full regression suite (tsc/build/vitest).

The legacy `AppShell`/`Sidebar`/`Topbar`/`MobileNav` files are **not deleted** — they
stay in the tree, still referenced by `/__shell-preview`, per the "Legacy Removal" rule
from the user's own Phase 11.0 coexistence brief (remove only once all usages have
migrated and the user confirms). The nested `OpsShell` (Operations Center's own internal
sidebar) is completely untouched — it doesn't care what wraps it, and rendering it inside
the new outer shell required zero changes to `ops-shell.tsx` or any Ops Center page.

### A real dev-server bug found during verification (not a code bug)

Mid-verification, the showcase page and shell preview suddenly rendered with **zero**
Infinity styling — white background, black text, no domain colors — despite having
rendered correctly minutes earlier. Investigation (not assumption) traced it precisely:

- `getComputedStyle(document.documentElement).getPropertyValue('--infinity-ground-1')`
  returned an empty string, and the raw hex value `#05070a` was absent from the entire
  compiled CSS served to the browser — even though the `@theme` mapping block
  (`--color-infinity-ground-1: var(--infinity-ground-1)`) *was* present.
- The source files on disk were confirmed correct (`grep` showed the token defined at
  the right line, the import present and correctly ordered).
- This isolated the cause to **Vite dev-server state corruption**, not a source bug —
  almost certainly a lingering effect of the transient JSX syntax error hit hours earlier
  in this session (`provider-management.tsx`, since fixed) that never fully cleared from
  Vite's CSS dependency graph across subsequent HMR updates.
- **Fix**: stopped and restarted the dev server (`preview_stop` / `preview_start`) — a
  full process restart, not a page reload — which immediately restored correct styling,
  confirmed via a fresh tab and a clean re-verification pass.

Documented here because it's a genuine, reproducible class of failure worth knowing
about for future phases: if Infinity styling appears to vanish inexplicably mid-session
after touching an unrelated file, suspect dev-server state before suspecting the CSS.

### Verification performed

- `tsc --noEmit` — clean, at every stage (primitives → assembly → migration).
- `npm run build` — succeeds. Main bundle grew from 1,351,504 → 1,363,350 bytes
  (~11.8 kB, ~0.9%) — **expected and temporary**: both the legacy and Infinity shells are
  currently eagerly bundled (neither is behind a lazy `import()`), since the legacy shell
  is still reachable via `/__shell-preview`. This resolves once the legacy shell is
  removed in a future cleanup phase.
- `npm run test` (vitest) — **67/67 passing, 15/15 files**, byte-for-byte identical to
  the pre-migration baseline captured before any Phase 11.1 code was written.
- Impeccable mechanical detector on every new file plus `router.tsx` — zero findings.
- **Live verification with a real authenticated session** (not a mock): confirmed real
  `useAuthStore` profile data in the topbar/profile menu (`info.autotechub@gmail.com`,
  "Super Administrator"), real `useThemeStore` toggle (full shell re-themes correctly,
  confirmed via computed styles), real Command Palette navigation and fuzzy filtering,
  real mobile drawer open/close, and — critically — the real Dashboard and real nested
  Operations Center (with its own real Redis health / prediction market / system alert
  data from Milestone 11A) both rendering correctly inside the new shell with the
  breadcrumb trail (`Dashboard > Operations Center`) computed correctly from the actual
  route.
- Confirmed `ProtectedRoute` still functions: an unauthenticated tab visiting `/app`
  correctly redirects to `/login`, unchanged.
- Structural DOM check for the nested-button pattern fixed in an earlier milestone
  (`document.querySelectorAll('button')` + `.querySelector('button')`) — zero violations
  in the live authenticated `/app/ops` DOM under the new shell.

### Honest scope

- Search is navigation-only (see table above) — no entity search, disclosed rather than
  faked.
- Notifications is a link, not a live unread-indicator — the destination page itself is
  still a placeholder.
- Breadcrumbs are two levels deep (Dashboard → top-level section), not full deep-route
  trails — deeper trails would require guessing at page-owned structure this phase
  doesn't touch.
- Quick Actions / Context Actions (named in the original Phase 11.0 nav-component list)
  were not built into the real shell — the Command Palette's real navigation + account
  actions cover what's genuinely actionable today.

---

## Phase 11.3 — Sport Centers content migration

**Scope**: bring the four content pages the Sport Centers migration order still owed —
Match List, Team (list + detail), Player (list + detail), Competition (list + detail) —
onto Infinity. All seven pages previously imported the legacy `components/ui/*` and
`components/domain/*` primitives (`Skeleton`, `ErrorState`, `EmptyState`, `TeamCard`,
`PlayerCard`, `FixtureCard`, `CompetitionCard`) while `match-detail-page.tsx` one level
below them (Phase 11.2) was already fully migrated — the split this phase closes.

### A real-data correction to the Phase 11.0 card library

`InfinityTeamCard` and `InfinityPlayerCard` were built for the component showcase with
fields no backend tracks: team `competition`/`position`/`form` (win-draw-loss streak) and
player `statLabel`/`statValue`/`available` (fitness/availability). No lineup or
match-events ingestion exists (see the honest gaps already noted on `match-detail-page.tsx`
itself), so wiring these pages to the showcase props as-is would have meant fabricating
data. Both components' fabricated-only fields were widened to optional (rendered only
when supplied — real usage omits them, the showcase demo keeps passing them for a richer
gallery view) rather than rebuilt or duplicated.

### New: `InfinityCompetitionCard`

`components/infinity/cards/competition-card.tsx` — the fifth of Phase 11.0's five
not-built card types, added following the same `InfinityPanel` + `InfinityLabel` +
optional-real-fields composition as the correction above. Real fields only:
`type`, `country`, `tier` (all present on `CompetitionSummaryDto`).

### New shared util

`lib/sports-status.ts` — `isLiveStatus`/`fixtureCardStatus`, extracted from the inline
logic `match-detail-page.tsx` already had, now reused by every page building an
`InfinityMatchCard` list (Match List, Team Detail's recent fixtures, Competition Detail's
fixtures) instead of re-duplicating the same three-line status ternary a fourth and fifth
time.

### Verification performed

- `tsc -b` — clean.
- `npm run test -- --run` — 70/70 passing, including a `sport-pages.test.tsx` assertion
  updated from `getByText('Arsenal vs Chelsea')` to separate `getByText('Arsenal')` /
  `getByText('Chelsea')` checks, since `InfinityMatchCard` renders each team as its own
  text node rather than one combined string (the legacy `FixtureCard` it replaced did the
  opposite).
- `npm run build` — succeeds.
- **Live verification against the real backend** (not mocked): Football Teams, Team
  Detail (Manchester City — real recent fixtures via `InfinityMatchCard`, honest "No
  roster on file" empty state), Competitions, Competition Detail (Premier League — honest
  "No standings available" empty state, real fixtures grid), Players (honest "No players
  found" empty state — no player ingestion exists yet), and Match List (all 380 real
  synced fixtures) — zero console errors on every page.
- Player Detail and a populated Player List/roster could not be live-verified against real
  data in this pass, since no player records exist in the current dev database — the code
  path mirrors the proven Team List/Detail pattern exactly and passed `tsc`/tests, but this
  is disclosed rather than claimed as browser-verified.

### Not in scope this phase

`sport-hub-page.tsx`, `prediction-lab-page.tsx`, `sport-news-page.tsx`, and
`sport-community-page.tsx` remain on the legacy system — the Product Blueprint's roadmap
named only Match List/Team/Player/Competition for this phase; the remaining four Sport
Center pages are a follow-up.
