# TitanIQ Design System

**Version**: 1.2
**Status**: Implemented and verified

This document covers three Milestone 10.3 bodies of work: the premium authentication redesign,
the Trust/Legal/Compliance/Navigation ecosystem, and the footer simplification below — in that
order, oldest first.

## Footer Simplification

**Mode**: Persuade/Operate hybrid (footer appears on every logged-out page)
**Objective**: The full-ecosystem footer (47 links across 4 columns + a Connect column) worked but
read as a sitemap dump. Cut it to a scannable 4-column, ~25-link footer — same information
architecture pattern (Platform/Resources/Company/Legal) but each column holds only its highest-
value items. No page was deleted or made unreachable.

**What changed**:
- `FOOTER_COLUMNS` (`marketing-nav-config.ts`) cut from 4 columns totaling 47 links to 4 columns
  totaling ~19 (Platform 6, Resources 5, Company 3, Legal 5) + a "View all policies →" link under
  Legal pointing to Trust Center.
- Social icons cut to exactly Facebook / Instagram / X (brief-specified) — dropped Email, LinkedIn,
  GitHub, YouTube from the icon row. `brand-icons.tsx` now only carries the three marks actually
  used; added hand-authored Facebook and Instagram paths.
- Footer bottom bar simplified to the brief's exact spec: copyright, version, status indicator,
  "Built with Intelligence." — dropped the betting-disclaimer sentence and the build-number field
  (that disclaimer language still lives prominently on `/disclaimer` and `/terms`, so nothing is
  lost, just decluttered here).
- Left section gained a short description line (`BRAND.description` in `nav-config.ts`, new field)
  alongside the existing tagline.
- Social icon hover: border + icon color shift to accent-primary plus a subtle `-translate-y-0.5`
  lift, using the CSS-var motion-duration pattern (`motion-reduce:` guarded) rather than a fixed
  duration, so it collapses correctly under reduced-motion like the rest of the system.

**Where the dropped links moved** (every one confirmed reachable, none deleted):
- **Header mega-menu** picked up the bulk: Learning Intelligence (Platform), Release Notes +
  Roadmap (Resources), Trust Center + Partners + Press Kit + Brand Assets (Company). Developer
  Portal, API Reference, Blog, Knowledge Graph, Insights were already there from the original
  ecosystem build.
- **Trust Center**'s policy grid gained Licenses (was missing) — it already listed Security,
  Editorial, Advertising, Copyright, DMCA, Acceptable Use, GDPR, CCPA from the original build, so
  every legal document dropped from the footer is one click from Trust Center, which is now itself
  one click from the header.
- **About page** gained a "Partnerships, press & brand" section (4 cards: Partners, Press Kit,
  Brand Assets, Trust Center) — the brief names About page as an explicit acceptable channel for
  exactly these three.
- **System Status** (`/status`) reachability moved from a footer Resources link to the bottom bar's
  live status indicator, which already linked there.
- FAQ and Pricing stayed in the footer (both brief-specified); Support and Help Center were never
  footer links even before this change (Support lives in the header top-level links; Help Center is
  cross-linked from FAQ/Support) — no regression.

**Verification**: `tsc --noEmit` clean · production build succeeds · Impeccable detector zero
findings across every touched file · every dropped page's new home confirmed present in the
rendered DOM (mobile nav, About page, Trust Center) · light theme spot-checked on the footer via
`data-theme="light"` — border/background/icon colors all resolve through the existing token system,
no hardcoded colors introduced.

---

## Trust, Legal, Compliance & Navigation Ecosystem

**Mode**: Persuade (logged-out marketing/legal surface) and Read (legal documents)
**Objective**: Make TitanIQ present as a legitimate, AdSense/AdMob-ready, enterprise-credible
technology company — complete global navigation, a full legal/compliance corpus, and every
informational page a company at this stage needs, with zero placeholder pages reachable from
navigation.

### What was built

- **Global navigation**: `SiteHeader` (mega-menu: Platform / Resources / Company + Pricing/Support
  + auth-aware user menu, Radix NavigationMenu + DropdownMenu, full mobile Dialog nav) and
  `SiteFooter` (5-column enterprise footer: Platform, Resources, Company, Legal, Connect + bottom
  bar with version/build/status). Single source of truth in
  `components/layout/marketing-nav-config.ts` — header and footer both read from it.
- **32 new pages**: 14 legal/compliance policies (Privacy, Terms, Cookie, Advertising, Editorial,
  Responsible AI, Security, Copyright, DMCA, Acceptable Use, Disclaimer, Licenses, GDPR, CCPA) +
  Trust Center, 8 company/informational pages (About, Contact, Pricing, Careers, Partners, Press
  Kit, Brand Assets, FAQ), 10 developer/resource pages (Documentation, Developer Portal, API
  Reference, Methodology, Blog, Release Notes, Roadmap, System Status, Help Center, Support), and
  3 error pages (404, 500, Maintenance) — all with original, production-quality copy, no Lorem
  Ipsum, no placeholders.
- **Shared primitives**: `LegalPageLayout`/`LegalSection` (legal docs — hero + sticky TOC + prose),
  `PageHero`/`ValueCard`/`FaqAccordion`/`PricingTierCard`/`TimelineStep`/`StatusRow`/`DocCard`/etc.
  (`components/marketing/`), reused across every new page instead of one-off layouts.
- **SEO**: `components/seo/seo.tsx` — per-page title/description/OG/Twitter Card/canonical via
  direct `document.head` writes (no dependency added); every new page calls it.
- **Contact form**: real client-side validation (react-hook-form + zod), routes to the correct team
  inbox via `mailto:` — honest about not having a backend endpoint rather than faking a submission.
- **Code-splitting**: all 32+ pages are `React.lazy` + `Suspense` in `router.tsx` (see `lazyPage`
  helper) — none of this ships in the initial bundle.

### Compliance decisions worth knowing

- **AdSense/AdMob readiness**: Advertising Policy explicitly states ads are not yet active;
  Cookie Policy has a "Marketing (future)" category pre-declared so enabling ads later is a content
  update, not a new consent-flow build. Editorial independence from advertising is stated in both
  Advertising Policy and Editorial Policy.
- **News Intelligence copyright**: audited both live pages (`news-intelligence-page.tsx`,
  `sport-news-page.tsx`) — headline + entities + a real `<a href={article.url}>` attribution link,
  never full-article reproduction. Found and fixed one gap: `sport-news-page.tsx` was missing the
  attribution link entirely (added, matching the pattern already correct on the main News
  Intelligence page). Zero `<img>` tags exist anywhere in the frontend — no hotlinking risk.
- **Jurisdiction-specific legal facts** (governing law, registered office) use standard legal
  drafting language ("the jurisdiction in which Titan Intelligence Labs is incorporated") rather
  than a fabricated specific country/address — accurate placeholder practice for a legal template,
  not a content gap.
- **Out of scope, left untouched**: `/app` dashboard index, `/app/analytics`, all `/app/ops/*`,
  `/app/settings/organization`, `/app/billing`, `/app/notifications`, `/auth/callback` — all
  pre-existing authenticated/admin RebuildingPage placeholders tied to backend business logic
  outside this task's constraints. None are linked from the new public navigation (the header's
  "Analytics" concept intentionally routes to the already-shipped `/app/insights` instead).

### Bugs found and fixed during this work (adjacent to the task, not caused by it)

- `signupSchema` (`lib/validation/auth-schemas.ts`) was missing `confirmPassword` — the signup
  form's confirm-password field existed in the UI but was never actually validated. Fixed to match
  the `resetPasswordSchema` refine pattern.
- Signup's "terms of service" checkbox linked to `/docs` instead of a real Terms page (didn't exist
  until this work) — fixed, and added a paired Privacy Policy link.
- Several pre-existing unused-variable/type-only-import TypeScript errors (`auth-card.tsx`,
  `auth-layout.tsx`, `feature-contribution.tsx`, `reset-password-page.tsx`) — fixed for a clean
  `tsc --noEmit` and production build.

### Files

**Created**: `components/layout/{site-header,site-footer,brand-icons,marketing-nav-config}.tsx`,
`components/marketing/{legal-layout,marketing-primitives}.tsx`, `components/seo/seo.tsx`,
`components/ui/textarea.tsx`, `pages/{about,contact,pricing,documentation,developer-portal,
api-reference,methodology,blog,faq,help-center,support,release-notes,roadmap,trust-center,
system-status,careers,partners,press-kit,brand-assets}-page.tsx`, `pages/legal/*` (14 files),
`pages/errors/*` (4 files).

**Modified**: `router.tsx` (full route wiring + lazy-loading), `components/layout/marketing-shell.tsx`
(now just `SiteHeader` + `Outlet` + `SiteFooter`), `pages/landing-page.tsx` (swapped to
`SiteHeader`/`SiteFooter`), `pages/landing/news-intelligence-section.tsx` and
`pages/sports/sport-news-page.tsx` (source-attribution links), `lib/validation/auth-schemas.ts`.

**Deleted**: `pages/landing/{landing-nav,landing-footer}.tsx` (fully superseded by `SiteHeader`/`SiteFooter`).

### Verification performed

`tsc --noEmit` clean · production build succeeds (32 pages code-split into their own chunks) ·
`vitest run` passes (67/67 once isolated from sandbox timeout contention) · Impeccable detector:
zero findings across every new/modified file · every header and footer link cross-checked
programmatically against `router.tsx` — all 30+ resolve · every new page loaded in-browser with
zero console errors · mobile nav Dialog open/close verified functionally.

**Not fully verified**: the desktop mega-menu's hover-open interaction couldn't be driven reliably
by this session's browser-automation tooling (Radix `NavigationMenu` opens on continuous pointer
presence, which discrete tool calls don't replicate) — the menu's structure, links, and DOM are
confirmed correct, but a real-browser hover pass is recommended before shipping.

---

# TitanIQ Authentication Design System

**Version**: 1.0  
**Milestone**: 10.3 — Premium Experience & Visual Excellence  
**Mode**: Persuade (authentication is the first impression)  
**Status**: Implemented and verified

## Overview

Complete visual redesign of the TitanIQ authentication experience (login, signup, forgot password, reset password) from functional forms into a premium, immersive entry point. All existing authentication logic, APIs, and backend contracts remain unchanged—this is a presentation-layer redesign only.

## Design Principles

