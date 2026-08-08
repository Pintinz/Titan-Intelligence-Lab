# 11 — Model Registry Schema

> Part of the standalone `docs/master-spec/` set — see the notice at the top of
> [`01-system-architecture.md`](01-system-architecture.md). This document specifies where every
> trained model's lineage, metrics, and deployment status are recorded — the schema backing the
> lifecycle described in [`04-mlops-architecture.md`](04-mlops-architecture.md).

## 1. Tables

```sql
CREATE SCHEMA IF NOT EXISTS models;

CREATE TABLE models.dataset_versions (
    id                  uuid PRIMARY KEY,
    market_id             uuid NOT NULL REFERENCES markets.market_definitions(id),
    window_start           timestamptz NOT NULL,
    window_end              timestamptz NOT NULL,
    sample_count             integer NOT NULL,
    feature_versions           jsonb NOT NULL,   -- { feature_key: version } snapshot at build time
    built_at                     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_dataset_versions_market_id ON models.dataset_versions (market_id);

CREATE TABLE models.training_runs (
    id                    uuid PRIMARY KEY,
    market_id               uuid NOT NULL REFERENCES markets.market_definitions(id),
    dataset_version_id        uuid NOT NULL REFERENCES models.dataset_versions(id),
    trigger                     text NOT NULL,       -- 'manual' | 'drift_detected' | 'dataset_stale'
    algorithms_evaluated          jsonb NOT NULL,      -- [{algorithm, metric_value}, ...] full roster + scores
    winning_algorithm               text NOT NULL,
    started_at                       timestamptz NOT NULL,
    completed_at                      timestamptz,
    status                              text NOT NULL DEFAULT 'running'  -- 'running' | 'succeeded' | 'failed'
);
CREATE INDEX ix_training_runs_market_id ON models.training_runs (market_id);

CREATE TABLE models.model_definitions (
    id                      uuid PRIMARY KEY,
    market_id                 uuid NOT NULL REFERENCES markets.market_definitions(id),
    model_key                   text NOT NULL,          -- stable identity across versions, e.g. 'football.match_winner.lgbm'
    version                       integer NOT NULL,
    algorithm                       text NOT NULL,          -- 'lightgbm' | 'xgboost' | 'catboost' | 'sklearn_logreg' | ...
    framework                         text NOT NULL,
    status                              text NOT NULL DEFAULT 'candidate',  -- § 2 lifecycle
    training_run_id                      uuid NOT NULL REFERENCES models.training_runs(id),
    dataset_version_id                     uuid NOT NULL REFERENCES models.dataset_versions(id),
    feature_versions                         jsonb NOT NULL,
    metrics                                    jsonb NOT NULL,  -- held-out accuracy/MAE/log-loss/etc
    calibration_ref                              uuid,             -- FK to a calibration_curves row, once fit
    feature_importance_ref                         jsonb,            -- top-level global importances
    artifact_ref                                     text NOT NULL,    -- object-storage / filesystem path to serialized model
    deployment_mode                                    text,             -- 'shadow' | 'canary' | 'live', set on promotion
    trained_at                                           timestamptz NOT NULL,
    promoted_at                                            timestamptz,
    retired_at                                               timestamptz,
    UNIQUE (model_key, version)
);
CREATE INDEX ix_model_definitions_market_status
    ON models.model_definitions (market_id, status);

-- Enforces "at most one CHAMPION per market" at the database level, not just in application code.
CREATE UNIQUE INDEX ux_model_definitions_one_champion_per_market
    ON models.model_definitions (market_id)
    WHERE status = 'champion';

-- Enforces "at most one CHALLENGER per market."
CREATE UNIQUE INDEX ux_model_definitions_one_challenger_per_market
    ON models.model_definitions (market_id)
    WHERE status = 'challenger';
```

## 2. Status Lifecycle

See [`04-mlops-architecture.md`](04-mlops-architecture.md) §1 for the full state diagram and
promotion policy narrative. In schema terms: `promote_to_champion(model_id)` is a single
transaction that (a) sets the target row's `status = 'champion'`, `promoted_at = now()`, and (b) sets
whatever row currently holds `status = 'champion'` for the same `market_id` to `status = 'retired'`,
`retired_at = now()` — the two partial unique indexes above make it impossible for this transaction
to leave a market with zero or two champions, even under a concurrent-write race.

`rollback(model_id)` (must reference a `RETIRED` row) runs the same transaction shape in reverse.

## 3. What a Model Record Answers

| Question | Column(s) |
|---|---|
| Which sport/market is this for? | `market_id` → `markets.market_definitions.sport_code` |
| What algorithm and framework? | `algorithm`, `framework` |
| When was it trained, on what data? | `trained_at`, `dataset_version_id` → `dataset_versions.window_start/end/sample_count` |
| Exactly which feature versions did it see? | `feature_versions` (snapshot, not a live FK — so it stays correct even after those features bump version later) |
| How good is it? | `metrics` (held-out accuracy for classification, MAE for regression, plus log-loss/Brier where relevant) |
| Is it calibrated? | `calibration_ref` |
| Why does it predict what it predicts? | `feature_importance_ref` (global) + SHAP computed per-request at serve time (§ [02-ml-architecture.md](02-ml-architecture.md) §6) |
| Is it live right now? | `status`, `deployment_mode` |
| Can I get the actual bytes? | `artifact_ref` |

## 4. Version History & Audit

Because rows are never deleted (`RETIRED` is a terminal-but-retained status, not a deletion), the
full promotion/retirement history of a market is reconstructible from `promoted_at`/`retired_at`
timestamps alone — "what model was serving this market on a given past date" is always answerable,
which matters for auditing a prediction that was made in the past against the model that actually
produced it.

## 5. What This Document Does Not Cover

Training run mechanics (how `algorithms_evaluated` gets populated) →
[`12-training-pipeline.md`](12-training-pipeline.md). Promotion/rollback HTTP endpoints →
[`15-api-contracts.md`](15-api-contracts.md). Calibration curve storage →
[`02-ml-architecture.md`](02-ml-architecture.md) §8.
