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
Request-log storage/viewing, retry-policy configuration beyond the circuit breaker, and webhook
support are not yet built — data model supports them, service methods land when the Admin UI
(Milestone 15) needs them.

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