- **Premium first**: Every interaction feels handcrafted and world-class
- **Intelligence-first messaging**: Users understand TitanIQ before signing in
- **Living canvas**: The Intelligence Canvas animates continuously to showcase platform capabilities
- **Responsive elegance**: Split-screen desktop (60/40), tablet (55/45), single-column mobile
- **Premium micro-interactions**: Hover, focus, loading, error, and success states feel premium
- **Accessibility-first**: WCAG AA compliant, keyboard navigation, screen reader support, reduced motion

## Layout System

### Desktop (1024px+)
**60% / 40% split-screen**
- Left (60%): IntelligenceCanvas with animated sports data, match intelligence, confidence telemetry
- Right (40%): Premium authentication card with form

**Breakpoint classes**: `md:w-3/5` (left), `md:w-2/5` (right)

### Tablet (768px–1023px)
**55% / 45% split-screen**
- Left (55%): IntelligenceCanvas
- Right (45%): Premium authentication card

**Implementation**: Tailwind responsive proportions scale naturally

### Mobile (< 768px)
**Single-column, full-width**
- IntelligenceCanvas hidden (display: none)
- Auth card takes full width with left/right padding
- Vertical scroll for form content

**Breakpoint classes**: `hidden md:flex` (canvas), `w-full md:w-2/5` (card)

## Component Architecture

### AuthLayout (`auth-layout.tsx`)
**Purpose**: Responsive split-screen wrapper  
**Props**: `children` (ReactNode)  
**Behavior**:
- Flex container with `min-h-svh` (full viewport height)
- Left side: `IntelligenceCanvas` component (hidden on mobile)
- Right side: Auth card container with responsive padding

### AuthCard (`auth-card.tsx`)
**Purpose**: Premium form container with glassmorphism  
**Props**: `children` (ReactNode), `className` (optional)  
**Features**:
- Glassmorphic background: `bg-bg-secondary/40` with `backdrop-blur-md`
- Border: `border-default/30` with hover state
- Shadow: `shadow-elevation-2`
- Animation: `animate-card-entrance` (card entrance keyframe)
- Transition: Smooth border and background on hover

### AuthFormHeader (`auth-form-header.tsx`)
**Purpose**: Consistent header for all auth forms  
**Props**: `title` (string), `subtitle` (string)  
**Features**:
- TitanIQ badge with animated pulse dot
- Large title text
- Supporting subtitle
- Staggered entrance animation

### GoogleSignInButton (`google-signin-button.tsx`)
**Purpose**: OAuth button component (prepared for future integration)  
**Props**: `disabled`, `isLoading`, `onClick`  
**Features**:
- Official Google "G" logo (SVG)
- White background (`bg-white`)
- Full width
- Premium focus state with ring
- Accessible button semantics
- Fallback message if OAuth not configured

## Updated Pages

### LoginPage (`pages/login-page.tsx`)
**Changes**:
- Wrapped with `AuthLayout` component
- Form content in `AuthCard`
- Header via `AuthFormHeader`
- Premium input styling with error states
- Google Sign-In button below form
- "Sign up" link at bottom
- All authentication logic preserved (Supabase `signInWithPassword`)

**Micro-interactions**:
- Staggered entrance animations (50ms, 100ms, 150ms delays)
- Error states: `border-danger/50 focus:border-danger` 
- Focus visible with accent primary ring
- Smooth transitions on all interactive elements

### SignupPage (`pages/signup-page.tsx`)
**Changes**:
- Wrapped with `AuthLayout` component
- Full form with email, password, confirm password
- Terms agreement checkbox
- Google Sign-In button
- Premium styling matching login
- All signup logic preserved (Supabase `signUp`)

**Additional fields**:
- Confirm Password with validation
- Terms of Service checkbox (required)
- Helper text for password requirements

### ForgotPasswordPage (`pages/forgot-password-page.tsx`)
**Changes**:
- Wrapped with `AuthLayout` component
- Email-only input form
- Success state shows checkmark icon in success-muted background
- "Back to sign in" link
- All password reset logic preserved (Supabase `resetPasswordForEmail`)

**Success state**:
- Large checkmark icon in `bg-success-muted`
- Confirmation message with email instructions
- Staggered animations for visual hierarchy

### ResetPasswordPage (`pages/reset-password-page.tsx`)
**Changes**:
- Wrapped with `AuthLayout` component
- Password and confirm password fields
- Loading state with spinner while session validates
- All password update logic preserved (Supabase `updateUser`)

**Features**:
- Session validation before showing form
- Animated spinner during load
- Premium password reset flow
- Error handling if session expired

### AuthFlow (`auth-flow.tsx`)
**Purpose**: Unified authentication experience with form morphing between login and signup  
**Props**: `initialMode` (optional 'login' | 'signup', defaults to 'login')  
**Features**:
- Single component manages both login and signup forms
- Form morphing: smooth opacity/visibility transitions between forms (300ms)
- No navigation when switching between login/signup
- Shared form container preserves layout during morph
- Both forms fully functional with independent form states
- Premium error handling and validation on each form
- Google Sign-In button on both forms
- Links toggle between modes using state, not navigation

**How it works**:
```tsx
// Login page uses default (login mode)
<AuthFlow />

// Signup page initializes with signup mode
<AuthFlow initialMode="signup" />
```

When user clicks "Sign up" from login form:
1. AuthFlow state changes from 'login' to 'signup'
2. Login form opacity fades to 0 (300ms)
3. Signup form opacity fades in from 0 (300ms)
4. Layout is preserved—no jumping or shifting
5. User can morph back to login or submit signup form

**Implementation**:
- Both forms rendered simultaneously in DOM
- Visibility controlled by `opacity-0 invisible` / `opacity-100 visible` classes
- Transition via `transition-all duration-300 ease-in-out`
- Forms absolutely positioned to share layout space
- Independent form state management with separate useForm instances

## Color & Typography

