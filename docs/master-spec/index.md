# TitanIQ — Master AI/ML Architecture Specification

**Status**: Complete (21 documents, 6 milestones). Written as a standalone, from-scratch
architecture specification for TitanIQ's AI Sports Intelligence platform, covering Football,
Basketball, Baseball, and Tennis.

## Read this first

**This is a target-state / pitch-grade spec artifact, not a description of what is currently
deployed.** TitanIQ's `backend/` already has a mature, working implementation of nearly everything
specified here — a real Feature Store (online Redis + offline Postgres), a real Feature Registry
with a DRAFT→ACTIVE lifecycle, a real Market Registry with `FeatureMarketMapping`, a real Model
Registry with CANDIDATE→CHALLENGER→CHAMPION promotion, real SHAP explainability, real
Platt/Isotonic/Temperature calibration — documented in real depth in the living `docs/` tree
(`architecture.md`, `machine_learning.md`, `training_pipeline.md`, `model_registry.md`,
`calibration.md`, `feature_catalog.md`, `prediction_engine.md`, `prediction_markets.md`,
`database_schema.md`, `api_specification.md`, `security.md`, `deployment.md`, `experiments.md`),
matching real code and referencing real milestones/ADRs.

This document set was written anyway, deliberately, as a separate artifact — grounded in the real
tech stack and module conventions this codebase already uses, but authored fresh against a specific
brief rather than copied from the living docs. It's expected to diverge from and partially duplicate
what already exists; that tradeoff was made explicitly by the person who commissioned it, not by
accident. Read it as "here is the full spec as asked for," not as "here is what TitanIQ does today."

## Contents

### Milestone 1 — Foundational Architecture
1. [System Architecture](01-system-architecture.md) — vision, high-level architecture diagram, guiding principles, sport-plugin boundary, data flow, component inventory
2. [ML Architecture](02-ml-architecture.md) — baseline+ML two-tier strategy, `PredictionModel` interface, frameworks, ensembling, explainability, confidence, calibration
3. [Data Engineering Architecture](03-data-engineering-architecture.md) — the Feature Engineering Pipeline, stage by stage, and its reuse contract between Prediction and Training
4. [MLOps Architecture](04-mlops-architecture.md) — model lifecycle state machine, Champion/Challenger promotion policy, automatic retraining trigger flow, deployment modes

### Milestone 2 — Structural Blueprints
5. [FastAPI Folder Structure](05-fastapi-folder-structure.md) — hexagonal module layout, the composition root, testing convention
6. [PostgreSQL Schema](06-postgresql-schema.md) — schema-per-domain conventions, cross-cutting columns, RLS, migrations
7. [Raw Data Schema](07-raw-data-schema.md) — full DDL for the `raw` schema across all entity types

### Milestone 3 — Registries & Feature Store
8. [Feature Store Schema](08-feature-store-schema.md) — dual-backed offline/online design, table DDL, read/write API
9. [Feature Registry Schema](09-feature-registry-schema.md) — feature definitions, lifecycle, ownership
10. [Market Registry Schema](10-market-registry-schema.md) — market definitions, feature-market mappings, lifecycle
11. [Model Registry Schema](11-model-registry-schema.md) — model definitions, training runs, dataset versions, the database-enforced single-Champion invariant

### Milestone 4 — Pipelines & API Contracts
12. [Training Pipeline](12-training-pipeline.md) — full sequence, split strategy, sample guards, HPO
13. [Prediction Pipeline](13-prediction-pipeline.md) — full request-path sequence, prediction history schema, latency budget
14. [Automatic Retraining](14-automatic-retraining.md) — fixture-finish trigger, drift/staleness policy, rolling-window rationale
15. [API Contracts](15-api-contracts.md) — concrete request/response shapes for prediction, training, and all three registries

### Milestone 5 — Sport Prediction Engines
16. [Sport Prediction Engines](16-sport-prediction-engines.md) — Football, Basketball, Baseball, Tennis: baseline + ML + full market catalog per sport

### Milestone 6 — Operational Strategy
17. [Deployment Strategy](17-deployment-strategy.md) — deployment units, the app-deploy/model-deploy split, release pipeline, environments
18. [Monitoring Strategy](18-monitoring-strategy.md) — the three observability pillars, what's watched, alerting, dashboards
19. [Scaling Strategy](19-scaling-strategy.md) — statelessness precondition, per-tier scaling, inference scale, backpressure, capacity planning
20. [Security Strategy](20-security-strategy.md) — authn/authz, secrets, input validation, model artifact security, audit logging
21. [Testing Strategy](21-testing-strategy.md) — test pyramid, ML-specific test classes, integration tier, CI gates

## Cross-Reference Consistency

Terminology is held consistent across all 21 documents:

- **Feature lifecycle**: `DRAFT → IN_REVIEW → ACTIVE → DEPRECATED → REMOVED` (§9)
- **Market lifecycle**: `DRAFT → IN_REVIEW → APPROVED → PRODUCTION → DEPRECATED → ARCHIVED → REMOVED` (§10)
- **Model lifecycle**: `CANDIDATE → CHALLENGER → CHAMPION → RETIRED` (§4, §11)
- **Identifiers**: `market_key`, `feature_key`, `model_id`, `sport_code` are used with the same
  meaning everywhere they appear, never redefined between documents.
- **Schema ownership**: `raw` → ingestion; `features` → Feature Store + Registry; `markets` →
  Market Registry; `models` → Model Registry + Training; `predictions` → Prediction Service (§6).
