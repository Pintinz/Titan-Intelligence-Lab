# 20 — Security Strategy

> Part of the standalone `docs/master-spec/` set — see the notice at the top of
> [`01-system-architecture.md`](01-system-architecture.md).

## 1. Authentication

Bearer-token authentication (JWT) on every API request; `apps/api/auth_deps.py`-style dependency
functions validate the token and attach the authenticated identity to the request context before any
handler runs. No endpoint is reachable unauthenticated, including read-only registry listing
endpoints — this platform's registries and prediction history are internal business data, not a
public API surface.

## 2. Authorization

Role-based access control, enforced at two layers, neither trusted alone:

| Layer | Enforces | Example |
|---|---|---|
| Application (FastAPI dependency) | Endpoint-level role checks (`require_role("admin")`) | Only an admin can call `POST /models/{id}/promote` (§ [15-api-contracts.md](15-api-contracts.md) §3) |
| Database (Row-Level Security) | Row-level tenant/ownership scoping, per [`06-postgresql-schema.md`](06-postgresql-schema.md) §5 | A query issued with a compromised or buggy application-layer check still cannot return rows outside the caller's authorized scope, because Postgres itself enforces the policy |

Mutation endpoints across every registry (Market, Feature, Model) and the manual training-trigger
endpoint are admin-only (§ [15](15-api-contracts.md)). Read endpoints (list markets, view a
prediction) are available to any authenticated user, scoped by RLS where the data is
tenant-specific.

## 3. Secrets Management

- Provider API keys and any other credential are never committed to the repository, including in
  example/template env files — real secrets live only in the deployment environment's secret store.
- Provider credentials are encrypted at rest in the database (for any credential that must be
  stored, e.g. per-tenant provider API keys), decrypted only in-memory at the point of use.
- Config is environment-driven (12-factor) and validated at process startup against a typed schema
  — a missing or malformed required secret fails the process at boot, not on the first request that
  happens to need it.

## 4. Input Validation & Abuse Prevention

- Every API request body/query parameter is validated against a typed schema (Pydantic) at the
  boundary — a handler never receives an unvalidated dict.
- The Prediction endpoint is rate-limited per authenticated caller — unlike a typical read endpoint,
  each request triggers real inference compute (§ [19-scaling-strategy.md](19-scaling-strategy.md)
  §4), so unbounded request volume is both a cost and an availability risk, not just a performance
  nuisance.
- The manual training-trigger endpoint (§ [15](15-api-contracts.md) §2) is additionally
  rate-limited independent of role — even an admin should not be able to accidentally fire
  unbounded concurrent training runs against the same market.

## 5. Model & Artifact Security

- Model artifacts (§ [11-model-registry-schema.md](11-model-registry-schema.md) `artifact_ref`) are
  stored in a location accessible only to the Training and Prediction services' service identities —
  never publicly readable. A leaked model artifact leaks feature importances and effectively the
  platform's scoring logic, which is treated as sensitive IP, not just a file.
- `feature_vector_snapshot` stored on every prediction (§ [13-prediction-pipeline.md](13-prediction-pipeline.md)
  §5) is scoped by the same RLS as the rest of `predictions.*` — a prediction's full input trail is
  only visible to callers authorized to see that prediction in the first place.

## 6. Audit Logging

Every registry mutation — market status change, feature status change, model promotion, model
rollback, manual training trigger — is written to an append-only audit log recording the actor, the
action, the before/after state, and the timestamp. This is a distinct requirement from the
operational logs in [`18-monitoring-strategy.md`](18-monitoring-strategy.md): audit logs answer
"who did this and when," retained for compliance/accountability, not for debugging latency.

## 7. Data Sensitivity

Raw provider data (§ [07-raw-data-schema.md](07-raw-data-schema.md)) is predominantly public sports
information — team names, player names, public statistics — and does not carry the PII burden a
typical consumer application has. The genuinely sensitive surfaces are: user account data
(handled by the `identity` module's own security posture, out of scope for this ML-focused spec set),
provider API credentials (§3), and model artifacts (§5) — security effort here is weighted toward
those, not toward encrypting public match statistics.

## 8. What This Document Does Not Cover

User identity/tenancy data model itself (owned by the `identity` module, not part of this ML/data
spec set). Infrastructure network-layer security (VPC/firewall rules) — deployment-environment
specific, set at the infrastructure-provisioning layer referenced but not detailed in
[`17-deployment-strategy.md`](17-deployment-strategy.md).
