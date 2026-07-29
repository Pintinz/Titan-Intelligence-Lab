# TitanIQ — Design System

Status: Live as of Milestone 10. Implements the token *names* fixed in Milestone 8
(docs/ui_design_system.md §2) with real values. Original visual language — informed by, never a
clone of, Linear/Stripe/TradingView/Notion/Vercel — reading as analytical, confident, and calm
rather than a betting-odds board (docs/titaniq.md §4).

## 1. Brand identity

"Titan Blue" indigo (`#4f7dfb` dark / `#3a63d1` light) is the primary accent — a cool, confident
blue distinct from generic SaaS blue and from any sportsbook color grammar. A warm amber
(`#d9a441` dark / `#a97a1f` light) is the secondary accent, reserved for premium/highlight
moments, not primary UI chrome. Semantic success/warning/danger/info are deliberately muted, not
neon — see docs/titaniq.md §4's rejection of flashing-odds visual language.

## 2. Design tokens (`frontend/src/styles/tokens.css`)

All values are CSS custom properties, mapped into Tailwind's `@theme` block
(`frontend/src/index.css`) so utilities like `bg-bg-primary` or `text-confidence-high` resolve
through the variable at paint time — flipping `[data-theme]` repaints every color instantly, no
React re-render required.

### Color

| Token | Dark | Light |
|---|---|---|
| `color.background.primary` | `#0a0e14` | `#ffffff` |
| `color.background.secondary` | `#10151d` | `#f6f7f9` |
| `color.background.elevated` | `#171d27` | `#ffffff` |
| `color.text.primary` | `#eef1f5` | `#10151d` |
| `color.text.secondary` | `#a7b0bf` | `#454e5c` |
| `color.text.muted` | `#6b7585` | `#767f8c` |
| `color.text.inverse` | `#0a0e14` | `#ffffff` |
| `color.accent.primary` | `#4f7dfb` | `#3a63d1` |
| `color.accent.secondary` | `#d9a441` | `#a97a1f` |
| `color.semantic.success` | `#3fb27f` | `#1f8f5f` |
| `color.semantic.warning` | `#d9a441` | `#a97a1f` |
| `color.semantic.danger` | `#d9615a` | `#c4433c` |
| `color.semantic.info` | `#4f9fd9` | `#2d7fb3` |

`color.confidence.{high,medium,low}` is a **separate scale** from semantic success/warning/danger
— confidence is a reliability signal, not "good/bad" (docs/ui_design_system.md §2). Dark:
`#3fa3b2` / `#b58a3f` / `#6b7585`. Light: `#237e8c` / `#92691f` / `#767f8c`. `ConfidenceMeter` and
`PredictionCard` pick the tone by threshold (≥0.7 high, ≥0.4 medium, else low), never by mapping
confidence onto the success/danger palette.

### Spacing, radius, typography, motion

- `spacing.{0..12}` — 4px base scale (0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48px).
- `radius.{sm,md,lg,full}` — 6px / 10px / 16px / 9999px.
- `typography.{display,heading,body,mono}` — Inter for display/heading/body; IBM Plex Mono for
  `mono` (used for stats, market keys, model versions, ids — anything numeric/identifier-like).
- `motion.duration.{fast,base,slow}` — 120ms / 200ms / 320ms, `easing.{standard,decelerate,accelerate}`
  as standard cubic-beziers. All zeroed under `prefers-reduced-motion: reduce` (`tokens.css`), plus
  Tailwind's `motion-reduce:` variant used directly on individual animated components (e.g.
  `Skeleton`'s pulse).

## 3. Light/dark mode

Dark is the default and primary mode (data-dense dashboards read best dark — docs/ui_design_system.md
§3). Toggled via `useThemeStore` (`frontend/src/stores/theme-store.ts`), persisted to
`localStorage`, applied via `data-theme` on `<html>` — deliberately **not** driven by
`prefers-color-scheme`, since dark stays default regardless of OS theme; only an explicit user
toggle (or a previously-persisted choice) changes it.

## 4. Grid & breakpoints

Tailwind v4 defaults: `sm` 640px, `md` 768px, `lg` 1024px, `xl` 1280px, `2xl` 1536px. The app
shell's sidebar is desktop-only (`lg:flex`, hidden below); a slide-in `MobileNav` drawer
(Radix Dialog) covers the same navigation below `lg`.

## 5. Motion guidelines

Motion communicates state change (loading → loaded, a value updating on a Realtime push) — never
decorative. Examples already in the system: `Skeleton`'s pulse (loading), `Progress`'s width
transition (value change), the live-match `Badge`'s pulse (status = live). All respect
`prefers-reduced-motion`.

## 6. Accessibility floor

WCAG 2.1 AA. Concretely: every interactive Radix primitive ships its own keyboard/focus/ARIA
behavior (Dialog traps focus and restores it on close, Select/DropdownMenu/Tabs are full
arrow-key navigable, Toast announces via `aria-live` internally); `:focus-visible` gets a visible
2px accent ring app-wide (`index.css`); icon-only buttons carry `aria-label`; decorative icons
carry `aria-hidden="true"`. Four component combinations are automated-tested for zero axe
violations (`frontend/src/test/accessibility.test.tsx`) — this is a spot-check on the primitives,
not a full-app audit (see the M10 STOP-GATE for what's not yet covered).
