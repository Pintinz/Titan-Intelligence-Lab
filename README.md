# TitanIQ

Sports Intelligence Beyond Prediction — Titan Intelligence Labs.

**Status**: Milestone 10 (Enterprise Frontend Platform) complete. TitanIQ now has a real,
running React + TypeScript frontend ([frontend/](frontend/)) over the Milestone 1-9.1 backend —
Prediction/Match/Competition/Team/Player/News/Community/Analytics Centers, a Knowledge Graph
Explorer, RBAC-gated Model/Experiment/Feature/Admin Centers, live Supabase Auth + Realtime, a
full design system/component library, and a PWA build — all a strict presentation layer, with two
small backend additions the frontend genuinely needed (a new read-only `sports_router.py`, and
closing an auth gap on ~41 previously-unauthenticated admin endpoints). Underneath: real,
calibrated, confidence-scored, explainable predictions across Football, Basketball, Baseball, and
Table Tennis — a data-driven Market Registry, Feature-to-Market mapping, Champion/Challenger
Model Registry, real LightGBM/XGBoost/CatBoost/scikit-learn predictors (Automatic Model
Selection, Ensemble Learning, SHAP explainability) behind the same `PredictorPort` the original
weighted statistical predictors still serve as fallback (never an LLM), Probability Calibration
(Platt/Isotonic/Temperature Scaling), a 9-factor Confidence Engine, and an Explainability Engine
composing the Knowledge Graph (Milestone 7) and News/Community Intelligence (Milestone 8)
retrieval layers plus Gemini's narration — all under [backend/](backend/), against a real
provisioned Supabase project (`titaniq`). 1,357 fast backend tests passing
(SQLite/fakeredis/MockJWTValidator), 97%+ line coverage across every backend module; 68 frontend
tests (component/store/route/a11y) + 6 Playwright e2e tests, ~16% frontend line coverage (see
the Milestone 10 STOP-GATE for the honest breakdown — nowhere near the 95% target on a
from-scratch ~90-file frontend built in one milestone). See [docs/roadmap.md](docs/roadmap.md)
for the full milestone-by-milestone history and what's next,
[docs/frontend_architecture.md](docs/frontend_architecture.md) for the frontend itself,
[docs/prediction_engine.md](docs/prediction_engine.md)/[docs/machine_learning.md](docs/machine_learning.md)
for the Prediction Intelligence & ML Platform, [docs/supabase.md](docs/supabase.md) for the
live project's configuration, and [docs/database_schema.md](docs/database_schema.md) §11 for
the Entity Expansion Matrix.

## Start Here

- [docs/titaniq.md](docs/titaniq.md) — product charter: what TitanIQ is, mission, sports, providers
- [docs/architecture.md](docs/architecture.md) — system architecture, layering, patterns, tech stack
- [docs/database_schema.md](docs/database_schema.md) — schema design
- [docs/feature_catalog.md](docs/feature_catalog.md) — Feature Intelligence Platform
- [docs/prediction_engine.md](docs/prediction_engine.md) — Prediction Intelligence Platform (pipeline, engines, APIs)
- [docs/machine_learning.md](docs/machine_learning.md) — Enterprise ML Platform (frameworks, ensembles, Automatic Model Selection, SHAP)
- [docs/training_pipeline.md](docs/training_pipeline.md) — Dataset & Training Platform
- [docs/model_registry.md](docs/model_registry.md) — extended Model Registry & Model Monitoring
- [docs/experiments.md](docs/experiments.md) — Experiment Tracking
- [docs/calibration.md](docs/calibration.md) — Probability Calibration
- [docs/prediction_markets.md](docs/prediction_markets.md) — Prediction Market Registry
- [docs/knowledge_graph.md](docs/knowledge_graph.md) — Knowledge Graph schema
- [docs/api_specification.md](docs/api_specification.md) — API design and contracts
- [docs/frontend_architecture.md](docs/frontend_architecture.md) — frontend stack, layout, typed API layer, known limitations
- [docs/design_system.md](docs/design_system.md) — design tokens, theming, motion, accessibility floor
- [docs/ui_components.md](docs/ui_components.md) — full component inventory
- [docs/user_flows.md](docs/user_flows.md) — golden paths through the app
- [docs/ui_design_system.md](docs/ui_design_system.md) — original Milestone 8 design-system framework (token names fixed; see design_system.md for the real Milestone 10 values)
- [docs/admin_center.md](docs/admin_center.md) — administration platform
- [docs/security.md](docs/security.md) — security architecture and threat model
- [docs/supabase.md](docs/supabase.md) — live Supabase project configuration
- [docs/authentication.md](docs/authentication.md) — dual-path auth, RBAC, PATs, session/security intelligence
- [docs/rls.md](docs/rls.md) — full per-table Row Level Security policy reference
- [docs/deployment.md](docs/deployment.md) — env vars, running migrations/tests, OAuth dashboard setup
- [docs/roadmap.md](docs/roadmap.md) — 20-milestone delivery plan and Definition of Done
- [docs/decisions.md](docs/decisions.md) — Architecture Decision Records

