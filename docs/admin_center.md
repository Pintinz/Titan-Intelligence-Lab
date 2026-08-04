# TitanIQ — Admin Control Center

Status: A real (partial) visual dashboard shipped in Milestone 10 — earlier than this doc
originally planned (Milestone 15), because the frontend milestone needed *something* real to
render rather than waiting. `frontend/src/pages/admin/admin-center-page.tsx` covers Provider
Management (read), Feature Flags (read + enable/disable), Sync Runs (read), Prediction Markets
health/alerts (read), and Redis health (read) — all RBAC-gated `administrator`+ via `RoleRoute`,
matching the backend's own gating. **Not yet built**: the mutating admin workflows beyond flag
toggling — dataset build/validate/approve, champion selection/promotion, model rollback,
prediction regeneration all have a typed API client method (`mlPlatformApi`,
`adminPredictionsApi`) but no UI action forms yet. Role-gating behind `identity.roles` has been
live since Milestone 6 — see [security.md](security.md).

**Backend already live** (built ahead of schedule in Milestones 3–4): the full Provider
Management System described in §2 below, the Provider Health Intelligence subsystem in §2a, and
Feature Flags in §2b — `backend/modules/admin/` (domain, application, infrastructure) — so the
future Admin UI has a complete, tested service layer to call into rather than being built
alongside it. See [roadmap.md](roadmap.md) Milestones 3–4 and [decisions.md](decisions.md)
ADR-008–015.

## 1. Modules

Executive Dashboard · System Health / Infrastructure Monitoring · User Management · Role
Management & Permissions · Subscriptions & Payments · Rewarded Ads & Google Ads config ·
Revenue Analytics · Usage Analytics · Feature Store Management · Knowledge Graph Management ·
Prediction Monitoring · Model Registry · Outcome Learning Dashboard · News Dashboard ·
Community Dashboard · Notifications · Logs · Audit Trail · Feature Flags · Configuration
Management · Maintenance Mode.

## 2. API Provider Center

Centralized management for every external data/AI provider adapter
([architecture.md](architecture.md) §5):

- Add / remove / enable / disable providers.
- Rotate and encrypt API keys (never displayed in plaintext after entry — see
  [security.md](security.md) §"Secrets Management").
- Monitor usage, daily/monthly quota consumption, rate limits, latency, error rates.
- View request logs (redacted of any secrets/PII).
- Configure retry policy, cache policy, and sync schedule per provider.
- Alerting on quota approach/exhaustion.

Quota protection is automatic, not just visible: Redis caching, incremental sync (never
re-pull unchanged data), request deduplication, background/quota-aware scheduling, graceful
degradation (serve last-known-good + staleness flag), and automatic provider failover where a
second provider implements the same port ([architecture.md](architecture.md) §5).

**Implementation status** (Milestone 3): register/activate/deactivate/priority, multi-credential
storage with encryption and rotation, daily/monthly quota tracking, exhaustion prediction,
alerting threshold, priority-aware throttling, and per-provider circuit breaking are all built
and tested (`backend/modules/admin/`). `SportsProviderRouter`'s response cache is still
in-memory TTL, not Redis — Redis infrastructure now exists (`RedisFeatureStore`, Milestone 4)
but hasn't been wired into the provider router itself; that's a small follow-up, not a blocker.
Request-log storage/viewing and retry-policy configuration beyond the circuit breaker are not yet
built — data model supports them, service methods land when the Admin UI needs them.

### Milestone 11B — Provider Registry Admin API

The Operations Center's Provider Management page (Milestone 11A) shipped against an admin
console that could only *read* providers (`GET /api/v1/admin/providers`) and activate one that
already existed — there was no way to actually register a provider, add a credential, or delete
one, which is why the page showed "No providers configured" with nothing wrong underneath it.
Milestone 11B closes that specific gap; it does **not** rebuild the Provider Management System —
that was already complete per Milestone 3 above. All additions are additive, `Role.ADMINISTRATOR`-
gated the same way every other admin route is, and audit-logged through the same
`identity.audit_log_entries` table role changes use (`AuditAction.PROVIDER_*` values).

**New endpoints** (`backend/apps/api/main.py`, all under `/api/v1/admin/providers`):

