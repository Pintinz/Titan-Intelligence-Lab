# 15 — API Contracts

> Part of the standalone `docs/master-spec/` set — see the notice at the top of
> [`01-system-architecture.md`](01-system-architecture.md). This document specifies the HTTP
> surface for the pipelines and registries described in Milestones 3–4. All endpoints are under
> `apps/api/routers/` (§ [05](05-fastapi-folder-structure.md) §2), require authentication, and
> registry-mutation endpoints additionally require an admin/owner role.

## 1. Prediction API

### `POST /api/v1/predictions/{market_key}/generate`

Runs the full pipeline in [`13-prediction-pipeline.md`](13-prediction-pipeline.md).

**Request**
```json
{
  "fixture_id": "8f14e...c9a2"
}
```

**Response `200`**
```json
{
  "market_key": "football.match_winner",
  "fixture_id": "8f14e...c9a2",
  "model_id": "b2a91...ff01",
  "model_status": "champion",
  "predicted_probability": {"HOME": 0.54, "DRAW": 0.24, "AWAY": 0.22},
  "predicted_label": "HOME",
  "confidence": {
    "composite": 0.78,
    "breakdown": {
      "feature_quality": 0.9, "feature_freshness": 0.95, "historical_accuracy": 0.71,
      "data_completeness": 0.88, "model_reliability": 0.8, "prediction_stability": 0.82,
      "knowledge_graph_completeness": 0.6, "news_reliability": 0.7, "community_reliability": 0.65
    }
  },
  "explanation": {
    "type": "shap",
    "top_positive_features": [{"feature_key": "football.team.form_diff_last5", "contribution": 0.11}],
    "top_negative_features": [{"feature_key": "football.team.injury_impact", "contribution": -0.04}],
    "base_value": 0.41
  },
  "generated_at": "2026-08-05T14:02:11Z"
}
```

**Response `422` — market has insufficient historical data (no Champion, baseline still served)**
```json
{
  "market_key": "football.correct_score",
  "fixture_id": "8f14e...c9a2",
  "model_id": null,
  "model_status": "insufficient_data",
  "predicted_probability": {"...": "baseline-only distribution"},
  "confidence": {"composite": 0.31, "breakdown": {"...": "..."}},
  "explanation": {"type": "baseline_formula", "terms": ["..."]},
  "note": "Served from statistical baseline — insufficient historical data to train a model for this market yet."
}
```

`404` if `market_key` doesn't resolve to a `PRODUCTION` market; `404` if `fixture_id` doesn't exist.

### `GET /api/v1/predictions/{prediction_id}`

Returns a previously generated prediction, including its stored `feature_vector_snapshot` — the
audit/replay read path against `predictions.predictions` (§ [13](13-prediction-pipeline.md) §5).

## 2. Training API

### `POST /api/v1/training/{market_key}/trigger`

Manually invokes [`12-training-pipeline.md`](12-training-pipeline.md) for a market — the same
pipeline the scheduler triggers automatically (§ [14](14-automatic-retraining.md)), exposed for
on-demand use. **Admin-role only.**

**Request**
```json
{"reason": "manual retrain after feature formula fix"}
```

**Response `202`** (training runs asynchronously — a Celery task, not an inline request)
```json
{"training_run_id": "7c02f...11ab", "status": "running"}
```

### `GET /api/v1/training/runs/{training_run_id}`

Poll for run status/result — mirrors `models.training_runs` (§ [11](11-model-registry-schema.md) §1).

```json
{
  "training_run_id": "7c02f...11ab",
  "market_key": "football.match_winner",
  "status": "succeeded",
  "winning_algorithm": "lightgbm",
  "algorithms_evaluated": [
    {"algorithm": "lightgbm", "metric": "accuracy", "value": 0.612},
    {"algorithm": "xgboost", "metric": "accuracy", "value": 0.601},
    {"algorithm": "catboost", "metric": "accuracy", "value": 0.598}
  ],
  "resulting_model_id": "b2a91...ff01",
  "resulting_model_status": "challenger"
}
```

## 3. Model Registry API

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `/api/v1/models?market_key=&status=` | GET | any authenticated | List models, filterable by market/status |
| `/api/v1/models/{model_id}` | GET | any authenticated | Full `model_definitions` row + metrics |
| `/api/v1/models/{model_id}/promote` | POST | admin | Challenger → Champion (§ [11](11-model-registry-schema.md) §2) |
| `/api/v1/models/{model_id}/rollback` | POST | admin | Retired → Champion, retiring the current Champion |
| `/api/v1/models/{model_id}/deployment-mode` | PATCH | admin | Set `shadow` / `canary` / `live` (§ [04](04-mlops-architecture.md) §6) |

**`POST /api/v1/models/{model_id}/promote` — `409` if the model isn't `CHALLENGER` status, or if
the market already has a `CHAMPION` and no `force` flag was passed (promotion is always an explicit,
reviewed action outside the bootstrap case — see § [04](04-mlops-architecture.md) §3).**

## 4. Market Registry API

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `/api/v1/markets` | GET | any authenticated | List markets, filterable by `sport_code`/`status` |
| `/api/v1/markets` | POST | admin | Register a new `DRAFT` market |
| `/api/v1/markets/{id}/status` | PATCH | admin | Advance lifecycle status (§ [10](10-market-registry-schema.md) §2) — `409` if `promote_to_production` requested with zero required `feature_market_mappings` |
| `/api/v1/markets/{id}/feature-mappings` | POST | admin | Add a `feature_market_mappings` row |

## 5. Feature Registry & Feature Store API

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `/api/v1/features` | GET | any authenticated | List feature definitions, filterable by `sport_code`/`category`/`status` |
| `/api/v1/features` | POST | admin | Register a new `DRAFT` feature |
| `/api/v1/features/{feature_key}/status` | PATCH | admin | Advance lifecycle status (§ [09](09-feature-registry-schema.md) §3) |
| `/api/v1/feature-store/values` | GET | internal service only | `?feature_key=&entity_type=&entity_id=[&as_of=]` — thin HTTP wrapper over `FeatureStoreService.read_latest`/`read_as_of` (§ [08](08-feature-store-schema.md) §4), not exposed to the frontend |

## 6. Error Shape (shared across all endpoints)

```json
{
  "error": {
    "code": "insufficient_training_data",
    "message": "Market football.correct_score has 12 labeled samples, below the minimum of 30.",
    "details": {"market_key": "football.correct_score", "sample_count": 12, "minimum_required": 30}
  }
}
```

`code` is a stable, documented enum (never a raw exception class name) — the frontend and any
external consumer switches on `code`, never on `message` text.

## 7. What This Document Does Not Cover

Authentication/authorization mechanics themselves → [`20-security-strategy.md`](20-security-strategy.md).
Rate limiting/quota policy → [`19-scaling-strategy.md`](19-scaling-strategy.md).
