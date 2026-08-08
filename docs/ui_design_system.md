# TitanIQ — UI Design System

> **Archived — superseded by [`design_system.md`](design_system.md).** This was the Milestone 8
> planning draft (token *names* only, values TBD). Every concrete thing it proposed — token
> values, dark/light mode implementation, component scope — has since shipped and is documented
> with real values in `design_system.md` (tokens/motion/accessibility) and
> [`ui_components.md`](ui_components.md) (component inventory). Kept here for historical
> reference only; do not treat anything below as current.

Status: Framework and principles defined; token values and component library land in
Milestone 8. Design must be original — informed by the usability bar of Apple, Linear, Stripe,
TradingView, Figma, Notion, Arc, and Vercel, but never a visual clone of any of them.

## 1. Brand Identity (to finalize in Milestone 8)

TitanIQ's visual language should read as *analytical, confident, and calm* — a data-intelligence
product, not a betting-odds board. Avoid the neon/urgency visual grammar common to sportsbook
UIs (flashing odds, countdown pressure, red/green gambling cues as the primary palette) since
the product philosophy explicitly rejects imitating betting sites
(see [titaniq.md](titaniq.md) §4).

## 2. Design Tokens

Structure (values TBD in Milestone 8, token *names* fixed now so components can be built
against stable references):

```
color.background.{primary,secondary,elevated}
color.text.{primary,secondary,muted,inverse}
color.accent.{primary,secondary}
color.semantic.{success,warning,danger,info}
color.confidence.{high,medium,low}      -- distinct scale from semantic colors;
                                          confidence is not "good/bad", it's a reliability signal
spacing.{0..12}          -- 4px base scale
radius.{sm,md,lg,full}
typography.{display,heading,body,mono}  -- mono used for stats/odds-like numeric data
motion.duration.{fast,base,slow}
motion.easing.{standard,decelerate,accelerate}
```

Tokens implemented as CSS variables + a Tailwind theme extension, consumed by every component —
no hard-coded hex values or px values in component code.

## 3. Modes & Responsiveness

Dark mode is the primary/default mode (data-dense dashboards read best dark); light mode is a
first-class second mode, not an afterthought. Mobile-first breakpoints, PWA-installable,
offline support for previously-loaded dashboards/predictions where feasible.

## 4. Core Component Library (initial scope, Milestone 8)

Global navigation & command palette · AI dashboard shell · prediction cards (must render the
full explainability contract from [api_specification.md](api_specification.md) §3: value,
confidence, risk, feature importance, limitations) · match intelligence pages · interactive
charts (Recharts-based) · advanced data tables (sortable/filterable, virtualized for scale) ·
search experience · skeleton loading states · empty states · error states · toasts/inline
validation · forms.

## 5. Accessibility

WCAG 2.1 AA as the floor: color contrast, keyboard navigation for every interactive element,
focus-visible states, semantic HTML/ARIA on custom components, reduced-motion support respecting
`prefers-reduced-motion`. Accessibility is checked in CI (axe or equivalent), not just at design
review.

## 6. Motion Guidelines

Motion communicates state change (loading → loaded, data updating live) — never decorative for
its own sake. Respect `prefers-reduced-motion` by substituting fades for spatial animation.

## 7. Milestone Mapping

Design tokens + component library scaffolding: Milestone 8. Prediction card + match
intelligence page (first real usage of explainability contract): Milestone 8–9. Admin Center UI:
Milestone 15. Full accessibility audit pass: before each major UI milestone's Definition of Done.