## Repository Layout

```
backend/
  apps/api/          FastAPI app — providers, health, features, flags, quality, sync, monitoring,
                       graph, intelligence, predictions, markets, admin/predictions, admin/ml, auth,
                       organizations, billing, webhooks
  modules/sports/      Sports bounded context — domain/application/ports/infrastructure
  modules/admin/         Provider Management, Health Intelligence, Feature Flags
  modules/features/       Feature Intelligence Platform — registration, lineage, store, quality
  modules/ingestion/       Sports Data Ingestion Engine — validation, quality, reconciliation,
                             sync orchestration, feature pipeline + real calculators, Redis, Celery
  modules/knowledge_graph/  Knowledge Graph — Graph Query Engine, Entity Resolution, Similarity,
                             Semantic Search, Context Engine, Temporal Graph, RAG retrieval — Milestone 7
  modules/intelligence/    News/Community Intelligence Platform, Gemini text-intelligence adapters — Milestone 8
  modules/predictions/       Prediction Intelligence Platform — Market/Model/Feature-to-Market
                               registries, Prediction Engine, Confidence/Explainability Engines,
                               per-sport market seeding — Milestone 9; extended with the Enterprise
                               ML Platform (framework adapters, ensembles, Dataset/Training
                               Platform, Automatic Model Selection, SHAP, Model Monitoring/Serving)
                               under infrastructure/ml/, infrastructure/monitoring/ — Milestone 9.1
  modules/identity/         RBAC, federated auth, PATs, sessions, security/audit — Milestone 6
  modules/tenancy/           Organizations, Teams, Memberships, Invitations — Milestone 6
  modules/billing/            Plans, Entitlements, Subscriptions, Usage Counters — Milestone 6
  modules/webhooks/            Endpoint registration + delivery ledger — Milestone 6
  apps/api/routers/sports_router.py   Sports reference-data read API (competitions/teams/
                                        players/fixtures) — new in Milestone 10, see §2f
  alembic/                  0001 sports, 0002 admin, 0003 flags, 0004 features, 0005 quality,
                             0006 sports versioning/Country/Lineup, 0007 ingestion,
                             0008 knowledge_graph, 0009 identity/tenancy/billing/webhooks schema,
                             0010-0011 RLS, 0012 schema grants, 0013 storage, 0014 realtime,
                             0015-0016 KG ontology/indexes, 0017 intelligence platform,
                             0018 predictions platform, 0019 predictions realtime,
                             0020 predictions/intelligence grants, 0021-0022 predictions/intelligence RLS,
                             0023 ML platform schema, 0024 ML platform RLS — all applied live
  tests/unit/                 fast pytest suite (1,357 tests, SQLite/fakeredis/MockJWTValidator)
  tests/integration/           live-Supabase suite — skips without live credentials
frontend/          React 19 + TypeScript + Vite — Milestone 10, see docs/frontend_architecture.md
  src/components/ui/            Foundational Radix-based primitives
  src/components/domain/         TitanIQ-specific composites (PredictionCard, MatchCard, …)
  src/components/layout/          AppShell, Sidebar, Topbar, MobileNav
  src/pages/                       One file per route, grouped by domain
  src/lib/api/                      Typed client — one module per backend router
  src/stores/                        Zustand: auth, theme, toast, command-palette, active-org
  e2e/                                 Playwright golden-path smoke tests
docs/               Living documentation
infra/               Docker, deployment configs — not started
```

`backend/modules/sports/`, `modules/admin/`, `modules/features/`, `modules/ingestion/`,
`modules/knowledge_graph/`, `modules/intelligence/`, `modules/predictions/`, `modules/identity/`,
`modules/tenancy/`, `modules/billing/`, and `modules/webhooks/` all follow the layering in
[docs/architecture.md](docs/architecture.md) §3:

```
domain/            entities.py, value_objects.py, (sports: contracts/) — zero framework imports
application/         orchestration services — registration/lifecycle workflows, engines, registries
ports/                abstract interfaces — repositories, provider/online-store gateways, vault
infrastructure/        persistence/ (SQLAlchemy), providers/online/cache/celery/ (mock + real adapters)
football/ basketball/ baseball/ table_tennis/    sport plugins (provider-agnostic structure)
```

`infra/` remains unimplemented — see [docs/roadmap.md](docs/roadmap.md) for what each future
milestone adds. `frontend/` is live as of Milestone 10 (see above and
[docs/frontend_architecture.md](docs/frontend_architecture.md)).

## Working Agreement

Every milestone follows the Definition of Done in [docs/roadmap.md](docs/roadmap.md): tests,
updated docs, an ADR for non-trivial decisions, and explicit approval before the next milestone
begins.
