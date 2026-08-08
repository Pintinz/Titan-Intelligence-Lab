# 05 — FastAPI Folder Structure

> Part of the standalone `docs/master-spec/` set — see the notice at the top of
> [`01-system-architecture.md`](01-system-architecture.md). This document specifies the backend
> folder layout the rest of this spec assumes.

## 1. Architectural Style

**Hexagonal / clean architecture, one bounded-context module per business capability.** Every
module is internally organized the same way — `domain/`, `application/`, `infrastructure/`,
`ports/` — so a developer who understands one module already knows how to navigate any other.

```
domain/         Entities, value objects, pure business rules. No I/O, no framework imports.
application/    Services that orchestrate domain logic. Depend on ports, never on infrastructure.
infrastructure/ Concrete implementations of ports: DB models/repositories, ML framework adapters,
                Celery tasks, external API clients.
ports/          Abstract interfaces (Python Protocols) that application/ depends on and
                infrastructure/ implements. This is the seam that keeps the domain framework-free.
```

Dependency direction is strictly inward: `infrastructure` → `ports` ← `application` → `domain`.
`domain` imports nothing from the other three.

## 2. Top-Level Layout

```
backend/
├── apps/
│   ├── api/                       # FastAPI HTTP entrypoint
│   │   ├── main.py                # App instantiation, lifespan, CORS, router registration
│   │   ├── composition.py         # Composition root — see §3
│   │   ├── auth_deps.py           # Auth/role dependency helpers
│   │   └── routers/
│   │       ├── prediction_router.py
│   │       ├── training_router.py
│   │       ├── market_registry_router.py
│   │       ├── feature_registry_router.py
│   │       ├── model_registry_router.py
│   │       ├── feature_store_router.py
│   │       ├── sports_router.py
│   │       └── ...                # one router file per module with an HTTP surface
│   ├── worker/                    # Celery worker entrypoint (imports task modules, starts consumer)
│   └── scheduler/                 # Celery beat entrypoint (imports beat schedule, starts scheduler)
│
├── modules/
│   ├── ingestion/                 # Data Ingestion Service + Feature Engineering Pipeline
│   │   ├── domain/
│   │   ├── application/
│   │   │   ├── feature_pipeline.py
│   │   │   └── windowed_feature_engineering_service.py
│   │   ├── infrastructure/
│   │   │   ├── providers/         # one adapter per external sports data API
│   │   │   ├── persistence/       # raw table models/repositories — see 07-raw-data-schema.md
│   │   │   └── celery/
│   │   └── ports/
│   │
│   ├── features/                  # Feature Store + Feature Registry
│   │   ├── domain/                # FeatureDefinition, FeatureValue entities
│   │   ├── application/
│   │   │   ├── feature_store_service.py
│   │   │   └── feature_registration_service.py
│   │   ├── infrastructure/
│   │   │   ├── persistence/       # offline (Postgres) store
│   │   │   └── cache/             # online (Redis) store
│   │   └── ports/
│   │
│   ├── markets/                   # Market Registry
│   │   ├── domain/                # MarketDefinition, FeatureMarketMapping
│   │   ├── application/market_registry_service.py
│   │   ├── infrastructure/persistence/
│   │   └── ports/
│   │
│   ├── models/                    # Model Registry + Training Service
│   │   ├── domain/                # ModelDefinition, TrainingRun, DatasetVersion
│   │   ├── application/
│   │   │   ├── model_registry_service.py
│   │   │   ├── training_pipeline_service.py
│   │   │   ├── model_selection_service.py
│   │   │   ├── calibration_fitting_service.py
│   │   │   └── scheduled_retraining_orchestrator.py
│   │   ├── infrastructure/
│   │   │   ├── ml/                # LightGBM/XGBoost/CatBoost/sklearn adapters (PredictionModel impls)
│   │   │   ├── calibration/       # Platt/Isotonic/Temperature adapters
│   │   │   ├── artifact_store/    # model artifact persistence (filesystem/object storage)
│   │   │   └── celery/
│   │   └── ports/
│   │
│   ├── predictions/                # Prediction Service
│   │   ├── domain/
│   │   ├── application/
│   │   │   ├── prediction_engine.py
│   │   │   ├── prediction_context_builder.py
│   │   │   ├── confidence_engine.py
│   │   │   └── explainability_engine.py
│   │   ├── infrastructure/
│   │   │   ├── predictors/        # baseline + ML PredictorPort implementations, per sport
│   │   │   └── shap/
│   │   └── ports/
│   │
│   ├── sports/                    # Sport plugin boundary — see 01-system-architecture.md §4
│   │   ├── football/
│   │   │   ├── baseline.py        # Dixon–Coles
│   │   │   ├── feature_calculators.py
│   │   │   └── market_catalog.py
│   │   ├── basketball/
│   │   ├── baseball/
│   │   └── tennis/
│   │
│   └── identity/                  # Auth, tenancy, roles — cross-cutting, not ML-specific
│
├── tests/
│   ├── unit/
│   │   ├── apps/                  # test_api_<module>.py — router-level tests
│   │   └── modules/               # mirrors modules/ 1:1
│   └── integration/                # cross-cutting: DB, auth, real Postgres-tier tests
│
├── alembic/
│   └── versions/                   # one linear migration history, schema-per-module (§ 06)
│
├── scripts/                        # seed/backfill/one-off operational scripts
│
└── pyproject.toml                  # single dependency manifest
```

## 3. The Composition Root

`apps/api/composition.py` is the **only** place that wires `ports` interfaces to concrete
`infrastructure` implementations. It exposes a `build_*()` factory function per service (e.g.
`build_prediction_engine()`, `build_model_registry_service()`), and every router depends on these
factories via FastAPI's `Depends`, never on infrastructure classes directly:

```python
# apps/api/routers/prediction_router.py
@router.post("/predict/{market_key}")
async def predict(
    market_key: str,
    fixture_id: UUID,
    engine: PredictionEngine = Depends(composition.build_prediction_engine),
):
    return await engine.generate(market_key, fixture_id)
```

This is manual dependency injection — no DI framework/container — chosen because it keeps the
wiring graph textually greppable in one file rather than distributed across decorator metadata.

## 4. Testing Convention

`tests/unit/` mirrors `apps/` and `modules/` exactly, one test file per source file
(`modules/predictions/application/prediction_engine.py` → `tests/unit/modules/predictions/test_prediction_engine.py`).
Each module folder under `tests/unit/modules/<module>/` has its own `conftest.py` providing an
in-memory async database engine (schema-scoped) and hand-rolled in-memory repository fakes, so unit
tests never depend on a running Postgres/Redis instance. `tests/integration/` is the only tier that
talks to a real (or containerized) Postgres — used for RLS, auth, and cross-service tests where an
in-memory fake would hide the exact thing being tested.

## 5. What This Document Does Not Cover

Database schema/DDL → [`06-postgresql-schema.md`](06-postgresql-schema.md) and
[`07-raw-data-schema.md`](07-raw-data-schema.md). Endpoint request/response contracts →
[`15-api-contracts.md`](15-api-contracts.md). Deployment packaging of `apps/api`, `apps/worker`,
`apps/scheduler` → [`17-deployment-strategy.md`](17-deployment-strategy.md).