| Route | Purpose |
|---|---|
| `POST /providers` | Register a provider — now exposes every `ProviderDefinition` field (base URL, auth type, region, version, environment, timeout/retry policy), not just key/name/category/priority. |
| `GET /providers/{id}` | Fetch one provider. |
| `PATCH /providers/{id}` | Patch-style update — only fields present in the request body change. |
| `DELETE /providers/{id}` | Removes a provider and its full history (credentials, usage, health checks, incidents, health state) — the `admin.*` foreign keys were switched to `ON DELETE CASCADE` for this (migration `0025`). |
| `POST /providers/{id}/disable` | The missing counterpart to the existing `/activate`. |
| `GET`/`POST /providers/{id}/credentials` | List credentials (masked — `****...<last 4>`, computed server-side from a controlled decrypt-then-discard, never the plaintext) / add a new one. |
| `POST /providers/{id}/rotate-key` | Wraps the existing `ProviderManagementService.rotate_credential` (deactivates the old credential, keeps its history, stores a new encrypted one). |
| `POST /providers/{id}/test`, `POST /providers/{id}/refresh` | Runs a real HTTP probe (`modules/admin/infrastructure/connection_tester.py`) against the provider's `base_url` using its active credential, classifies the result (healthy/warning/offline/unauthorized/rate_limited/timeout/not_configured), and records it through the existing `HealthIntelligenceEngine`. `/refresh` is the identical operation under the name the Operations Center brief used for it. |
| `POST /providers/import-from-env` | One-time migration for a provider whose only credential today is a raw `.env` value — see "Environment variable migration" below. |
| `GET /providers/{id}/usage` | Real request-count/error-count/quota-remaining data from `provider_usage_records`, not a placeholder. |
| `GET /providers/{id}/history` | Merges recent health checks and incidents into one timeline. |
| `GET /providers/categories`, `GET /providers/status` | Aggregate counts (by category, by status, by health) computed from the real provider table — used for the Operations Center's category/status summary tiles. |

**Category expansion**: `ProviderCategory` grew from `sports_data`/`ai` to also cover
`news`/`odds`/`general` (`modules/admin/domain/value_objects.py`) — the category column was
already a plain `String(32)`, so this needed no migration.

**Environment variable migration — deliberately not a standing fallback.** The brief that drove
this milestone asked for "read from DB, fall back to `.env` if unavailable." That's not what got
built, on purpose: `SportsProviderRouter._resolve_adapter` already has a designed fallback — no
usable DB credential means the *mock* adapter is used, not a raw environment read. Adding a
second, permanent env-read path would bypass the vault entirely for any request the DB path
missed, which is a real security regression, not a neutral compatibility feature. Instead,
`ProviderManagementService.import_from_env()` (and `POST /providers/import-from-env`) reads a
named environment variable **exactly once**, encrypts it into the vault, and registers/
credentials the provider — from that request onward the DB is the only source of truth for that
provider's credential, identical to a credential entered by hand through `/providers/{id}/credentials`.

**Connection testing** (`modules/admin/infrastructure/connection_tester.py`): deliberately
provider-agnostic — one HTTP GET to `base_url` with the credential attached per `auth_type`
(`bearer` / `api_key_header` / `api_key_query` / `basic`), classifying the transport-level
outcome. It does not parse or understand any individual provider's response schema; that keeps
one prober working for every current and future provider category the brief named (sports, news,
AI, odds, general/webhooks) without per-provider code.

**Background health monitoring**: `modules/admin/infrastructure/celery/tasks.py`'s
`admin.check_all_provider_health` task runs the same connection-test-and-record logic
(`modules/admin/application/connection_check_service.py`, shared with the manual `/test` and
`/refresh` endpoints) for every `ACTIVE` provider, on the `PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS`
(300s) cadence that `beat_schedule.py` had reserved since Milestone 5 but never wired up — see §2a
above ("Periodic scheduling of recovery probes ... needs Celery beat, not wired until a later
milestone — this is the method that job will call").

**Migration**: `alembic/versions/0025_provider_registry_fields.py` — additive columns on
`admin.providers` (all nullable or defaulted) plus the `ON DELETE CASCADE` FK switch described
above. No existing row, query, or service method is affected.

## 2a. Provider Health Intelligence

`HealthIntelligenceEngine` (`backend/modules/admin/application/health_intelligence_engine.py`)
is the automatic scoring layer behind the API Provider Center's health signals:

- **Success/failure rate, average latency, p50/p95/p99 latency, availability %, daily/monthly
  uptime, request throughput** — windowed metrics computed on demand from the append-only
  health-check history, never pre-aggregated (so nothing goes stale).
- **Consecutive failures & automatic status** — a materialized `ProviderHealthState` per
  provider (HEALTHY/DEGRADED/DOWN, 2/5 consecutive-failure thresholds by default) updated
  inline on every check, not a separate scoring job ([decisions.md](decisions.md) ADR-011).
- **Provider reliability score** and **independent per-credential reliability score** — 0-100,
  `None` when there's no data rather than a fabricated default ([decisions.md](decisions.md)
  ADR-012).
