# 19 — Scaling Strategy

> Part of the standalone `docs/master-spec/` set — see the notice at the top of
> [`01-system-architecture.md`](01-system-architecture.md). Every scaling decision here traces back
> to [`01-system-architecture.md`](01-system-architecture.md) §9's non-functional targets.

## 1. Statelessness Is the Precondition

`apps/api` and `apps/worker` hold no in-process state that a second replica wouldn't also have —
every model artifact loaded into a process is loaded independently by every replica from the same
Model Registry/artifact store (§ [11-model-registry-schema.md](11-model-registry-schema.md), a
recomputable cache, not authoritative state); the Feature Store's online cache (Redis) is external,
shared, and safe for N replicas to read/write concurrently. This is what makes horizontal scaling of
the API and worker tiers a capacity decision, not an architecture change.

## 2. Per-Tier Scaling

| Tier | Scales on | Mechanism |
|---|---|---|
| `apps/api` | Request rate / p95 latency | Horizontal pod autoscaling, stateless replicas behind a load balancer |
| `apps/worker` | Celery queue depth | Horizontal autoscaling keyed to queue length, separate worker pools per queue priority (ingestion vs. training — a burst of ingestion tasks should never starve a scheduled training run) |
| `apps/scheduler` | N/A | Single active leader (§ [17-deployment-strategy.md](17-deployment-strategy.md) §3); this tier does not need horizontal scale, only availability (a standby ready to take leadership) |
| PostgreSQL | Read volume vs. write volume, separately | Primary handles all writes + the Prediction Service's latency-sensitive reads; read replica(s) absorb the Training Service's bulk `read_bulk_as_of` scans (§ [08-feature-store-schema.md](08-feature-store-schema.md) §4) so a large training run never contends with live prediction traffic on the same connection pool |
| Redis (online Feature Store) | Key cardinality / read throughput | Cluster mode once per-feature-per-entity key count outgrows a single node's memory comfortably; TTL-bounded keys (§ [08](08-feature-store-schema.md) §3) keep steady-state memory bounded regardless of historical data growth |

## 3. Model Inference Scale

LightGBM/CatBoost/XGBoost models at the size this platform trains (tabular, hundreds of features,
not deep learning) fit comfortably in a single process's memory and infer in single-digit
milliseconds — inference scales by replicating `apps/api` horizontally like any other stateless
work, with no dedicated model-serving tier required. This is revisited only if/when the PyTorch
track (§ [02-ml-architecture.md](02-ml-architecture.md) §3, reserved for future
sequence/embedding-based models) introduces models large enough that per-replica loading becomes
memory-prohibitive — at that point a dedicated inference tier (loaded once, called over an internal
RPC) would be the next design, not a starting assumption.

## 4. Backpressure & Load Shedding

- **Ingestion bursts**: provider adapters respect each provider's own rate limits; a burst of
  available fixture updates queues in Celery rather than fanning out unbounded concurrent requests
  to an external API.
- **Training queue priority**: training tasks run on a separate Celery queue from ingestion tasks
  (§2), so a large backlog of routine ingestion work never delays a retraining run that
  [`14-automatic-retraining.md`](14-automatic-retraining.md) has already decided is needed.
- **Prediction endpoint**: rate-limited per caller (§ [20-security-strategy.md](20-security-strategy.md)
  §4) — inference has real compute cost per request, unlike a typical read endpoint, so unbounded
  request volume is a cost/availability risk worth shedding at the edge rather than absorbing.

## 5. Capacity Planning

Sized against the non-functional targets in
[`01-system-architecture.md`](01-system-architecture.md) §9: 99.9% availability budget (≈43
min/month), p95 < 300ms for cached prediction reads, p95 < 2s for cold/uncached inference. Capacity
headroom is planned so that losing one full availability zone's worth of `apps/api`/`apps/worker`
replicas does not itself breach the latency target under current traffic — a target expressed as
"N+1 at peak," reviewed each time sustained traffic grows past the previous planning cycle's
assumption.

## 6. What This Document Does Not Cover

Release mechanics for scaling a deployment unit's replica count → [`17-deployment-strategy.md`](17-deployment-strategy.md).
The metrics that inform when to scale → [`18-monitoring-strategy.md`](18-monitoring-strategy.md).
