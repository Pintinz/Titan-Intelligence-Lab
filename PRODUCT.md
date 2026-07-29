# TitanIQ Product Context

## Product
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