- **Historical health trends** — 7/30-day daily buckets of success rate and latency.
- **Provider incident history** — opens on degradation, escalates severity in place, resolves
  automatically on recovery; severity is a high-water mark for the episode.
- **Provider diagnostics** — one composite report (status, score, metrics, open incident,
  recent checks, plain-language recommendation) for a single dashboard call.
- **Automatic recovery attempts** — `attempt_recovery()` records a probe result through the same
  classification path as any other check, so recovery detection and normal monitoring can never
  drift out of sync. Periodic scheduling of recovery probes while a provider is DOWN needs
  Celery beat, not wired until a later milestone — this is the method that job will call.

**Dashboard API** (all under `/api/v1/admin/`): `providers/{id}/health/summary`,
`providers/{id}/health/trend`, `providers/{id}/health/incidents`, `providers/{id}/diagnostics`,
`providers/{id}/health/check` (record — used by the router on every real provider call, and
available for manual/synthetic checks), `credentials/{id}/health`.

## 2b. Feature Flags

`FeatureFlagService` (`backend/modules/admin/application/feature_flag_service.py`, Milestone 4)
gates incomplete sports/markets/subsystems from general availability:

- Create / enable / disable / set rollout percentage.
- Evaluation is deterministic — a SHA-256 hash of `key:context_id` decides the bucket, never
  `random()`, so the same context always gets the same answer for a given flag/percentage
  ([decisions.md](decisions.md) ADR-015).
- Safe defaults: an unknown flag, a disabled flag, or a partial-rollout flag evaluated with no
  `context_id` all evaluate to `False` — nothing is accidentally open.

**Dashboard API**: `POST /api/v1/admin/flags` (create), `GET /api/v1/admin/flags` (list),
`POST /api/v1/admin/flags/{key}/enable|disable|rollout`, `GET /api/v1/admin/flags/{key}/evaluate`.

## 3. Model & Outcome Learning Dashboards

Surfaces the Model Registry and Outcome Learning Engine data
([database_schema.md](database_schema.md) §4) for human oversight: champion vs. candidate
comparisons, drift reports, pending promotion decisions requiring approval — this is the human
gate referenced in the AI Governance section of the constitution; no model auto-promotes without
appearing here first. ✅ Implemented Milestone 9 for the Prediction Intelligence Platform
specifically (`ModelRegistryService`'s Champion/Challenger lifecycle + `rollback()`; the full
automated evaluation-report/benchmarking pipeline that writes `Experiment` rows remains future
scope, see [roadmap.md](roadmap.md) item 12).

## 3a. Prediction Intelligence Platform Extension (Milestone 9)

`prediction_admin_router.py`, prefix `/api/v1/admin/predictions`, gated at
`Role.ADMINISTRATOR` (stricter than the broad-read `get_current_user` the public
`/api/v1/predictions`/`/api/v1/markets` routers use) — see
[api_specification.md](api_specification.md) §2d for the full route list and
[prediction_engine.md](prediction_engine.md) for the services behind each:

| Constitution item | Delivered as |
|---|---|
| Prediction Registry, Market Registry, Feature Registry, Model Registry | `/api/v1/predictions`, `/api/v1/markets` (public resource routers) + `ModelRegistryService`/`PredictionCacheService` |
| Prediction Monitoring | `GET /api/v1/predictions/monitoring/summary` |
| Confidence Dashboard | `GET markets/{market_key}/confidence` |
| Feature Dashboard | existing Milestone 4 Feature Quality dashboards (§2 above) |
| Prediction Accuracy Dashboard | `GET markets/{market_key}/accuracy` |
| Prediction Drift Dashboard | `GET markets/{market_key}/drift` |
| Feature Drift Dashboard | not built this milestone — `features.feature_drift_reports` table exists (Milestone 4), no computation engine yet; genuinely future ([roadmap.md](roadmap.md) item 11) |
| Market Health Dashboard | `GET markets/health` (counts by status, PRODUCTION markets missing a champion) |
| Execution Queue, System Health (full infra metrics) | not built this milestone — no job queue is wired to prediction generation yet; `alerts()` below covers the honest observable subset instead |
| Audit Logs | `GET /api/v1/predictions/monitoring/summary` (audit action counts) + `PredictionAuditRepositoryPort.list_by_prediction`/`list_recent` |
| Alerts | `GET alerts` — missing-champion and below-confidence-threshold conditions, computed from real data, not simulated |
| Administration (Approve/Reject/Rollback/Recompute/Reprocess/Retry/Archive/Export) | Approve/Reject: `POST /api/v1/predictions/{id}/approve`\|`/reject`. Rollback: `POST models/rollback`. Recompute/Reprocess/Retry (same underlying action): `POST regenerate`. Archive: `POST /api/v1/markets/{market_key}/archive` (market-level). Export: `GET markets/{market_key}/export` |

## 3b. Enterprise Machine Learning Platform Extension (Milestone 9.1)

`ml_platform_router.py`, prefix `/api/v1/admin/ml`, gated at `Role.ADMINISTRATOR` — see
[api_specification.md](api_specification.md) §2e for the full route list and
[machine_learning.md](machine_learning.md)/[training_pipeline.md](training_pipeline.md)/
[model_registry.md](model_registry.md)/[experiments.md](experiments.md)/[calibration.md](calibration.md)
for the services behind each. The 9 named dashboards, each backed by a real endpoint:

| Dashboard | Delivered as |
|---|---|
| Training Dashboard | `POST training/datasets/{market_key}/build`\|`/validate`\|`/approve`, `POST training/select-champion` |
| Model Dashboard | `GET models/{market_key}`, `POST models/{model_id}/deployment-mode` |
| Champion Dashboard | `GET champion/{market_key}`, `POST champion/{model_id}/promote` |
| Experiment Dashboard | `GET experiments/{market_key}`, `POST experiments/{experiment_id}/decide` |
| Calibration Dashboard | `POST calibration/reports` |
| Feature-Importance Dashboard | `GET feature-importance/{market_key}` (SHAP global importance; 409 if the champion has no trained ML model yet) |
| Drift Dashboard | `GET monitoring/{market_key}/health` (surfaces `feature_drift`/`probability_drift`/`concept_drift`/`confidence_drift` together) |
| Model-Monitoring Dashboard | `GET monitoring/{market_key}/health`, `GET`/`POST monitoring/{market_key}/latency` |
| Retraining Dashboard | `POST retraining/{market_key}/check` |

Benchmark and Evaluation, though not among the 9 named dashboards, round out the API surface:
`POST benchmark` (rank one named candidate), `GET evaluation/{model_id}` (`ModelEvaluation`
history).

## 4. Access Control

All `/api/v1/admin/*` routes require `role = admin` (or a narrower admin sub-role once RBAC
detail is defined). Every admin action is written to the audit trail
(`admin.audit_log`, added to schema in Milestone 15) with actor, action, target, and timestamp.
✅ The Prediction Intelligence Platform extension (§3a) implements this today via
`Role.ADMINISTRATOR` gating (`require_role`, Milestone 6) and `predictions.prediction_audits`
(Milestone 9) — ahead of the general `admin.audit_log` table this section originally scoped for
Milestone 15.

## 5. Milestone Mapping

API Provider Center + Health Intelligence shipped in Milestone 3 (providers must be manageable
and observable before ingestion goes live), Feature Flags shipped in Milestone 4 alongside the
Feature Store, the Prediction Intelligence Platform extension (§3a) shipped in Milestone 9
alongside the platform it monitors, and the Enterprise Machine Learning Platform extension (§3b,
9 named dashboards) shipped in Milestone 9.1 alongside the ML platform it monitors — all backend
service layer, ✅ complete. **The visual dashboard (read-only across the sections above, plus
Feature Flag toggling) shipped in Milestone 10** — earlier than this document's original
Milestone 15 target — see [roadmap.md](roadmap.md) and [frontend_architecture.md](frontend_architecture.md).
Full mutating admin workflows (dataset/champion/model lifecycle actions) remain a follow-up.
