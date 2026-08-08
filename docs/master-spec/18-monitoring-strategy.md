# 18 — Monitoring Strategy

> Part of the standalone `docs/master-spec/` set — see the notice at the top of
> [`01-system-architecture.md`](01-system-architecture.md). Observability is a Milestone-1 concern
> per [`01-system-architecture.md`](01-system-architecture.md) §9 ("traced end-to-end from Milestone
> 2 onward, not bolted on later") — this document specifies what's actually watched.

## 1. Three Pillars

| Pillar | What it answers | Mechanism |
|---|---|---|
| Structured logs | "What exactly happened for this one request/task?" | JSON logs, every log line for a request carries `request_id`; every prediction-related log additionally carries `market_key` and `model_id` so a single prediction's full trail is greppable |
| Metrics | "Is the system healthy right now, and how is it trending?" | Time-series counters/histograms exported per service |
| Traces | "Where did the time go across service boundaries?" | End-to-end span per request (API → Feature Store read → model inference → calibration → confidence → SHAP), so the latency budget in [`13-prediction-pipeline.md`](13-prediction-pipeline.md) §6 is actually measured, not assumed |

## 2. What's Monitored

### Serving health
- API request rate, error rate, and p50/p95/p99 latency, **per endpoint** — the Prediction endpoint
  is watched separately from registry CRUD endpoints, since their latency budgets differ entirely.
- Feature Store cache hit rate (online reads) — a falling hit rate is an early signal of a Redis
  problem or a TTL misconfiguration before it shows up as prediction latency.
- Model load status per market — is a Champion actually loaded and warm for every `PRODUCTION`
  market, or is a market silently falling back to baseline-only because its model failed to load.

### Data pipeline health
- Ingestion freshness per sport/provider — time since the last successful sync; alerts if a
  provider goes silent past its expected sync cadence.
- Feature Engineering Pipeline task failure rate (Celery task-level) and per-stage duration
  (§ [03-data-engineering-architecture.md](03-data-engineering-architecture.md) §2) — a slow
  "rolling stats" stage, specifically, is a different problem than a slow "clean" stage, and the
  per-stage breakdown says which.
- Null-rate per feature (§ [03](03-data-engineering-architecture.md) §4) — trended over time, not
  just gated at write time, so a *slow* degradation (a provider quietly dropping a field over weeks)
  is caught, not just a hard failure.

### ML/prediction quality
- **Live accuracy vs. held-out accuracy, per market's Champion** — this is the exact signal
  [`14-automatic-retraining.md`](14-automatic-retraining.md) §3's drift check reads; it is
  dashboarded independently of whether it has yet crossed the retraining threshold, so a human can
  see a market trending toward drift before the automated trigger fires.
- Confidence score distribution per market — a market whose confidence scores cluster unexpectedly
  low across the board usually means one of the nine factors
  (§ [02-ml-architecture.md](02-ml-architecture.md) §7) is systematically starved, not that every
  individual prediction is genuinely uncertain.
- Calibration reliability — a reliability diagram (predicted probability bucket vs. observed
  frequency) per market's Champion, refreshed alongside each calibration refit
  (§ [02](02-ml-architecture.md) §8).
- Training run outcomes — success/discard/failure rate over time per market, surfaced from
  `models.training_runs` (§ [11](11-model-registry-schema.md) §1).

## 3. Alerting

| Signal | Threshold | Routes to |
|---|---|---|
| API p95 latency breach | Sustained above [`01`](01-system-architecture.md) §9's target for 5+ min | On-call engineer |
| A `PRODUCTION` market has no loaded Champion | Any duration | On-call engineer (page — this means live traffic is silently degraded to baseline-only) |
| Ingestion freshness breach for a provider | Past 2× expected sync cadence | Data engineering |
| A feature's null rate spikes | Statistically significant jump vs. trailing baseline | The feature's registered `owner` (§ [09](09-feature-registry-schema.md) §4) — not a generic on-call queue, since only the owner knows if it's expected |
| Drift threshold crossed for a market | Per [`14`](14-automatic-retraining.md) §3 | ML engineering (informational — retraining is already automatic; this alert is "here's why a retrain just fired") |
| Calibration fit sample count stuck below minimum | A `PRODUCTION` market accumulating outcomes too slowly to ever calibrate | ML engineering |

## 4. Dashboards

- **Executive**: prediction volume, aggregate accuracy trend across all markets, system uptime.
- **Per-market**: accuracy trend (live vs. held-out), confidence distribution, calibration
  reliability diagram, training run history, current Champion/Challenger status.
- **Pipeline health**: ingestion freshness per provider, Feature Engineering Pipeline stage
  durations, Feature Store cache hit rate.
- **Infrastructure**: standard service-level dashboards (CPU/memory/queue depth) per deployment
  unit from [`17-deployment-strategy.md`](17-deployment-strategy.md) §1.

## 5. What This Document Does Not Cover

Infrastructure capacity/autoscaling decisions made in response to these signals →
[`19-scaling-strategy.md`](19-scaling-strategy.md). Access control for who can view/query
monitoring data → [`20-security-strategy.md`](20-security-strategy.md).
