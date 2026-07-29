# TitanIQ — UI Component Library

Status: Live as of Milestone 10. Two layers: foundational primitives (`frontend/src/components/ui/`,
backend-agnostic, mostly thin Radix wrappers) and domain composites
(`frontend/src/components/domain/`, TitanIQ-specific, consume typed DTOs from `lib/api/types.ts`).

## 1. Foundational (`components/ui/`)

| Component | File | Notes |
|---|---|---|
| Button | `button.tsx` | CVA variants: primary/secondary/ghost/danger/link; sizes sm/md/lg/icon; `loading` disables + shows a spinner |
| Card (+Header/Title/Description/Content/Footer) | `card.tsx` | |
| Badge | `badge.tsx` | Variants: neutral/success/warning/danger/info/accent |
| Tag | `tag.tsx` | Removable chip |
| StatusDot | `status-dot.tsx` | Colored dot + optional label, tones success/warning/danger/info/neutral |
| Tabs (+List/Trigger/Content) | `tabs.tsx` | Radix Tabs |
| Breadcrumbs | `breadcrumbs.tsx` | |
| Input, Textarea | `input.tsx` | |
| Label | `label.tsx` | Radix Label |
| Select (+Content/Item/Group/Value) | `select.tsx` | Radix Select |
| Checkbox | `checkbox.tsx` | Radix Checkbox |
| Switch | `switch.tsx` | Radix Switch |
| Dialog (+Content/Header/Title/Description/Footer/Close) | `dialog.tsx` | Radix Dialog |
| DropdownMenu (+Content/Item/CheckboxItem/RadioItem/Label/Separator/Sub*) | `dropdown-menu.tsx` | Radix DropdownMenu |
| Popover | `popover.tsx` | Radix Popover |
| Tooltip (+Provider/Trigger/Content) | `tooltip.tsx` | Radix Tooltip |
| Accordion (+Item/Trigger/Content) | `accordion.tsx` | Radix Accordion |
| Toaster + toast store | `toaster.tsx`, `stores/toast-store.ts` | Radix Toast; imperative `toast.success/warning/danger/show()` API |
| Command Palette (+Empty/Group/Item) | `command-palette.tsx` | cmdk-based, controlled input, Cmd/Ctrl+K global shortcut |
| Progress | `progress.tsx` | ARIA progressbar, clamped 0-100% |
| Skeleton | `skeleton.tsx` | Loading placeholder, respects `motion-reduce` |
| EmptyState | `empty-state.tsx` | Icon + title + description + optional action |
| ErrorState | `error-state.tsx` | Icon + title + description + optional retry button |
| Separator | `separator.tsx` | Radix Separator |
| Avatar (+Image/Fallback) | `avatar.tsx` | Radix Avatar |

## 2. Domain composites (`components/domain/`)

| Component | File | Backend data it renders |
|---|---|---|
| StatCard | `stat-card.tsx` | Generic label/value/delta — used across Analytics/Model/Experiment centers |
| ConfidenceMeter | `confidence-meter.tsx` | Full 10-factor `ConfidenceBreakdownDto` |
| FeatureImportanceBars | `feature-importance-bar.tsx` | `ExplanationBundleDto.top_positive_features` / `top_negative_features` |
| PredictionCard | `prediction-card.tsx` | Full `PredictionDto` — value, probability, confidence (expandable), model version, SHAP-vs-heuristic indicator, KG/news/community contribution text, AI narrative |
| MatchCard / TeamCard / PlayerCard / CompetitionCard | `match-card.tsx` etc. | `FixtureSummaryDto` / `TeamSummaryDto` / `PlayerSummaryDto` / `CompetitionSummaryDto` (new `sports_router.py`, §Known Limitations in frontend_architecture.md) |
| ModelCard / ExperimentCard | `model-card.tsx` / `experiment-card.tsx` | `ModelDto` / `ExperimentDto` (ML Platform) |
| VirtualTable | `virtual-table.tsx` | Generic — row-virtualized (`@tanstack/react-virtual`) for any typed row + column-def list |
| Timeline | `timeline.tsx` | Generic dated-entry list — used for prediction history and the live Notifications feed |
| Stepper | `stepper.tsx` | Generic ordered-step indicator |
| KnowledgeGraphViewer | `knowledge-graph-viewer.tsx` | `KgNodeDto[]` / `KgEdgeDto[]` — deterministic radial layout (not a force simulation — see the file's own comment for why), pan/zoom via SVG viewBox, click-to-recenter |
| KeyValueGrid | `key-value-grid.tsx` | Renders any untyped aggregate-endpoint dict (monitoring/statistics responses) as label/value rows instead of a raw JSON dump |
| SportTabs | `sport-tabs.tsx` | Football/Basketball/Baseball/Table Tennis tab switcher, used across every sport-scoped Center |

## 3. Layout (`components/layout/`)

`AppShell` composes `Sidebar` (desktop, `lg:flex`, RBAC-filtered via `nav-config.ts` +
`isAtLeast`) + `Topbar` (search trigger, notifications link, theme toggle, user menu,
`MobileNav` trigger below `lg`) + a routed `<Outlet/>` + the global `GlobalSearch` command
palette. `PageLoader` is the `Suspense` fallback for every lazy-loaded route.

## 4. Component standards

- No hard-coded hex/px values — every color/spacing/radius value flows through a token
  (`tokens.css` → Tailwind `@theme` → utility class).
- No duplicated components — sport-specific variance (Match/Team/Player/Competition cards) is
  handled by separate small components sharing the same `Card` primitive and layout conventions,
  not by one component branching on a `type` prop.
- Every interactive primitive is a Radix wrapper (accessibility behavior is never hand-rolled)
  except where no Radix primitive exists (Command Palette uses `cmdk`; VirtualTable/Timeline/
  Stepper/KnowledgeGraphViewer are bespoke since there is no equivalent accessible-primitives
  library for them).
