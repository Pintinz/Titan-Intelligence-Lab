# TitanIQ — API Specification

Status: Design principles defined Milestone 1; concrete endpoints implemented through
Milestone 9.1 (§2a-§2e below). **No external API shall be called directly by frontend clients** —
every provider call is proxied and normalized through the backend (see
[architecture.md](architecture.md) §5).

## 1. Design Principles

- **OpenAPI-first**: Pydantic v2 request/response models are the contract. The OpenAPI document
  is generated from code, never hand-maintained separately, and is what the TypeScript client
  (generated via `openapi-typescript` or equivalent) consumes — contract drift is a build
  failure, not a runtime surprise.
- **Versioned**: all routes under `/api/v1/...`. Breaking changes require a new version prefix,
  never an in-place semantic change to `v1`.
- **Resource-oriented REST** for CRUD-shaped resources (teams, fixtures, users); **RPC-style
  action endpoints** (`/predictions/{market}/evaluate`) where the operation isn't naturally a
  resource. WebSockets reserved for genuinely live data (live match state, real-time odds-style
  intelligence updates) — not used where polling/caching would do.
- **Consistent envelope**: every response uses `{ data, meta, error }` shape; errors use a
  typed `error.code` + `error.message`, never bare HTTP status with no body.
- **Pagination**: cursor-based for all list endpoints from day one (offset pagination is not
  used — it doesn't hold up at the scale targeted in [architecture.md](architecture.md) §9).
- **Idempotency**: all mutating endpoints accept an `Idempotency-Key` header.

## 2. Route Groups (module → route prefix)

| Module | Prefix | Notes |
|---|---|---|
| Identity | `/api/v1/auth`, `/api/v1/users` | delegates to Supabase Auth |
| Sports | `/api/v1/sports`, `/api/v1/competitions`, `/api/v1/teams`, `/api/v1/players`, `/api/v1/fixtures` | read-heavy, cached |
| Features | `/api/v1/features` | mostly internal/admin-facing |
| Predictions | `/api/v1/predictions`, `/api/v1/markets` | includes confidence + explanation payload inline |
| Knowledge Graph | `/api/v1/graph` | relationship/similarity/context/traversal queries — implemented Milestone 7, see §2b |
| Analytics | `/api/v1/analytics` | dashboards, comparative analysis |
| Personalization | `/api/v1/me/preferences`, `/api/v1/me/recommendations` | owner-scoped, RLS-backed |
| Billing | `/api/v1/billing` | subscriptions, ad-unlocks, usage counters |
| Content | `/api/v1/intelligence` | read-only to clients — implemented Milestone 8, see §2c |
| Admin | `/api/v1/admin/*` | role-gated, see [admin_center.md](admin_center.md) |

## 2a. Implemented Endpoints (as of Milestone 5)

Everything below exists in `backend/apps/api/main.py` today, all under `/api/v1/admin/*` (role
gating itself is still deferred — see [security.md](security.md) — these are functionally
correct but not yet auth-protected). All still use the `{data, meta, error}` envelope from §1;
role gating and full RBAC land with real Identity (deferred, see [roadmap.md](roadmap.md)
Milestone 3 notes).

| Area | Endpoints |
|---|---|
| Provider Management (M3) | `providers` list/get/activate/deactivate, `providers/{id}/credentials` |
| Provider Health (M3) | `providers/{id}/health/*`, `providers/{id}/diagnostics`, `credentials/{id}/health` |
| Feature registration (M4) | `features` CRUD, `features/{key}/submit`, `/approve`, `/reject`, `/deprecate` |
| Feature flags (M4) | `flags` CRUD, `flags/{key}/enable`, `/disable`, `/rollout`, `/evaluate` |
| Feature Quality (M4.5) | `features/{key}/quality`, `/validate`, `/validations*`, `/usage`, `/consumers`, `/computation`, `/statistics`, `/health` |
| Sports Data Sync (M5) | `sync/{sport_code}/countries`, `/teams/{competition_ref}`, `/fixtures/{competition_ref}/{season_label}`, `/standings/{competition_ref}/{season_label}` (all POST, trigger a sync run) |
| Sync Monitoring (M5) | `sync/status`, `sync/stats` (GET, read `SyncRun` history) |
| Ingestion Data Quality (M5) | `ingestion/quality/{sport_code}/{entity_kind}` (GET latest `DataQualityReport`) |
| Infra Health (M5) | `monitoring/redis` (GET — ping + latency) |
| Knowledge Graph (M5, population-only, legacy) | `admin/graph/nodes/{node_type}/{entity_ref}` (GET — node + its edges; superseded by the M7 endpoints below for anything beyond a single node lookup) |

## 2b. Knowledge Graph API (Milestone 7 — Sports Semantic Intelligence Platform)

`apps/api/routers/graph_router.py`, prefix `/api/v1/graph`, all GET/read-only, gated at
`get_current_user` (any authenticated user — see [rls.md](rls.md)'s broad-read posture; graph
data is not per-organization/per-user sensitive the way billing or PATs are). Maps 1:1 onto the
eight API categories the constitution names — see [knowledge_graph.md](knowledge_graph.md) for
the services behind each:

| Category | Endpoint(s) |
|---|---|
| Entity Search | `entities/{node_type}`, `entities/{node_type}/{entity_ref}` |
| Relationship Search | `relationships?from_id=&to_id=` |
| Graph Traversal | `traverse?node_id=&edge_type=&reverse=&max_hops=&max_nodes=`, `shortest-path?from_id=&to_id=&edge_type=&max_depth=` |
| Timeline Queries | `timeline/{node_id}?edge_type=`, `at-time/{node_id}?as_of=&depth=&max_nodes=` |
| Similarity Queries | `similar/{node_id}?node_type=&limit=&min_score=` |
| Context Queries | `context/{node_id}?depth=&max_nodes=` |
| Neighborhood Queries | `neighborhood/{node_id}?depth=&edge_type=&max_nodes=` |
| Graph Statistics | `statistics` |

## 2c. News Intelligence & Community Intelligence API (Milestone 8)

`apps/api/routers/intelligence_router.py`, prefix `/api/v1/intelligence`, all GET/read-only,
gated at `get_current_user` (any authenticated user — same broad-read posture as §2b's Knowledge
Graph API). Maps 1:1 onto the nine API categories the constitution names — see
[news_intelligence.md](news_intelligence.md) and
[community_intelligence.md](community_intelligence.md) for the services behind each. Direct-
Postgres access now has matching real RLS (added retroactively in Milestone 9, migration 0022 —
see [rls.md](rls.md) §6b): the 7 tables this router serves are free+, the 4 it doesn't
(`news_sources`, `community_posts`, sync bookkeeping) are analyst+.

| Category | Endpoint(s) |
|---|---|
| News Search | `news/search?query=&source_id=&limit=` |
| News Timeline | `news/timeline?since=&until=&limit=` |
| Entity News | `news/entity/{entity_ref}?limit=` |
| Community Topics | `community/topics?platform=` |
| Sentiment | `sentiment/{entity_ref}?limit=` |
| Impact Scores | `impact?limit=`, `impact/event/{news_event_id}` |
| Summaries | `summaries/{subject_ref}/{summary_type}` |
| Source Reliability | `sources/{source_id}/reliability` |
| News Analytics | `analytics` |

## 2d. Prediction Intelligence Platform API (Milestone 9)

Three routers, all under `/api/v1`, gated at `get_current_user` except the operator dashboards
(`Role.ADMINISTRATOR`) — see [prediction_engine.md](prediction_engine.md) for the services
behind each. Direct-Postgres access (bypassing this API layer entirely) is backed by real RLS as
of migration 0021, not just the API-layer gate — see [rls.md](rls.md) §6a: app-facing
`predictions`/`prediction_markets` are free+, registry tables are analyst+, `prediction_audits`
is administrator+ only.

**`prediction_router.py` + `prediction_analytics_router.py`, prefix `/api/v1/predictions`**
(the analytics router's literal-prefixed routes register before the resource router's generic
`GET /{prediction_id}` so they aren't shadowed by the catch-all):

| Category | Endpoint(s) |
|---|---|
| Prediction (resource) | `POST generate`, `GET {prediction_id}`, `GET ?market_id=&status=&limit=`, `POST {prediction_id}/approve`, `POST {prediction_id}/reject` |
| Confidence | `GET {prediction_id}/confidence` |
| Explainability | `GET {prediction_id}/explanation` |
| Prediction History | `GET history/{subject_ref}?market_id=` |
| Prediction Monitoring | `GET monitoring/summary?limit=` |
| Prediction Statistics | `GET statistics/{market_key}?limit=` |
| Prediction Comparison | `POST compare` (body: `prediction_ids: string[]`, ≥2 required) |

**`market_router.py`, prefix `/api/v1/markets`**:

| Category | Endpoint(s) |
|---|---|
| Market Registry | `POST` (register), `GET ?sport_code=&status=`, `GET {market_key}`, `POST {market_key}/submit`, `/approve`, `/reject`, `/promote`, `/deprecate`, `/archive`, `/remove` |
| Feature Registry (Feature-to-Market mapping) | `GET {market_key}/features`, `POST {market_key}/features` |

**`prediction_admin_router.py`, prefix `/api/v1/admin/predictions`** (Admin Control Center
extension, [admin_center.md](admin_center.md)):

| Category | Endpoint(s) |
|---|---|
| Market Health Dashboard | `GET markets/health` |
| Confidence Dashboard | `GET markets/{market_key}/confidence?limit=` |
| Prediction Accuracy Dashboard | `GET markets/{market_key}/accuracy?limit=` |
| Prediction Drift Dashboard | `GET markets/{market_key}/drift?window=` |
| Export (Admin Action) | `GET markets/{market_key}/export?limit=` |
| Alerts | `GET alerts` |
| Recompute/Reprocess/Retry (Admin Action) | `POST regenerate` |
| Rollback (Admin Action) | `POST models/rollback` |

## 2e. Enterprise Machine Learning Platform API (Milestone 9.1)

`ml_platform_router.py`, prefix `/api/v1/admin/ml`, `Role.ADMINISTRATOR`-gated throughout — same
posture as `prediction_admin_router.py`. `prediction_admin_router.py` itself is unchanged; every
route below is new. See [machine_learning.md](machine_learning.md),
[training_pipeline.md](training_pipeline.md), [model_registry.md](model_registry.md),
[experiments.md](experiments.md), [calibration.md](calibration.md) for the services behind each.

| Category | Endpoint(s) |
|---|---|
| Training (Dataset Platform) | `POST training/datasets/{market_key}/build`, `POST training/datasets/{dataset_id}/validate`, `POST training/datasets/{dataset_id}/approve` |
| Training (Automatic Model Selection) | `POST training/select-champion` (body: `market_key`, `model_key_prefix`, `next_version`, `target_type`) |
| Experiment | `GET experiments/{market_key}?limit=`, `POST experiments/{experiment_id}/decide` (body: `decision`) |
| Model Registry | `GET models/{market_key}`, `POST models/{model_id}/deployment-mode` (body: `mode`) |
| Champion | `GET champion/{market_key}?model_key=&pinned_version=`, `POST champion/{model_id}/promote` (body: `approved_by`) |
| Feature Importance | `GET feature-importance/{market_key}` (SHAP global importance for the market's champion — 409 if the champion has no trained ML model to explain) |
| Calibration | `POST calibration/reports` (body: `method`, `samples: [[probability, outcome], ...]`) |
| Benchmark | `POST benchmark` (body: `market_key`, `algorithm`, `framework`, `target_type` — ranks one named candidate against the market's latest approved dataset) |
| Monitoring | `GET monitoring/{market_key}/health`, `GET`/`POST monitoring/{market_key}/latency` |
| Retraining | `POST retraining/{market_key}/check` |
| Evaluation | `GET evaluation/{model_id}?limit=` |

## 2f. Sports Reference Data & News Article Lookup API (Milestone 10)

Two additions surfaced by the frontend's mandatory backend audit — neither existed before this
milestone.

**`sports_router.py`, prefix `/api/v1/sports`, `get_current_user`-gated, no role floor** (free+ —
reference/catalog data, same posture as `predictions`/`prediction_markets`, not the analyst+
posture of Milestone 2-5's own schema). Composes the existing Milestone 2 repositories directly;
the only new capability is `PlayerRepositoryPort.list_by_sport` (additive, mirrors
`TeamRepositoryPort.list_by_sport`).

| Category | Endpoint(s) |
|---|---|
| Competitions | `GET {sport_code}/competitions`, `GET competitions/{id}`, `GET competitions/{id}/standings`, `GET competitions/{id}/fixtures?limit=` |
| Teams | `GET {sport_code}/teams`, `GET teams/{id}`, `GET teams/{id}/players`, `GET teams/{id}/fixtures?limit=` |
| Players | `GET {sport_code}/players?limit=`, `GET players/{id}` |
| Fixtures | `GET fixtures/{id}`, `GET {sport_code}/fixtures?competition_id=&limit=` (cross-competition browse) |

"Current season" is chosen heuristically (prefer `SeasonStatus.ACTIVE`, else most recently
started) — there is no single authoritative "current season" flag in the schema; this is a
frontend-convenience choice, not a domain rule. `{sport_code}/fixtures` without `competition_id`
is a bounded N+1 (competitions → current season → fixtures), acceptable at current data volume,
matching the naive-composition style already used elsewhere (e.g. `SemanticSearchService`).

**`intelligence_router.py` addition**: `GET /api/v1/intelligence/news/articles/{id}` — single-
article lookup using the existing `NewsArticleRepositoryPort.get()`; `/news/search` only ever
returned lists, and a News Center detail page needs a stable per-article URL.

## 3. Prediction Response Contract (as implemented, Milestone 9)

```json
{
  "data": {
    "id": "uuid",
    "market_id": "uuid",
    "model_id": "uuid",
    "subject_ref": "fixture-1",
    "value": "positive",
    "probability": 0.62,
    "confidence": {
      "feature_quality": 0.9, "feature_freshness": 0.95, "historical_accuracy": 0.5,
      "knowledge_graph_completeness": 0.2, "news_reliability": 0.5, "community_reliability": 0.5,
      "data_completeness": 1.0, "model_reliability": 0.5, "prediction_stability": 1.0,
      "composite": 0.68
    },
    "explanation": {
      "top_positive_features": [["football.team.form_shots_on_target_last5", 0.42]],
      "top_negative_features": [],
      "feature_importance": { "football.team.form_shots_on_target_last5": 1.0 },
      "knowledge_graph_evidence": [],
      "news_contribution": [],
      "community_contribution": [],
      "ai_explanation": "..."
    },
    "feature_snapshot": { "football.team.form_shots_on_target_last5": 6.0 },
    "model_version": "1",
    "status": "published",
    "generated_at": "2026-07-26T10:00:00Z",
    "data_freshness": "2026-07-26T10:00:00Z",
    "probability_distribution": { "HOME": 0.62, "DRAW": 0.23, "AWAY": 0.15 },
    "confidence_interval": null,
    "expected_error": null
  },
  "meta": {},
  "error": null
}
```

Matches the mandatory fields in the constitution's Confidence Engine / Explainable AI sections
— a prediction payload missing `confidence` or `explanation` is a contract violation.
`probability_distribution` carries the full outcome distribution for classification markets
(empty/omitted for regression markets, which use `confidence_interval`/`expected_error` instead).
`risk_score`
from the original illustrative shape doesn't exist as a separate field — `1 - probability` (for
the disfavored side) or `1 - composite confidence` serve that purpose today; a dedicated risk
score is a documented future addition, not a silently dropped field.

## 4. Auth & Rate Limiting

- Bearer JWT issued by Supabase Auth, validated on every request via a shared FastAPI
  dependency; role/claims drive RBAC.
- Rate limiting per user tier (free/premium/enterprise) enforced at the API gateway layer
  (Nginx) plus an application-layer token-bucket check tied to `billing.usage_counters`.
- **Every route in `apps/api/main.py` and every router now has an explicit auth dependency.**
  ~41 routes defined directly in `main.py` (Provider Management, Feature Registration/Flags/
  Quality, Sync triggers, Redis/KG monitoring) had none at all until Milestone 10 — closed with
  `require_role(Role.ADMINISTRATOR)`, user-approved (docs/security.md §8). `GET /api/v1/health`
  is the sole deliberate exception (public liveness probe, no data).

## 5. Real-Time

Live match state and live prediction updates are pushed via Supabase Realtime channels scoped
per-fixture; the REST API remains the source of truth for anything not inherently live.

## 6. Milestone Mapping

Auth: Milestone 3 (mock path)/Milestone 6 (real Supabase JWT path). Knowledge Graph API:
Milestone 7 (§2b). News/Community Intelligence API: Milestone 8 (§2c). Prediction Intelligence
Platform API (predictions, markets, admin dashboards): ✅ Milestone 9 (§2d) — not Milestone 6 as
originally sketched, since the Feature Intelligence Platform (Milestone 4) and Sports Ingestion/
Knowledge Graph (Milestones 5, 7) both needed to exist first to back real predictions. Enterprise
Machine Learning Platform API (training/experiment/registry/champion/feature-importance/
calibration/benchmark/monitoring/retraining/evaluation): ✅ Milestone 9.1 (§2e). **Core sports
read endpoints (competitions/teams/players/fixtures) did not actually ship until Milestone 10**
(§2f) — this line previously (incorrectly) said "Milestone 3"; Milestones 2-9 built the sports
schema, ingestion pipeline, and market/prediction layers on top of it, but nothing ever exposed
the sports entities themselves for reading until the frontend needed them.
Analytics/personalization endpoints: Milestones 10+ (Analytics Center shipped in Milestone 10
using existing aggregate endpoints; no new analytics-specific endpoints were added). Full OpenAPI
doc generation + TS client pipeline wired into CI: not yet done — the frontend's typed client is
hand-written against the backend's hand-built response dicts (§2f, docs/frontend_architecture.md
§3), since the backend defines no Pydantic response models to generate from.
