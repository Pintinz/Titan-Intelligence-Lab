# TitanIQ Product Context

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Sports fans and analytical followers who want to *understand* a match, not place a bet on it — people who want to know why an outcome is likely, not just what the odds say. Explicitly not bettors: TitanIQ is never positioned as a betting/odds-comparison tool.

## Product Purpose
TitanIQ transforms live sports data, structured intelligence, news, and community signals into explainable sports predictions backed by real evidence. Its job is to help users understand, analyze, predict, learn from, and monitor sports through AI-powered intelligence — never to sell bets.

## Positioning
Every prediction traces to a real, inspectable reason: a confidence breakdown (feature quality/freshness, historical accuracy, model reliability, prediction stability, Knowledge Graph/news/community reliability), ranked feature evidence, and — where available — genuine narration grounded in that same evidence. A tips site or odds aggregator cannot truthfully copy this because it has no underlying explainability pipeline to point to; TitanIQ's mechanism (SHAP-backed feature contributions + a real Knowledge Graph + a calibration/retraining loop on resolved outcomes) is the product, not a marketing claim layered on top of a black box.

## Operating Context
A responsive web app covering four real sports — Football, Basketball, Baseball, Table Tennis — kept sport-agnostic (new sports plug into existing infrastructure, never a redesign). Core workflows: browse live/upcoming/completed matches, generate an AI prediction for a real trained market, review its confidence and evidence, follow teams/competitions/matches/predictions, read AI-curated news/community intelligence, explore the Knowledge Graph, and query a grounded (non-chatbot) Assistant for structured comparisons and explanations.

## Capabilities and Constraints
- Every displayed statistic must come from the real backend — never fabricated, never a plausible-looking placeholder.
- Prohibited vocabulary anywhere in the product: Odds, Stake, Bookmaker, Bet Slip, Value Bet, Edge %, "Best Betting Tips," "Winning Bets," "Bet Now." Use instead: Sports Intelligence, Explainable AI, Evidence-Based Insights, Confidence, Prediction, Risk, Prediction Stability, Model Agreement.
- A prediction display shows Prediction, Confidence, Risk, Prediction Stability, Supporting Factors, Contradicting Factors, Historical Accuracy, Model Agreement — never odds/stake/bookmaker/bet-slip framing.
- The Assistant is explicitly not a chatbot: it explains predictions, summarizes news, compares teams/players, and explores the Knowledge Graph, always grounded in real backend services — never free-form generation.
- Backend evolution is audit → reuse → extend, never a rewrite of working subsystems.

## Brand Commitments
TitanIQ. Core promise: Intelligence (every decision backed by explainable evidence), Premium (world-class, not generic SaaS), Trustworthy (precision and confidence in every interaction), Different (fundamentally not a betting site or score app).

## Evidence on Hand
A real, running ML/explainability pipeline: Feature Store, Feature Registry, Market Registry, Model Registry (CANDIDATE→CHALLENGER→CHAMPION), SHAP-based feature-contribution explainability, a 9-factor Confidence Engine, Platt/Isotonic/Temperature calibration, and a scheduled retraining orchestrator that relearns from real resolved outcomes. A shipped design system (Command Deck + Infinity, documented in `DESIGN.md`) already covers Match Intelligence, Mission Control, AI Picks, and the Ops Center. No user testimonials, press, or case studies exist yet — do not invent any.

## Product Principles
1. Every prediction and every stat shown traces to real backend data — never fabricate a number or a claim.
2. Never read as a betting/gambling product, in vocabulary or in framing — TitanIQ sells understanding, not tips.
3. Backend work extends and reuses existing services; it does not rewrite what already works.
4. Architecture stays sport-agnostic — a new sport plugs into existing infrastructure without a redesign.
5. Visual craft stays premium and distinctive — TitanIQ's own world, never a reskin of Sofascore/FotMob/Flashscore/OneFootball category defaults.

## Product (legacy note)
TitanIQ is a Sports Intelligence Platform that transforms live sports data, structured intelligence, news, and community signals into explainable sports predictions backed by evidence.

## Authentication Surface
The authentication experience (login, signup, password reset) is the first impression users have of TitanIQ. Currently, it's a functional but basic set of forms. This redesign transforms it into a premium, immersive entry point that immediately communicates what TitanIQ is—before users even sign in.

## Core Promise
- **Intelligence**: TitanIQ is fundamentally intelligent. Every decision is backed by explainable evidence.
- **Premium**: The experience feels world-class, not generic SaaS.
- **Trustworthy**: Precision and confidence in every interaction.
- **Different**: TitanIQ is fundamentally different from betting sites and score apps.

## User Goals (Auth Context)
1. Understand what TitanIQ is before committing to signup
2. Feel confident entering their email and password
3. Experience a smooth, premium signup/login flow
4. Easily recover forgotten passwords

## Business Goals
- First impression establishes brand authority
- High visual polish reduces signup friction
- Premium experience increases perceived value
- Differentiate from competitors visually

## Key Insights
- Authentication pages are attention-capturing moments
- Users should see TitanIQ in action during login/signup
- "See Every Match Through Intelligence" is the core value proposition
- The Intelligence Canvas should showcase real TitanIQ capabilities

## Scope: Presentation Layer Only
**Do NOT modify:**
- Backend authentication APIs
- Supabase configuration or contracts
- Authentication business logic
- DTOs or API contracts
- React Router routes or Protected/RoleRoute components
- Authentication services (auth-store.ts, supabase.ts, etc.)
- Form validation schemas or submission handlers

**This redesign touches ONLY:**
- Visual layout and styling (split-screen, responsive)
- Component composition (Intelligence Canvas, Auth Card)
- Animations and micro-interactions
- Typography and color usage
- Error/success messaging presentation

## Success Criteria
1. Desktop users see a 60/40 split (Intelligence Canvas / Auth Card)
2. Tablet users see a 55/45 split
3. Mobile users see single-column layout
4. Intelligence Canvas continuously animates with living data
5. Sport rotation every 8–10 seconds with smooth transitions
6. Auth card feels premium and premium micro-interactions
7. Form morphing between login/signup (no navigation)
8. 60 FPS animation performance maintained
9. Accessibility: keyboard nav, screen reader, ARIA, reduced motion
10. All existing authentication flows work exactly as they do today

## Design Inspiration (Not Copied)
- Bloomberg Terminal: information density with premium feel
- Apple Human Interface Guidelines: precision and elegance
- Formula 1 Live Timing: confidence metrics and telemetry
- TradingView: real-time data presentation
- Linear: modern, premium design system

TitanIQ must establish its own identity inspired by these but distinct.
