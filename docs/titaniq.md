# TitanIQ — Product Charter

**Company:** Titan Intelligence Labs
**Product:** TitanIQ
**Codename:** Project Titan
**Tagline:** Sports Intelligence Beyond Prediction
**Status:** Foundation phase — no milestones started
**Owner:** ealbright82@gmail.com

## 1. What TitanIQ Is

TitanIQ is an AI Sports Intelligence platform, not a betting-odds site. It converts structured
sports data, historical performance, live match events, engineered statistics, contextual
intelligence, AI-extracted news, and community signals into **explainable** sports intelligence.
Predictions are one output of that intelligence, not the product itself.

Two properties distinguish TitanIQ from a typical prediction site:

1. **It gets smarter after every event.** The Outcome Learning Engine compares every prediction
   against the official result and feeds that error signal back into feature reliability, model
   monitoring, and retraining decisions.
2. **Every output is explainable.** No prediction, ranking, or recommendation ships without
   supporting evidence, feature attribution (SHAP), and a stated confidence/risk level.

## 2. Who It's For (funded-team scale)

TitanIQ is being built for real production scale from the start: multi-tenant SaaS, millions of
users, enterprise reliability targets (see [architecture.md](architecture.md) §9 for concrete
SLOs). This means early milestones still go through proper review, testing, and observability —
"funded team" changes the *target scale*, not the *engineering bar*.

## 3. Supported Sports

| Phase | Sports |
|---|---|
| Phase One (Milestones 1–12) | Football, Basketball, Baseball, Table Tennis |
| Future Expansion | Tennis, Cricket, Formula One, American Football, Ice Hockey, Volleyball, Rugby, MMA, Boxing, Esports |

The domain layer must never hard-code assumptions that block adding a new sport — see
[architecture.md](architecture.md) §4 (Sport Plugin Boundary).

## 4. Product Philosophy

- Predictions are outputs of intelligence, not the objective.
- AI augments statistical reasoning; it does not replace it.
- Every prediction ships with confidence, explainability, supporting evidence, and context.
- Intelligence compounds through measurable, monitored learning — not ad-hoc retraining.

## 5. Independent AI Subsystems

TitanIQ is deliberately **not** one monolithic model. Each subsystem below is independently
testable, observable, and replaceable (interfaces defined in [architecture.md](architecture.md) §6):

Sports Intelligence Engine · Historical Intelligence Engine · Live Intelligence Engine ·
Feature Intelligence Platform · Knowledge Graph · Prediction Intelligence Platform ·
Outcome Learning Engine · AutoML Engine · Feature Store · Recommendation Engine ·
Analytics Engine · Confidence Engine · Explainability Engine · AI Assistant ·
Natural Language Intelligence

## 6. Data Providers (initial)

| Provider | Purpose | Key status |
|---|---|---|
| API-Football | Football data | Held by user — confirm scope in Milestone 3 |
| API-Basketball | Basketball data | Held by user — confirm scope in Milestone 3 |
| API-Baseball | Baseball data | Held by user — confirm scope in Milestone 3 |
| API-Tennis | Tennis data (future expansion) | Held by user — confirm scope in Milestone 3 |
| Google Gemini | News extraction, NL intelligence | Held by user — confirm scope in Milestone 3 |
| Table Tennis provider | TBD — no confirmed provider yet | **Open item**, resolve in Milestone 3 |

No provider payload may cross the Infrastructure Layer boundary — see
[architecture.md](architecture.md) §5 (Provider Adapter Pattern).

## 7. Monetization

Free tier (limited AI usage) → Rewarded-ad unlock (Google Rewarded Ads) → Premium subscription
(unlimited predictions/analysis, priority processing, ad-free) → Enterprise plans. All ad and
payment integrations must comply with Google policy and are scoped to their own milestone —
see [roadmap.md](roadmap.md).

## 8. Living Documents

This charter is the entry point. The authoritative detail lives in:

- [architecture.md](architecture.md) — system architecture, patterns, module boundaries
- [database_schema.md](database_schema.md) — schema design and evolution
- [feature_catalog.md](feature_catalog.md) — Feature Intelligence Platform
- [prediction_markets.md](prediction_markets.md) — Prediction Market Registry
- [knowledge_graph.md](knowledge_graph.md) — Knowledge Graph schema
- [api_specification.md](api_specification.md) — API design and contracts
- [ui_design_system.md](ui_design_system.md) — design tokens and component library
- [admin_center.md](admin_center.md) — administration platform
- [security.md](security.md) — security architecture and threat model
- [roadmap.md](roadmap.md) — 20-milestone delivery plan
- [decisions.md](decisions.md) — Architecture Decision Records

All must stay synchronized with implementation. A milestone is not "done" until its docs are
updated (see the Definition of Done in [roadmap.md](roadmap.md)).