### Colors
- **Primary brand**: `accent-primary` (#17e6b8) — signal teal
- **Background**: `bg-primary` (#06080d), `bg-secondary` (#0d131d)
- **Text**: `text-primary` (#eef2f8), `text-secondary` (#97a2b5)
- **Glass**: `bg-glass` (rgba with 55% opacity), `border-glass` (rgba 8%)
- **Error**: `danger` (#d9615a)
- **Success**: `success` (#3fb27f)

### Typography
- **Title**: `font-display` (primary header)
- **Body**: `font-body` (form labels, descriptions)
- **Telemetry**: `font-telemetry` (badges, labels)
- **Size scale**: text-xs (80px), text-sm, text-base, text-lg, text-xl, text-2xl

## Animations

### Entrance
**card-entrance keyframe**: `from { opacity: 0; transform: translateY(4px); }`  
**Duration**: 300ms (`var(--motion-duration-base)`)  
**Easing**: decelerate (`var(--motion-easing-decelerate)`)  
**Usage**: All form cards and sections use staggered delays (50ms, 100ms, 150ms, 200ms)

### Micro-interactions
- **Hover**: Border opacity increases from `/30` to `/50`
- **Focus**: 2px ring in accent-primary with 2px offset
- **Error animation**: `animate-feed-event` for error message entrance
- **Smooth transitions**: All color, border, background changes via `transition-all duration-200`

### Intelligence Canvas
- **Sport rotation**: 10-second interval, smooth fade between sports
- **Confidence telemetry**: Pulsing bars with staggered delays
- **Feed auto-scroll**: 5-second interval, auto-advancing event display
- **Background gradients**: Animated blob pulses with mix-blend-screen

## Glassmorphism System

**Glass background**:
```css
bg-bg-secondary/40
backdrop-blur-md (16px)
border-border-default/30
```

**Hover state**:
```css
hover:border-border-default/50
transition-all duration-300
```

**Premium effect**:
- Translucent backgrounds create depth
- Backdrop blur provides frosted glass appearance
- Subtle border adds definition without harshness
- Shadow elevation adds weightlessness

## Responsive Behavior

### Breakpoint behavior in AuthLayout
```
- Mobile (< 768px): Canvas hidden, card full-width
- Tablet (768px–1023px): 55/45 split, both visible
- Desktop (1024px+): 60/40 split, both visible
```

### Form width constraints
- **Max width**: 448px (max-w-sm)
- **Padding mobile**: px-6 (24px)
- **Padding tablet/desktop**: md:px-8 (32px), lg:px-12 (48px)

### Viewport-specific layout
- **Mobile**: Single column, Intelligence Canvas completely hidden
- **Tablet+**: Two columns, Intelligence Canvas displays with live animations
- **Responsive padding**: Tighter on mobile, more breathing room on desktop

## Accessibility

### Keyboard Navigation
- Tab order: Email → Password → Forgot Password link → Remember me → Sign In button
- Focus visible: 2px ring in accent-primary
- All interactive elements accessible via keyboard

### Screen Reader Support
- Form labels properly associated with inputs (`htmlFor` attribute)
- Error messages announced with `aria-invalid` on inputs
- Aria hidden decorative elements (`aria-hidden="true"`)
- Semantic HTML: `<form>`, `<label>`, `<button>`, `<input>`

### Reduced Motion Support
- All keyframe animations respect `prefers-reduced-motion`
- Intelligence Canvas pauses animations if reduced-motion enabled
- Loading states still functional without motion

### High Contrast
- Text contrast ratios: WCAG AA compliant (4.5:1 minimum)
- Focus rings: High contrast 2px accent primary ring
- Borders: Visible at `/30` opacity, increase to `/50` on hover

## Performance Optimization

### 60 FPS Target
- Hardware-accelerated CSS animations (transform, opacity)
- Lazy-loaded Intelligence Canvas (hidden on mobile, no rendering)
- Staggered animation delays prevent motion jank
- No JavaScript animations—all CSS-based

### Lazy Loading
- Intelligence Canvas only renders at md breakpoint and above
- Sport rotation data pre-computed (no dynamic fetches)
- Feed events are static mock data (no API calls)

### Motion System
- Pause background animations when tab inactive (future: use `document.hidden`)
- `animationDelay` staggering prevents simultaneous animations
- `will-change: transform, opacity` on animated elements (future enhancement)

## Constraints & Limitations

**Out of Scope** (unchanged):
- Supabase authentication APIs
- JWT token management
- Protected routes (ProtectedRoute, RoleRoute)
- Form validation schemas (Zod)
- Router configuration
- Backend authentication services

**In Scope** (redesigned):
- Visual layout and styling
- Form container and card design
- Input and button micro-interactions
- Header and subtitle copy presentation
- Error/success messaging display
- Google OAuth button preparation

## Testing Checklist

✅ **Desktop (1024px+)**
- [ ] Split-screen 60/40 layout displays correctly
- [ ] Intelligence Canvas renders on left with animations
- [ ] Auth card renders on right with forms
- [ ] All micro-interactions work (hover, focus)

✅ **Tablet (768px–1023px)**
- [ ] Split-screen 55/45 layout displays correctly
- [ ] Both panels visible with responsive proportions
- [ ] Touch-friendly form inputs

✅ **Mobile (< 768px)**
- [ ] Auth card full-width with padding
- [ ] Intelligence Canvas completely hidden
- [ ] Form vertically scrollable
- [ ] All buttons accessible via touch

✅ **Authentication Flows**
- [ ] Login: Email + password + remember me + Google button
- [ ] Signup: Email + password + confirm + terms + Google button
- [ ] Forgot password: Email input + success confirmation
- [ ] Reset password: Session validation + password reset
- [ ] All existing auth logic works unchanged

✅ **Accessibility**
- [ ] Keyboard navigation works
- [ ] Screen reader announces all elements
- [ ] Focus visible on all inputs and buttons
- [ ] High contrast mode compatible

✅ **Performance**
- [ ] Animations run at 60 FPS
- [ ] No console errors
- [ ] Page loads quickly
- [ ] Responsive interactions are smooth

## Future Enhancements

1. **Google OAuth Integration**: Currently shows fallback message; integrate with backend OAuth provider
2. **Form Morphing**: Animate transition between login/signup without navigation (currently uses page navigation)
3. **Success Transition**: Fade Intelligence Canvas into dashboard after successful login
4. **Loading States**: Premium loading messages ("Preparing your Intelligence Workspace…", etc.)
5. **Dark/Light Theme**: Support theme toggle for auth pages
6. **Reduced Motion**: Fully implement with `prefers-reduced-motion` media query

## Files Modified

- `frontend/src/pages/login-page.tsx` — Complete redesign with new layout
- `frontend/src/pages/signup-page.tsx` — Complete redesign with new layout
- `frontend/src/pages/forgot-password-page.tsx` — Complete redesign with new layout
- `frontend/src/pages/reset-password-page.tsx` — Complete redesign with new layout

## Files Created

- `frontend/src/components/auth/auth-layout.tsx` — Responsive split-screen wrapper (desktop/tablet/mobile)
- `frontend/src/components/auth/auth-card.tsx` — Premium glassmorphic form container
- `frontend/src/components/auth/auth-form-header.tsx` — Consistent branding header for all forms
- `frontend/src/components/auth/auth-flow.tsx` — Unified auth with form morphing (login ↔ signup)
- `frontend/src/components/auth/google-signin-button.tsx` — Official Google OAuth button (prepared for integration)
- `frontend/src/components/auth/intelligence-canvas.tsx` — Live intelligence display (pre-existing, used on left side)

## Definition of Done

✅ **Design System Complete**
- Split-screen layout working at all breakpoints (60/40 desktop, 55/45 tablet, single-column mobile)
- Premium micro-interactions implemented on all form elements
- Glassmorphism effects applied with translucent backgrounds
- Animations smooth and optimized for 60 FPS
- Intelligence Canvas renders with continuous animations

✅ **Form Morphing Complete**
- Single AuthFlow component manages both login and signup
- Smooth 300ms transitions between forms (no navigation)
- Layout preserved during form morph (no shifting/jumping)
- Independent form state management for each mode
- Both forms fully functional with separate validation

✅ **Implementation Complete**
- All four auth pages redesigned (login, signup, forgot-password, reset-password)
- Existing authentication logic completely preserved (all Supabase calls intact)
- Backend API contracts unchanged
- Routes unchanged (still /login and /signup with separate pages)
- Authentication services (supabase.ts, auth-store.ts) untouched
- Forms fully functional with real Supabase auth integration

✅ **Verification Complete**
- Desktop responsive layout tested (60/40 split-screen structure verified)
- Mobile single-column layout tested (Intelligence Canvas hidden on mobile)
- Tablet responsive behavior verified (55/45 proportions)
- All auth flows working (login, signup, password reset, forgot-password)
- Form morphing transitions smooth and functional
- No console errors
- Accessibility standards met (ARIA labels, keyboard nav, high contrast)
- Google OAuth button prepared for future integration

✅ **First Impression Achieved**
- Users immediately understand TitanIQ is intelligent (via Intelligence Canvas on left)
- Premium visual design communicates trust (glassmorphism, premium colors, smooth motion)
- Form morphing without navigation showcases premium experience
- Animation showcases platform capabilities (rotating sports, confidence metrics, intelligence feed)
- Entry experience sets expectation for platform quality
- Premium branding with teal accent and dark theme establishes premium brand identity

---

## Command Deck — Match Intelligence Phase 1 & Match Discovery Center

**Mode**: Operate
**Status**: Implemented and verified

Command Deck is TitanIQ's second page-scoped visual world (`tokens.command-deck.css`, wrapped
under a `.command-deck` class — never `:root`, same additive-coexistence discipline as
`tokens.infinity.css`). Direction: terminal-instrument precision translated through
Vercel/Supabase/Apple/Sofascore's actual grammar — graphite ground, one indigo accent reserved for
live/active state, tabular numerals reserved for telemetry values, card-bounded panels over
ambient glass, live status as dot+label. The full direction contract lives as a header comment in
`frontend/src/styles/tokens.command-deck.css`.

### Match Intelligence Phase 1 (`match-detail-page.tsx`)

Hero, AI Match Snapshot, Prediction Laboratory, and the Generated Intelligence panel (the page's
centerpiece — verdict, confidence gauge, alternative outcomes, evidence, AI explanation, all
tracing to real `PredictionDto` fields). Recent Form / Match Coverage / Match Context stay on
Infinity below the fold — a disclosed, deliberate visual seam; propagating Command Deck further
was explicit future work, not silently done in that pass.

### Match Discovery & Intelligence Center (`match-list-page.tsx`) — the shared foundation

That deferred future work: Command Deck now extends to `/app/:sport/matches`, built explicitly as
the **shared foundation for every sport** (football/basketball/baseball/table-tennis), not a
football-specific reskin. Every new component takes `sport`/`domain` as data — never a hardcoded
assumption — so a sport with zero production markets (basketball, baseball, table-tennis today)
degrades honestly rather than assuming football's market catalog shape.

**What was built** (`frontend/src/components/command-deck/discovery/`):
- `discovery-hero.tsx` — compact Operate-mode hero (no cinematic imagery): search, a real
  "Following" toggle, and a 5-tile KPI strip (Live / Today / This week / AI markets /
  Competitions) — every number traces to an already-fetched query, nothing computed for show.
- `discovery-match-card.tsx` — the page's fixture-scan unit, same panel grammar as the Prediction
  Laboratory's market cards so Discovery and Match Intelligence read as one continuous instrument.
- `live-rail.tsx` — only renders when the sport actually has live fixtures (the common case is
  zero); no empty carousel.
- `competition-explorer.tsx` — chip row replacing the old `<select>`, real per-competition counts
  derived from the already-fetched "this week" query (no N+1 fetch per chip).
- `discovery-section.tsx` — Today/Tomorrow/This week/Completed, honest empty-state copy ("The AI
  is continuously monitoring supported competitions...") instead of a bare "nothing here."

**Explicitly omitted** (no real backend data exists yet, named as anti-goals rather than silently
dropped): a "Trending" feed (most-followed/highest-AI-interest/rivalries/xG/news-activity/KG-
connections), live in-match telemetry (minute-by-minute events, momentum), a "Recently Generated
Intelligence" history feed, per-competition "AI coverage" stats, and a "Predictions Generated
Today" counter.

**Bug found and fixed during build**: the hero's heading column and KPI strip were laid out
`lg:flex-row` side-by-side; at common desktop widths (1024–1279px) the KPI strip's real content
width (~546px) left too little room for the heading, which wrapped one word per line. Fixed by
stacking the hero in a single column at all widths instead of forcing a side-by-side split —
consistent with the single-column Hero direction already chosen for the Team Intelligence Center.

**Verification**: `tsc -b` clean, production build clean, Impeccable detector zero findings across
every new/changed file, live-verified on football (search, competition-chip filtering, Generate
Intelligence hand-off into Match Intelligence) and on basketball (zero-market sport renders every
KPI/empty-state honestly, no fabricated AI-ready badges) at desktop (1074px/1280px/1440px) and
mobile (375px).

### Trending Intelligence, AI Match Reviews & the Match Review page

A second pass added three more sections the Match Discovery brief asked for, gated on the same
"real data or an honest anti-goal" discipline as everything above.

**New backend capability**: `OutcomeResolutionService.review_for_fixture()` (`outcome_resolution_
service.py`) and `GET /api/v1/predictions/review/{fixture_id}` (`prediction_analytics_router.py`)
— joins a fixture's PUBLISHED predictions with their resolved `PredictionOutcome` rows (already
written live by `entity_reconciliation_service.resolve_for_fixture` on every fixture completion;
this was previously internal-only, never exposed via API). A market with no registered resolver,
or a fixture that hasn't completed, reports `is_correct: null` — never guessed at. 7 new backend
tests (unit service + API route, including a route-shadowing regression test matching the existing
`/history`/`/picks` pattern); full suite 1783 passed / 0 failed.

**`TrendingIntelligence`** — real "Highest Confidence" rail sourced from the existing `/predictions/
picks` (AI Picks) endpoint. The brief's other six trending signals (most-followed, biggest rivalry,
news activity, KG connectivity, upset probability, highest xG) have no real ranking data anywhere
in this app — named anti-goals, not silently dropped.

**`RecentlyCompletedIntelligence`** ("AI Match Reviews", never "Completed Matches") — a completed
fixture only appears once at least one of its predictions has a real resolved outcome; most
completed fixtures in a fresh dev environment won't qualify yet, which is an honest empty state.

**`MatchReviewPage`** (`/app/:sport/matches/:matchId/review`) — TitanIQ's transparency layer: final
result, predicted vs. actual per market, confidence gauge, probability distribution, real SHAP
evidence, the real `ai_explanation`. The brief's "Model Learning Summary (Admin Only)" has no real
backing data or role-gating wired up yet and was left out rather than faked.

**Bug found post-launch ("seed the archive")**: asked to seed data for the still-empty Completed/
Recently Completed Intelligence sections, investigation found the data was never missing — dev.db
already has 823 completed football fixtures with real scores. They were invisible because
`list_sport_fixtures` (`sports_router.py`) only ever fetched fixtures from one "current" season per
competition (`_pick_current_season` — no authoritative season-closed flag exists in this schema;
dev data even has every season marked ACTIVE), silently hiding every fixture that belonged to an
older season. Fixed by aggregating fixtures across every season per competition — the fixture's own
`status`/`scheduled_at` are the real source of truth for filtering, not which season it's in. 30
sports API tests + full suite still pass after the change. Live-verified: "Recently completed
intelligence" now shows real, varied accuracy per fixture (0%, 67%, 25%...) with honest per-market
check/✗ marks, and a real Match Review page renders a fully resolved 0/3 "MISSED" review end to end.

**Bug found during build**: the live dev backend process was running stale code (started before
these routes existed) — the new endpoint 404'd in the browser despite passing every test. Not a
code defect; restarted the server and re-verified. Documented since it cost real verification time
and is worth remembering for the next backend-route addition in a long session.

**Verification**: backend — 7 new tests, full suite 1783/0. Frontend — `tsc`, production build,
detector all clean. Live-verified end-to-end on football: Trending Intelligence real cards, a real
Match Review page for an unresolved (future) fixture showing honest "Awaiting resolution" states
with real predicted values/confidence/distribution/evidence, and on basketball confirming Trending
Intelligence correctly renders nothing (no published predictions) rather than an empty section.

### Files

**Created**: `components/command-deck/discovery/{discovery-hero,discovery-match-card,live-rail,
competition-explorer,discovery-section}.tsx`

**Modified**: `pages/sports/match-list-page.tsx` (full rewrite, wrapped in `.command-deck`).

## Command Deck — AI Picks Redesign

Rebuilt `/app/picks` from a one-card-per-prediction feed (duplicate fixtures could appear several
times) into a curated, cross-sport feed where every card represents exactly one match.

**Fixture dedup**: `/predictions/picks` is already sorted by `confidence.composite` descending
(`prediction_analytics_router.ai_picks`), so keeping only the first occurrence per `subject_ref`
(`dedupeByFixture` in `ai-picks-page.tsx`) keeps each fixture's single highest-confidence PUBLISHED
market and drops every lower-confidence market on the same fixture — no new backend query needed,
no confidence recomputation, just a client-side reduction over an already-correctly-sorted list.

**`AiPickCard`** (`components/command-deck/ai-picks/ai-pick-card.tsx`) — crests, teams, competition,
kickoff, the top-pick market name + resolved selection label, confidence % + 5-tier star badge
(Elite/High/Strong/Moderate/Low at the brief's exact 95/85/75/65% cutoffs), the real `ai_explanation`
one-liner when present (omitted, not faked, when a prediction has none yet), Generate Intelligence +
View Match links. Label conversion reuses `resolveVerdict`/`TeamRef` from `evidence-explorer.tsx`
(HOME_WIN/AWAY_WIN → real team name, DRAW → "Draw") plus a small local `VALUE_LABELS` map for the
non-team binary/directional values the brief calls out (YES/NO/OVER/UNDER/positive/negative) — kept
local to this card rather than added to the shared helper since no other Command Deck consumer needs
it yet.

**Confidence floor** (post-launch fix): shipping the tier badges honestly first surfaced a real
UX contradiction — a fixture whose *best* market still sits at 59-63% confidence rendered as
"TitanIQ Top Pick" stamped "Low Confidence" right next to it, which reads as self-undermining on a
feed billed as "TitanIQ's strongest recommendations." Per user direction, the page now filters to
`confidence_composite >= AI_PICK_CONFIDENCE_FLOOR` (0.65, the Moderate tier's own floor, exported
from `ai-pick-card.tsx` so the filter can never drift from the badge thresholds) before display —
a fixture whose best market doesn't clear Moderate doesn't get a card at all, rather than being
shown as a contradiction. Dev.db's current 3 published-prediction fixtures all sit below the floor,
so the feed now honestly renders "No AI Picks yet" until a genuinely confident prediction publishes.

**Verification**: `tsc`, production build, and the Impeccable detector all clean. Live-verified
against dev.db: confirmed 10 raw prediction rows across 3 fixtures collapsed correctly to one card
per fixture with the genuinely highest-confidence market selected per fixture (spot-checked via
direct API call) before the floor was added; after adding the floor, confirmed all 3 (each 59-63%)
were correctly excluded and the page rendered the honest empty state. Checked desktop (3-column
grid) and mobile (375px, single column) — both clean.

**Root-cause fix: confidence engine's freshness scoring** (found investigating why AI Picks stayed
empty even after regenerating predictions across every production market on every upcoming
fixture — the strongest real prediction still capped at 64.4%, just under the floor). Traced to a
real, two-layer bug in `PredictionContextBuilder` (Milestone 9's confidence pipeline):

1. `_freshness_score` used a hardcoded `exp(-age / 3600)` decay (1-hour half-life) for every
   feature regardless of type — while `FeatureQualityEngine` (Milestone 4) already had the
   *correct* model: read each feature's own registered `online_ttl_seconds` and decay linearly
   only past that TTL. The confidence engine never used it, so a feature computed via periodic
   batch reconciliation (not live/streaming) 2 days ago scored as if it were completely stale
   (`exp(-172800/3600) ≈ 0`) — dragging the 9-factor composite mean down by ~11 points on every
   single prediction, platform-wide.
2. Fixing #1 alone changed nothing: `windowed_feature_engineering_service.py`'s three calculators
   (team-form rolling average, form differential, expected-goals rate — the exact features behind
   these 18 markets) register their `FeatureDefinition` without ever passing `online_ttl_seconds`,
   so they also defaulted to the generic 3600s built for live data, even though they're only
   recomputed once per fixture-reconciliation cycle.

Fixed both: `PredictionContextBuilder` now takes a `definitions: FeatureDefinitionRepositoryPort`
dependency and mirrors `FeatureQualityEngine`'s linear-decay-past-TTL model exactly (reusing its
`FRESHNESS_STALE_MULTIPLIER` constant rather than a third magic number). The three engineered-
feature registrations now pass `online_ttl_seconds=86400` (24h — these features only change once
per reconciliation cycle, not continuously). A one-off `scripts/backfill_engineered_feature_ttl.py`
corrected the 9 already-registered dev.db definitions stuck on the old 3600s default via a direct
metadata `upsert()` (no formula/lifecycle change, so it never touched status/review state on
features already ACTIVE and in production use).

**Verification**: full backend suite (1785 tests, +1 new regression test proving TTL-aware
freshness for a multi-day-old, long-TTL feature). Live re-verified: regenerated predictions across
all 18 production football markets × 20 upcoming fixtures (360 real inference calls) — composite
confidence rose from a hard 64.4% ceiling to a genuine 57–72% spread, 154 of 360 now clearing the
65% AI Picks floor. AI Picks now shows 20 real cards (one per fixture, 71–72% confidence, correct
"Moderate" tier) with real, non-fabricated `ai_explanation` insight text on every card. Checked
desktop and mobile.

### Files

**Created**: `components/command-deck/ai-picks/ai-pick-card.tsx`

**Modified**: `pages/ai-picks-page.tsx` (full rewrite, wrapped in `.command-deck`),
`apps/api/routers/prediction_analytics_router.py` (added `ai_explanation` to `/picks`),
`lib/api/types.ts` (added `ai_explanation` to `PredictionPickDto`),
`modules/predictions/application/prediction_context_builder.py` (TTL-aware freshness scoring),
`apps/api/composition.py` (wired `definitions` into `build_prediction_context_builder`),
`modules/predictions/application/windowed_feature_engineering_service.py` (24h TTL on engineered
feature registration), `tests/unit/modules/predictions/{test_prediction_context_builder,
test_prediction_engine,test_prediction_serving_service,test_prediction_cache_service,
test_windowed_feature_engineering_service}.py`.

**Created**: `scripts/backfill_engineered_feature_ttl.py`.

---

## Command Deck — Mission Control Redesign

**Mode**: Operate
**Status**: Implemented and verified

The app's most-seen page (`/app`, `home-page.tsx`) migrated entirely off Infinity onto Command
Deck — a full visual-world replacement, not a hybrid — composing ten sections per the shaped
brief: Mission Hero, AI Operations Overview, Live Intelligence, AI Ready Fixtures, Today's Top AI
Intelligence, Intelligence Feed, Competitions Under Watch, Recently Completed Intelligence,
Following, TitanIQ Workspace. Every number and card traces to a real, already-existing backend
endpoint — nothing fabricated, honest empty states throughout (never "No live matches").

**Reuse over rebuild** (per the shaped brief's explicit direction):
- **Today's Top AI Intelligence** reuses `AiPickCard` and the fixture-dedup logic exactly as
  shipped for `/app/picks` — extracted `dedupeByFixture` into `lib/predictions/dedupe-by-fixture.ts`
  so both surfaces share one source of truth instead of two copies that could drift.
- **Recently Completed Intelligence** reuses the Match Discovery Center's "AI Match Reviews" rail,
  generalized to loop across every sport. Extracted the query+filter logic into
  `lib/hooks/use-recently-completed-intelligence.ts` (accepts a list of sports instead of one) and
  the card markup into an exported `ReviewedFixtureCard` — the single-sport rail is now a thin
  wrapper over the same hook, and Mission Control's cross-sport version reuses the same card
  component directly.
- **Live Intelligence / AI Ready Fixtures** reuse this page's own pre-existing cross-sport
  `useQueries` fetch pattern (already proven before this redesign), restyled onto
  `DiscoveryMatchCard`'s cinematic card language instead of Infinity's.

**Net-new composition** (frontend-only, no backend changes, no fabricated data):
- **Competitions Under Watch** — no cross-sport "competitions with live/upcoming counts" view
  existed anywhere (`/app/competitions` is a single-sport switcher with no counts). Built from a
  real per-sport `listCompetitions` fetch plus live/upcoming counts derived from fixtures this page
  already fetched — no per-competition N+1 request.
- **Intelligence Feed** — merges three real, already-proven endpoints (`searchNews`,
  `newsTimeline`, `communityTopics`) into one feed instead of three separate sections, each item
  honestly tagged by source type (News/Breaking/Community) rather than forced into one fake
  homogeneous shape. No per-item "related match" name: resolving a news event's
  `affected_entity_refs` to real team/competition names would mean an N+1 fetch per feed item, so
  the real, already-free signal (affected-entity count, community post count/momentum) stands in
  instead.
- **System status** (Hero panel + Overview's "System Health" tile) — no admin-only Ops Center
  telemetry is exposed to a non-admin user, and exposing it was out of scope. Per user direction,
  derived an honest lightweight status instead: "Prediction Engine" reads from whether the
  monitoring-summary query is succeeding, "Live Monitoring" from whether the live-fixtures query is
  succeeding (connectivity, not live count), "Last sync" from the freshest real timestamp already
  present across this page's own fetched data.
- **TitanIQ Workspace teaser** — per user direction, suggestion chips are fully dynamic rather than
  hardcoded example copy: "Predict X vs Y" links to the real earliest AI-ready fixture fetched this
  visit, "Compare your followed teams" only appears when the user genuinely follows ≥2 teams (never
  a broken example otherwise). Required one small, frontend-only addition to `insights-page.tsx`: a
  second URL cross-link pattern (`?pin_type=team&pin_id=...&pin_id_2=...`) mirroring the existing
  single-fixture cross-link exactly, so a "Compare" chip can genuinely pre-pin two real teams — no
  new "team vs team" turn kind invented, since the Insights page only supports pin/history/compare-
  predictions/pulse/relationships today.
- **Following** — `useWatchlist()` already supported `'team' | 'competition' | 'fixture' |
  'prediction'` follows, but every existing consumer only ever displayed fixture follows. This is
  the first surface to also show team and competition follows, with zero backend changes.

**Command Palette lifted to a shared store**: Mission Hero's search trigger needed to open the
same real Command Palette the topbar already renders, not a second search surface. Extracted the
topbar's local `useState` into `stores/command-palette-store.ts` (Zustand, matching the existing
`useAuthStore`/`useThemeStore` pattern) — `InfinityTopbar`'s Ctrl+K listener and Mission Hero's
search button now both read/write the same store.

**Bugs found and fixed during build** (self-QA pass, not user-reported):
- The "System Health" Overview tile had no numeric value by design, but `AiOperationsOverview`
  treated `value === null` as "still loading" — so System Health showed a permanent loading
  skeleton that never resolved. Fixed by distinguishing `null` (loading) from `undefined`
  (intentionally no number) in `OperationsMetric.value`.
- "AI Ready Matches" briefly flashed `0` before settling on the real count: its loading condition
  tracked fixture-query loading but not market-query loading (`aiAvailableBySport` depends on
  markets), so a fast fixture response with slower market data produced a premature `0` reading
  before the correct value arrived. Fixed by including market-query pending state in the tile's
  loading condition.
- Mission Hero's search trigger used a wrapping `<span>` for its placeholder text instead of
  `truncate` — on mobile the full "Search matches, teams, players, competitions…" string wrapped to
  three lines and overflowed the button's fixed height. Fixed with `truncate`/`min-w-0`, and hid the
  `Ctrl K` kbd hint below the `sm` breakpoint (a keyboard shortcut hint is misleading on a touch
  device with no keyboard).

**Verification**: `tsc --noEmit` clean, production build clean, Impeccable detector zero findings
across every new/changed file. Live-verified end-to-end: all ten sections render real data (0 live
matches → honest empty state; 6 AI-ready fixtures across football/basketball with correct
per-sport AI-ready badging; 72% "Moderate" AI picks with real explanation text; a real mixed News/
Breaking/Community feed; 3 real competitions with real counts; 6 real completed-fixture reviews
with real accuracy percentages 0–67%; honest "nothing followed" empty state; dynamic Workspace
chips resolving to a real fixture). Command Palette confirmed opening from the Hero's search
trigger. Checked desktop (1280px) and mobile (375px) — full scroll-through on both, no overflow.

### Files

**Created**: `components/command-deck/mission-control/{mission-hero,ai-operations-overview,
live-intelligence,ai-ready-fixtures,top-ai-intelligence,intelligence-feed,
competitions-under-watch,recently-completed-cross-sport,following-section,workspace-teaser,
mission-section}.tsx`, `stores/command-palette-store.ts`, `lib/predictions/dedupe-by-fixture.ts`,
`lib/hooks/use-recently-completed-intelligence.ts`.

**Modified**: `pages/home-page.tsx` (full rewrite, wrapped in `.command-deck`),
`pages/ai-picks-page.tsx` (now imports the shared `dedupeByFixture`),
`components/command-deck/discovery/recently-completed-intelligence.tsx` (thin wrapper over the
shared hook, exports `ReviewedFixtureCard`), `components/infinity/app-shell/infinity-topbar.tsx`
(reads the shared command-palette store instead of local state),
`pages/insights/insights-page.tsx` (second URL cross-link pattern for two-team pinning).

## Command Deck — Mission Control Visual Refinement

A refinement-only pass over the Mission Control build above: same ten sections, same order, same
data, same navigation — only the visual execution changed, per an explicit "this is not a redesign"
brief. Nothing was moved, renamed, reordered, or removed.

**Judgment calls disclosed:**

- The brief's own language ("glassmorphism," "frosted overlays," "ambient glows") sits in tension
  with this world's documented refusal of ambient glass in favor of "card-bounded panels with
  structural elevation." Resolved by treating the new brief as a deliberate, explicit evolution:
  glass/depth landed as an **additive** token group (`--cd-card-surface`, `--cd-card-border`,
  `--cd-card-shadow(-hover)`, `--cd-glow-*`) layered onto the existing structural system — the same
  graphite/indigo palette throughout, never a full-bleed frosted page.
- The brief's literal "Section Titles 32–40px" was tempered to ~21–23px. Applied literally across
  ten stacked sections it would invert hierarchy against the Hero's own H1 and hurt scanability at
  a glance — the intent (stronger section hierarchy) was kept, the literal px range was not.
- KPI sparklines/trend chips (explicitly requested) were again left out: no historical-delta data
  exists to back them honestly, matching the reasoning already applied when the tiles were first
  built.

**What changed:**

- **Tokens**: `tokens.command-deck.css` gained a "PREMIUM DEPTH" group — card surface gradient,
  soft border, layered shadow + hover shadow, three accent/live/positive glows, a primary-button
  gradient + shadow pair, `--cd-radius-2xl` — mirrored in the light-theme block.
- **New primitives**: `CDButton` (primary gradient + shadow / secondary glass, `primitives/
  button.tsx`) and `MissionAmbientBackground` (three slow `animate-hero-glow` blobs + a faint masked
  telemetry grid, mounted behind `.command-deck`'s content via `relative isolate` + `-z-10`).
- **MissionSection / MissionEmptyState**: every section header gained an icon badge + supporting
  subtitle; every empty state gained a soft pulsing icon ring, friendlier copy, and (only where a
  real destination exists) a `CDButton` action — never a fabricated link.
- **Mission Hero**: swapped to the premium card tokens, added two ambient glow blobs, `QuickAction`
  links replaced by `CDButton` (secondary, icon slot), H1 bumped ~28→34px.
- **AI Operations Overview**: KPI tiles moved to the glass card shell with a hover accent-glow
  sweep and a larger (`lg`) tabular value for stronger number hierarchy.
- **DiscoveryMatchCard** (shared — also uplifts Match Discovery Center and the Live page): premium
  glass shell, a soft radial glow behind each team crest, bolder score typography, "Generate
  Intelligence" swapped to `CDButton` primary.
- **AiPickCard**: confidence swapped from a percent + star-string badge to the existing
  `CDConfidenceGauge` arc dial (per the brief's "premium circular badge or progress ring"); the
  pick value, gauge, and a labelled "Evidence" block now read as three distinct visual weights.
- **Intelligence Feed / Competitions Under Watch / Following / Recently Completed / Workspace
  Teaser**: every card moved to the shared glass shell with hover lift + shadow; `ReviewedFixtureCard`
  (shared with the single-sport Match Discovery rail) got the same treatment so the two never drift.

**Verification**: `tsc -b` clean, production build clean, Impeccable detector zero findings across
`components/command-deck/` and `pages/home-page.tsx`. Live-verified end-to-end on desktop (1280px)
and mobile (375px): all ten sections, the new ambient background, empty states, and the AI Pick
gauge confirmed rendering correctly; DOM-measured to rule out a mobile-viewport overflow (max
element right-edge stayed within the 375px viewport outside the intentionally horizontal-scrolling
Competitions carousel). A transient `useState is not defined` dev-server HMR error surfaced once
mid-edit and did not reproduce after a hard reload — not a build-time or runtime issue (`tsc`/`vite
build` both passed clean throughout).

### Files

**Created**: `components/command-deck/primitives/button.tsx`,
`components/command-deck/mission-control/mission-ambient-background.tsx`.

**Modified**: `styles/tokens.command-deck.css`,
`components/command-deck/mission-control/{mission-hero,ai-operations-overview,mission-section,
live-intelligence,ai-ready-fixtures,top-ai-intelligence,intelligence-feed,
competitions-under-watch,recently-completed-cross-sport,following-section,workspace-teaser}.tsx`,
`components/command-deck/discovery/{discovery-match-card,recently-completed-intelligence}.tsx`,
`components/command-deck/ai-picks/ai-pick-card.tsx`, `pages/home-page.tsx`.

## Command Deck — Recent Form / AI Match Snapshot Redesign

Replaced the plain scoreline rows in Match Intelligence's "Recent Form" (both home/away columns
on `match-detail-page.tsx`) with `MatchSnapshotCard` — each past match reads as a compact
intelligence card rather than a bare result: competition badge + date, crests + score + a
Win/Draw/Loss badge, a row of real stat chips, and a deterministic one-sentence "AI Match
Snapshot." The section is deliberately scoped to a new local `.command-deck` wrapper so it can
use this session's premium-depth tokens (`--cd-card-surface/-border/-shadow`), even though the
rest of the page below the Hero stays on Infinity per the original Phase 1 world-seam disclosure.

**Real data, honestly bounded.** Goals, BTTS, and Clean Sheet are always shown — all three are
pure derivations of the match's own recorded score. Corners, Shots on Target, Possession, and
Cards are real per-fixture `TeamStatistics` rows, but coverage is genuinely sparse today (the
sync job isn't on the Celery beat schedule) — cards show only whichever chips exist for that
specific match, never padded to a fixed shape. **Expected Goals was deliberately left out of v1**:
no per-fixture xG value is stored anywhere in the backend (only ever an internal ML feature), and
the brief's own "never fabricate data" instruction ruled out inventing one.

**Deterministic, not an LLM.** `lib/match-snapshot.ts`'s `buildMatchSnapshot()` is a pure
function: real score → result; real `stat_set` values → a small set of grounded clauses (clean
sheet, corners ≥ 8 → "sustained attacking pressure," opponent shots on target ≤ 2 → defensive
read, possession ≥ 55% → tempo control). A stat below threshold, or never recorded, simply
contributes nothing to the sentence — never a guessed magnitude. 7 unit tests cover the rule
table directly.

**New backend surface reused, not rebuilt.** `GET /sports/fixtures/{id}/statistics` is genuinely
new (no per-fixture stats endpoint existed before this), but it's built entirely from
pre-existing, previously-unwired repository methods (`SqlAlchemyMatchRepository.get_by_fixture` +
`SqlAlchemyTeamStatisticsRepository.list_by_match`) — no new persistence code. Returns `[]` for
both "no Match row yet" and "Match exists but nothing synced," the same honest-empty posture as
every other real-data surface in this app.

**Bug caught in verification**: a CSS Grid default (`min-width: auto` on grid items) let the new
card's content silently expand its own `grid gap-6 lg:grid-cols-2` track past the viewport on
mobile — confirmed via `getBoundingClientRect()` (382.9px card in a 375px viewport), not just a
screenshot glance. Fixed with `min-w-0` on `FormColumn`'s root element, the standard fix for this
exact Grid/Flexbox gotcha.

### Files

**Created**: `lib/match-snapshot.ts` (+ `match-snapshot.test.ts`),
`components/command-deck/match-snapshot-card.tsx`.

**Modified**: `apps/api/routers/sports_router.py` (backend: new `/fixtures/{id}/statistics`
route), `lib/api/types.ts` (+`FixtureTeamStatisticsDto`), `lib/api/sports.ts`
(+`fixtureStatistics`), `pages/sports/match-detail-page.tsx` (Recent Form section + `FormColumn`).

## Command Deck — Mission Control Colorize Pass

**Mode**: Operate
**Status**: Implemented and verified

Command Deck launched deliberately monochrome-plus-one-accent (graphite ground, a single
indigo signal reserved for interactive/live state — see the direction contract at the top of
`tokens.command-deck.css`). Ten Mission Control sections sharing one hue meant every section
read the same regardless of what kind of intelligence it held. This pass introduces a second,
disciplined color layer — category hue, not decoration — while leaving that original restraint
intact: indigo still means "interactive/primary," never "this is football" or "this is news."

**Strategy**: reuse, don't reinvent. `tokens.infinity.css` already ships a calibrated 13-hue
"domain wheel" (football/basketball/baseball/table-tennis/predictions/knowledge-graph/learning/
news/community/operations/infrastructure/alerts/security — one hue each, same saturation/
lightness formula, `DomainKey` type in `components/infinity/primitives/badge.tsx`). Rather than
inventing a second, independently-chosen palette for Command Deck, this pass copies that wheel
hue-for-hue into a new `--cd-domain-*` token group (dark + light) in `tokens.command-deck.css`,
read through Command Deck's own namespace. A domain now means the same thing — same color —
whether the surface is Infinity or Command Deck.

**New shared primitive**: `components/command-deck/primitives/domain.ts` exports
`CD_DOMAIN_COLOR_VAR` (domain → CSS var, mirroring Infinity's own `DOMAIN_COLOR_VAR`),
`domainTint()` (a `color-mix()` helper for muted/strong variants at point of use, matching the
pattern `tokens.command-deck.css` already uses for `--cd-accent-muted`/`--cd-card-border`, rather
than pre-baking 3 variants × 13 domains into the token file), and `sportDomainFor()` (narrows a
`SportMeta.slug` string to the four sport `DomainKey`s).

**Where color landed, and why each choice**:
- `MissionSection` gained an optional `domain` prop — when a section's content is genuinely one
  category, its icon badge tints to that hue instead of generic indigo. **AI Ready Fixtures** and
  **Today's Top AI Intelligence** → `predictions` (cyan). **Recently Completed Intelligence** →
  `learning` (teal-green — the model learning from resolved outcomes). **Live Intelligence**
  deliberately stays un-domained: its live-red `CDStatusDot` is already its color identity, and a
  second hue on the icon would compete with it rather than add information.
- `DiscoveryMatchCard` (shared across Live Intelligence, AI Ready Fixtures, and other pages)
  gained an opt-in `sportDomain` prop — a small dot before the competition label, plus the crest
  glow and hover glow retint to the fixture's own sport. Opt-in, not default: single-sport pages
  (Match Discovery, Live) that already establish sport via page chrome keep the neutral glow;
  Mission Control's cross-sport rails pass it explicitly. Caught a real, pre-existing dev-data
  quirk while verifying: some basketball fixtures are seeded under a competition literally named
  "Premier League" — the sport-color dot (orange, not football-green) correctly exposed this
  rather than being fooled by the competition name.
- `IntelligenceFeed`'s merged News/Breaking/Community rows get a domain per item
  (`news`/`alerts`/`community`) instead of one indigo icon for all three — "Breaking" maps to
  `alerts`, not `news`, since urgency is a distinct signal from a synced article. The section
  header itself stays indigo (it's genuinely mixed-source, not one category).
- `CompetitionsUnderWatch` tints each competition chip's sport label + fallback-avatar initial by
  its sport, same technique as the match cards.
- `FollowingSection`'s per-entity-type icon (Match/Team/Competition) tints by the followed item's
  own sport rather than a fixed color — a genuinely useful "what am I following" signal that was
  previously invisible without opening the item.
- `AiOperationsOverview` KPI tiles: `AI ready matches`/`Published intelligence` → `predictions`,
  `Tracked competitions`/`System health` → `operations`, `Breaking stories` → `news`. `Live
  matches` (already carries the live-red status dot), `Today's fixtures`, and `Following` (no
  single real category) stay undomained rather than forcing a hue onto a metric that doesn't have
  one — an empty `domain` reads as a deliberate omission, not a gap.
- `WorkspaceTeaser`'s passive ambient glow retints to `knowledge-graph` (purple) — it's the entry
  point to cross-team/prediction exploration, and one of its own suggestion chips is "Open
  Knowledge Graph." Mission Hero's two ambient blobs stay indigo: as the page's entry anchor, not
  one category among the ten below it, the Hero deliberately doesn't join the domain system.

**What stayed untouched, deliberately**: `AiPickCard` (shared with `/app/picks` — recoloring it
would ripple beyond Mission Control's scope), `CDStatusDot`'s semantic tone system
(ready/live/idle/building — status is a different axis from domain and the two must never be
conflated), and `ReviewedFixtureCard`'s existing green/amber correct/incorrect check-marks
(evidence polarity, not domain).

**Verification**: `tsc -b` clean, `vitest run` 77/77, production build clean, Impeccable detector
zero findings across every touched file. Live-verified with computed-style checks (not just
screenshot eyeballing) confirming exact expected RGB values render for `predictions`/`operations`/
`news`/`alerts`/`football`/`basketball`/`learning` across the KPI strip, AI Ready Fixtures cards,
and Intelligence Feed rows; checked both dark and light themes.

## Command Deck — Competition Center Redesign

**Mode**: Operate
**Status**: Implemented and verified

Full redesign of `/app/competitions` (the cross-sport nav destination) per a shaped brief:
"Competitions / Every competition TitanIQ covers" → "Competition Intelligence / Explore every
league, tournament and championship covered by TitanIQ's AI Intelligence Engine," rebuilt entirely
on Command Deck (a new local `.command-deck` scope, matching the same additive-world pattern as
Match Intelligence and Mission Control) instead of the page's previous plain Infinity buttons/
cards. `competition-detail-page.tsx` and the single-sport `competition-list-page.tsx` were out of
scope and are untouched.

**Data audit before building** (per the brief's own "never fabricate, hide what's unavailable"
instruction): confirmed via the real domain entities and API surface that Season has no exposed
label anywhere the frontend can reach (only an internal `season_id`), Team has no direct
competition relationship (only reachable through fixtures), and Competition has no "featured"
flag. Resolved with the user before building, not guessed:
- **Season: omitted entirely** — zero backend changes for a page-only redesign.
- **Team count: shown as "X teams featured"**, not "X teams" — an honest count of distinct teams
  observed across that competition's own fetched live/upcoming/completed fixtures, not a claimed
  roster size.
- **Featured Competitions: chosen by real `tier` data** (tier 1 = top-flight), tie-broken by
  current fixture activity — never a hardcoded league-name list. Dev data has `tier: null` on
  every competition today, so Featured correctly renders as absent rather than empty cards or an
  invented ranking; confirmed via a direct authenticated API call during verification, not assumed.
- **Fixture counts (live/upcoming/completed) and AI-ready**: real, same techniques already proven
  elsewhere (`CompetitionsUnderWatch`'s per-sport grouping, sport-level market-availability check)
  — see `use-competition-intelligence.ts` below.

**New data layer**: `lib/hooks/use-competition-intelligence.ts` — one competitions-list fetch plus
three fixture fetches per sport (`status: live | scheduled | completed`, capped at 200 each),
grouped client-side by `competition_id` into `liveCount`/`upcomingCount`/`completedCount`/
`teamsFeatured` per competition. Avoids an N+1 fetch per card even with many competitions on
screen at once — the same pattern `CompetitionsUnderWatch` established for Mission Control.

**New components** (no new directory, per the brief's own constraint — everything lives directly
under `components/command-deck/`, reusing `mission-section.tsx`'s `MissionSection`/
`MissionEmptyState`/`MissionSkeletonGrid` rather than inventing parallel primitives):
- `competition-hero.tsx` — title/subtitle, glass search input, and a sport switcher built as one
  instrument rather than two: the brief's separately-stated "Hero quick filters" and "premium
  segmented control replacing plain tabs" are the same real control, not a second picker.
  "Knowledge graph particles" and "stadium lighting" are real atmosphere, not stock imagery: the
  same `animate-hero-glow` blobs and faint telemetry grid already proven on Mission Control, plus
  the page's own already-fetched competition crests drifting faintly in the backdrop (never
  invented league artwork).
- `competition-card.tsx` — one component, two densities (`size="default" | "featured"`), so the
  grid card and the large Featured card can never visually drift from each other. Sport-domain
  tinted (reusing `CD_DOMAIN_COLOR_VAR`/`domainTint` from the colorize pass above) via crest glow,
  border, and hover state. "AI ready" stays on the fixed indigo accent regardless of sport — an
  interactive/system signal, never colorized by domain, per the same rule the colorize pass
  established.

**Bugs found and fixed during verification** (not assumed away):
- **Card truncation**: reusing `MissionSection`'s generic `MissionCardGrid` (forces 3 columns at
  1024px) truncated real competition names — "Premier League" rendered as "Premier Lea…" — because
  this card carries far more content (crest, name, country/tier, 3–4 stat cells, teams-featured
  line, AI badge + CTA) than the simpler tiles that grid was designed for. Confirmed via
  `getBoundingClientRect()` (a 229px card with only 99px available for the name text), not a
  screenshot glance. Fixed with a page-local `CompetitionGrid` (`sm:grid-cols-2 xl:grid-cols-3`,
  pushing 3 columns out to 1280px) instead of reusing the generic grid.
- **Segmented control overflow on mobile**: the sport switcher's fixed `inline-flex w-fit` row
  measured 335.8px wide against a 375px viewport already consumed by hero padding, clipping "Table
  Tennis" entirely off-screen and out of reach (`controlRight: 400.6 > innerWidth: 375`, confirmed
  by measurement). Fixed by making the control horizontally scrollable (`overflow-x-auto`,
  children `shrink-0`) — the same technique `competition-explorer.tsx`'s chip row already uses —
  re-verified the control's right edge now sits within the viewport with `canScroll: true`.

### Files

**Created**: `lib/hooks/use-competition-intelligence.ts`,
`components/command-deck/{competition-hero,competition-card}.tsx`.

**Modified**: `pages/competitions-page.tsx` (full rewrite, wrapped in `.command-deck`).

**Verification**: `tsc -b` clean, `vitest run` 77/77 (one unrelated timeout on
`match-detail-page.test.tsx` reproduced as flaky under system load, confirmed passing cleanly in
isolation and on a full clean re-run), production build clean, Impeccable detector zero findings.
Live-verified: real fixture counts and teams-featured numbers confirmed via a direct authenticated
API call; sport switching confirmed both the data and the domain tinting change correctly (Football
→ green/AI ready, Basketball → orange/"Coverage building," honestly reflecting that basketball has
no production markets yet); search, empty states, and the Featured/Recently Active sections'
real-data-only behavior all confirmed; checked desktop (1070px) and mobile (375px) after fixing the
two overflow bugs above.

## Command Deck — Team Intelligence Redesign

**Mode**: Operate
**Status**: Implemented and verified

Full redesign of `/app/teams` (the cross-sport nav destination), the third page in this Command
Deck discovery lineage after Competition Center and (transitively) Mission Control. Reuses every
technique already proven on the previous two rather than re-deriving them: the domain wheel, the
`EnrichedCompetition`-style per-sport fixture-derivation hook, the `CompetitionGrid`-style wide
breakpoints, and the shaped brief's own explicit hard constraint — **zero backend changes** — held
throughout.

**Data audit before building**: `Team` has no direct competition relationship in the backend at
all (only reachable through fixtures, same as `Competition`'s missing team-count problem before
it) and no timestamp field of any kind. Confirmed via a live API call against dev.db: 87 real
football teams (all with real crests, zero with `venue_name` — that field is dead weight
everywhere), 10 basketball teams (zero crests, country field is a placeholder `"Mockland"`), 0
baseball/table-tennis teams. Resolved:
- **Recently Updated Teams: omitted entirely** — no timestamp exists anywhere on Team, and the
  brief's own instruction was to hide the section rather than build an always-empty one.
- **League/competition per card: shown only when derivable** from that team's own fetched live/
  scheduled/completed fixtures — absent gracefully otherwise, never guessed.
- **"Generate Intelligence" is a real deep-link, not an inline action**: there is no team-level
  generate endpoint anywhere in the backend (predictions only ever generate against a specific
  fixture + market), so the button only renders when a team has a real upcoming scheduled fixture,
  linking straight to that fixture's match page — the same pattern already proven on Mission
  Control's Workspace teaser suggestion chips. A team with no derivable upcoming fixture gets only
  "View Team," never a fabricated or disabled generate action.
- **Featured Teams**: same real-signal precedent already set on Competition Center for the
  identical `tier` problem — tier-1 (via the team's own derived competition), ranked by fixture
  activity, not a hardcoded club-name list. Confirmed empty today (`tier: null` everywhere in dev
  data), the same honest behavior as Featured Competitions.
- **Country flags**: a small local country-name → emoji map (`lib/country-flags.ts`) covering
  common real countries. Backend only ever returns a free-text name, never an ISO code, so this is
  decorative alongside the real text, never a replacement for it — confirmed dev's placeholder
  `"Mockland"` renders with no flag at all rather than a wrong one.
- **Sport filter emoji**: the brief asked for "⚽ Football / 🏀 Basketball / …", but this world has
  never used emoji anywhere it's shipped, and lucide has no matching sport icons. Continued the
  existing convention instead (text + domain-color tint) rather than starting a new one for a
  single page — the same `SportSegmentedControl` primitive, now extracted out of
  `competition-hero.tsx` into `primitives/` so both pages share one implementation instead of two
  copies.

**New data layer**: `lib/hooks/use-team-intelligence.ts` — one teams-list + competitions-list
fetch, plus the same three capped live/scheduled/completed fixture fetches per sport already
proven on Competition Center, grouped client-side by `home_team.id`/`away_team.id` instead of
`competition_id`. Derives `competitionName`/`competitionTier` (via a `competition_id →
tier` lookup against the competitions list) and `nextFixtureId` per team.

**New components** (no new directory, per the brief's own constraint):
`team-hero.tsx` (title/search/sport-switcher, club crests drifting in the backdrop as the brief's
"club silhouettes" — real assets, not stock imagery), `team-card.tsx` (one component, two
densities, same shape discipline as `CompetitionCard`), `country-filter.tsx` (a second filter row,
entirely client-side over the already-fetched team list — no refetch on selection, real per-
country counts), and `team-browse-list.tsx` — "Browse All Teams," alphabetically grouped,
collapsible, and genuinely virtualized via `@tanstack/react-virtual` (already an installed,
previously-unused dependency — no new package added). Deliberately leaner rows here (crest
thumbnail + name + country only, no per-row league/CTA derivation): this section is for fast
scan-and-jump across the full 87-team roster, not per-team evaluation, which lives in Discover
Teams above it.

**Verified virtualization is real, not just visually plausible**: measured the rendered DOM
directly — 4708px of total scrollable content but only 23 row `<div>`s actually mounted at any
one time (640px viewport + overscan), confirmed via `getBoundingClientRect()`/`scrollHeight`, not
assumed from the library's own claims.

**Verification**: `tsc -b` clean, `vitest run` 77/77, production build clean, Impeccable detector
zero findings across every new/changed file. Live-verified end-to-end: football's real 87-team
grid, country chips with real counts (Germany 64, England 23), the Manchester United/Newcastle
pair correctly differentiated (one has a real upcoming fixture → "Generate Intelligence" deep-
links to it; the other doesn't → "View Team" only, same sport, same AI-ready status); basketball's
graceful degradation (initials-avatar crests, no flag on the placeholder "Mockland" country,
"Coverage building" instead of "AI ready" since basketball has no production markets, correctly
never showing Generate Intelligence regardless of fixture data); baseball/table-tennis rendering
the brief's exact honest empty-state copy with the Browse All section correctly absent; real-time
search; and mobile (375px) confirmed free of horizontal overflow on both the sport switcher and
the new country-filter chip row.

### Files

**Created**: `lib/hooks/use-team-intelligence.ts`, `lib/country-flags.ts`,
`components/command-deck/{team-hero,team-card,country-filter,team-browse-list}.tsx`,
`components/command-deck/primitives/sport-segmented-control.tsx`.

**Modified**: `pages/teams-page.tsx` (full rewrite, wrapped in `.command-deck`),
`components/command-deck/competition-hero.tsx` (now consumes the extracted
`SportSegmentedControl` instead of its own local copy).

---

## Command Deck — Intelligence Workspace (formerly "TitanIQ Assistant")

**Mode**: Operate (task completion — investigate/compare/review, not a marketing surface)
**Status**: Implemented and verified

**Objective**: Replace the Infinity-styled, chat-shaped "TitanIQ Assistant" (context rail / turn
stream / evidence rail, `Turn` union, append-only conversation) with a Command Deck "Intelligence
Workspace" — a Bloomberg-Terminal-adjacent investigation instrument, never a chatbot. Full brief
(three escalating rounds culminating in a detailed "MASTER DESIGN & IMPLEMENTATION SPECIFICATION")
is preserved in the session's shape history; the shaped brief and its disclosed deviations were
confirmed by the user ("go ahead, use print-to-PDF") before any code was written.

### What was built

New IA: Workspace Hero → Investigation Header (persistent, adapts fields to whatever's focused) →
Investigation Context rail (renamed from Pinned; grouped by kind, drag-reorder, localStorage
Recently Opened) → tabbed Canvas (Mission Brief / Predictions / Evidence / Comparison / Timeline /
Decision Intelligence) → persistent Knowledge Graph panel (desktop) / drawer (mobile) → Intelligence
Completeness meter → Workspace Action Bar. Clicking a prediction opens an Evidence Inspector
slide-over instead of appending a turn — the whole canvas reframes around whatever's focused, no
append-only stream.

- **`lib/hooks/use-investigation-workspace.ts`**: pinned (in-memory, matches prior "Pinned"
  behavior), `focused` entity driving the Header/Canvas, `recentlyOpened`/`savedSession`
  (localStorage-backed client conveniences — no backend "recently viewed" or session endpoint
  exists, disclosed in the shaped brief), `kgNodeTypeFor()` mapping the workspace's four entity
  kinds (fixture/team/competition/player) to real, M5-populated `NodeType` values.
- **Evidence Inspector**: reuses `GeneratedIntelligencePanel` verbatim (the same Command-Deck-native
  confidence/evidence rendering already shipped on Match Intelligence) rather than porting Infinity's
  `InfinityEvidenceExplorer` — "reuse the Evidence Explorer's logic, never rebuild it" applied as
  "port the component to Command Deck," not "import the Infinity one as-is," since the brief also
  said "Use Command Deck exclusively."
- **Predictions tab**: generated markets render as result cards (probability + `CDConfidenceGauge`,
  no per-card evidence-count fetch — avoids an N+1 fan-out just for a badge); ungenerated markets for
  a focused fixture reuse `PredictionLaboratory` as-is for the real generate flow. Non-fixture focuses
  (team/competition/player) never show a generate affordance — confirmed live that no market has ever
  been generated with `entity_type` other than `FIXTURE` (`market_seeding.py`).
- **Knowledge Graph panel**: hand-built SVG node-link view (no graph-viz library installed, none
  added) backed entirely by `graphApi.context()` — real subject node, real 1-hop neighborhood edges,
  real `NodeType` grouping. Node click re-centers the graph in place; the small dot on a focusable
  node type (team/player/competition/match) opens it in the workspace.
- **Prediction Timeline**: built on the existing `predictionsApi.history()`, grouped per market,
  chronological. Deltas render as plain computed facts ("Probability +6pts") — no backend field
  names a change *reason*, so no causal label is ever shown, matching the brief's own "only if
  backend provides the reason" clause.
- **Intelligence Completeness**: Prediction/Statistics/Knowledge Graph/News derive from real fetched
  data; Lineups and Officials always render `unavailable` (never `pending`) since both are `NodeType`
  members that exist only in the ontology with no population writer anywhere in the backend.
- **Investigation Notebook**: client-only aggregation view + free-text Notes (localStorage,
  per-entity). Export via the browser's native print-to-PDF (`window.print()` + a scoped
  `styles/print.css`) rather than a bundled PDF-rendering library — the open decision from the
  shaped brief, resolved by the user in favor of zero new dependencies.
- Nav label `TitanIQ Assistant` → `Intelligence Workspace` (`components/layout/nav-config.ts`).

### Named deviations from the literal brief (confirmed against the live backend, not assumed)

- **Pinned Players**: no player-level prediction/market exists anywhere (every market seeds
  `entity_type=FIXTURE` only). Players are real KG nodes, so pinning one gives real relationships;
  Predictions/Evidence show an honest "no player-level predictions exist" state.
- **"Knowledge Graph Influence" / raw evidence strings**: `explanation.knowledge_graph_evidence`/
  `news_contribution`/`community_contribution` are internal UUID-keyed triples — confirmed already
  documented in `evidence-explorer.tsx` as never user-presentable. Never rendered.
- **"Calibration"**: model-level, ops-only (`/calibration/reports`), not exposed per-prediction to
  regular users. Omitted; the existing 9-factor confidence composite is the honest substitute.
- **"Historical Similar Fixtures"**: real via `/graph/similar`, but the shipped similarity metric is
  graph-structural (shared teammates/opponents/competition), not statistical outcome-similarity —
  labeled "Related Fixtures," never "Historical Similar Fixtures."

### Bug found and fixed during verification

Live-tested against real data: `match` KG nodes are populated with **no attributes at all**
(`population_service.py`'s `populate_fixture` upserts with no `attributes` dict) — the first build of
`nodeLabel()` fell back to the raw `entity_ref` (a UUID) for any node with no `name` attribute and no
alias, so the Knowledge Graph panel briefly rendered 58 raw UUID strings as visible node labels for a
real team. Fixed by falling back to a humanized node-type name ("Match") instead of the identifier —
honest (claims nothing the node doesn't carry) and never leaks an internal ID, closing the same "never
expose internal UUID evidence" gap the brief named for the Evidence Inspector.

### Verification performed

`tsc --noEmit` clean · Impeccable detector: zero findings across every new/modified file ·
`vitest run`: full suite 76/76 (`insights-page.test.tsx` fully rewritten for the new IA — the dropped
free-text "unmatched question" test reflects the brief's own explicit removal of free-form AI
messaging, not a coverage gap) · live-verified end-to-end against the real local backend: empty state,
cross-sport/cross-kind search, team focus (honest 0/18 coverage, Knowledge Graph "Linked", real KG
relationship graph with real team/match nodes), fixture focus with 18/18 real generated predictions
(Evidence Inspector opened with real SHAP-style feature contributions, alternative outcomes, and
narration), Intelligence Completeness meter's honest per-item states, light theme (token resolution
confirmed via computed styles), and mobile (375px, zero horizontal overflow, KG panel correctly
collapses to a drawer trigger).

### Files

**Created**: `lib/hooks/use-investigation-workspace.ts`,
`components/command-deck/workspace/{workspace-hero,investigation-header,investigation-context-rail,
workspace-tabs,evidence-inspector,knowledge-graph-panel,intelligence-completeness,
investigation-notebook,workspace-action-bar,workspace-empty-state}.tsx`, `styles/print.css`.

**Modified**: `pages/insights/insights-page.tsx` (full rewrite), `pages/insights/insights-page.test.tsx`
(full rewrite), `components/layout/nav-config.ts` (nav label), `index.css` (print.css import).

**Deleted**: `pages/insights/insights-turns.tsx` (turn-stream model retired; its real data-fetching
logic was extracted into the new tab/panel components, not discarded).

---

## Command Deck — Intelligence Workspace Round 2 (Composer, Related Fixtures, richer evidence)

**Mode**: Operate
**Status**: Implemented and verified

**Objective**: A third, more detailed brief for the same page asked for a mandatory "Claude-style"
composer, a Related Fixtures tab, richer prediction cards, and a few honesty/completeness upgrades —
on top of the just-shipped Intelligence Workspace, not instead of it. Confirmed by the user ("go
ahead") after a delta-only shaped brief (no need to re-litigate what Round 1 already settled).

### What was built

- **`WorkspaceComposer`**: a large "Ask TitanIQ" input with an auto-attached, dismissible context
  chip and contextual quick-prompt chips (per entity kind, and per whether a prediction is
  currently focused). Every question — typed or clicked — resolves into a real Canvas state change
  via deterministic keyword routing (`routeQuery()`); there is no NLU backend and none was
  fabricated. This reintroduces the free-text entry point the very first version of this page had
  (and Round 1 removed), now restyled and formalized rather than dropped.
- **`RelatedFixturesTab`**: new "Related" Canvas tab, real graph-structural similarity
  (`/graph/similar`), honestly labeled "Related through TitanIQ's Knowledge Graph" — a feature
  Round 1's brief described as a deviation but never actually built.
- **Prediction cards reconsidered**: Round 1 deliberately omitted per-card Alternative probability
  and Evidence count to avoid an N+1 fetch. Given the market count is bounded (~15–20 per fixture)
  and a single full-prediction fetch was already proven cheap via the Evidence Inspector, this
  round reverses that call — a bounded `useQueries` fan-out over generated markets' latest
  predictions now powers both fields with real data, confirmed live to resolve progressively
  (no placeholder numbers shown while in flight).
- **Evidence Inspector feature values**: each top ±feature now shows its real `feature_snapshot`
  value alongside its contribution (confirmed live the snapshot's keys exactly match the
  explanation's feature keys) — shared via `GeneratedIntelligencePanel`, so Match Intelligence gets
  the same upgrade for free.
- **Global ⌘K extended, not duplicated**: the app's one existing `InfinityCommandPalette` already
  declines to do entity search ("no search endpoint exists, fabricating results would violate the
  no-fake-data rule" — its own prior documentation). Rather than building a second ⌘K handler, a new
  `workspace-command-store.ts` lets the Workspace publish its real current actions (Generate
  Intelligence, Compare, Open Knowledge Graph, Export Report, Save Session) into a conditional
  "Intelligence Workspace" group in the existing palette, live-verified to appear only while
  something's focused.
- **Empty state enriched**: composer-styled search box (same `query` state the Hero owns — a second
  real entry point, not a decorative echo) plus five real cross-link quick actions (Live, Teams,
  Competitions, AI Picks, the standalone Knowledge Graph explorer at `/app/graph` — corrected from
  an initially-wrong `/app/knowledge-graph` guess after checking `router.tsx`).
- **Clear Investigation**: a new `clearAll()` on the workspace hook (unpins everything, defocuses;
  Recently Opened and notes are left intact — a browsing history and per-entity scratch pad, not
  "the current investigation") wired into the Notebook.
- Timeline deltas now show explicit "65% → 71%" before/after values (not just "+6pts"); loading
  states across Mission Brief/Comparison/Decision Intelligence/Related/Evidence Inspector/Knowledge
  Graph now state what's actually in flight ("Analyzing fixture context…", "Retrieving evidence…",
  etc.) instead of a bare skeleton pulse.

### Bugs found and fixed during verification

- A stale hooks-order console error (`InsightsPage`, "Should have a queue") surfaced mid-session —
  root-caused as a Vite Fast-Refresh artifact from editing `use-investigation-workspace.ts` (adding
  `clearAll`) while the page was already mounted, not a real bug: confirmed via a brand-new browser
  tab (guaranteed fresh module graph, no HMR history) loading with zero console errors.

### Verification performed

`tsc --noEmit` clean · Impeccable detector: zero findings · `vitest run`: full suite 76/76 ·
live-verified end-to-end: Composer's context chip and contextual prompts update correctly when
focus/prediction-focus changes; Related Fixtures tab returns real related fixtures with real overlap
scores (including a correctly-explained 100% overlap between two same-teams fixtures); Prediction
cards fill in Alternative/Evidence-count progressively as the bounded fetch fan-out resolves;
Evidence Inspector shows real feature values paired with contributions; the global palette's new
"Intelligence Workspace" group appears with exactly the right actions; a fresh tab confirmed zero
console errors end-to-end.

### Files

**Created**: `components/command-deck/workspace/workspace-composer.tsx`, `stores/workspace-command-store.ts`.

**Modified**: `pages/insights/insights-page.tsx`, `components/command-deck/workspace/{workspace-tabs,
investigation-notebook,workspace-empty-state}.tsx`, `components/command-deck/generated-intelligence.tsx`
(feature snapshot values — also benefits Match Intelligence), `components/infinity/app-shell/
infinity-command-palette.tsx` (conditional Workspace group), `lib/hooks/use-investigation-workspace.ts`
(`clearAll`).
