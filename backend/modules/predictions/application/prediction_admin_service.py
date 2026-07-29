"""Admin Control Center extension — Prediction Intelligence Platform dashboards (Milestone 9
Part 6). Aggregates real data already produced by this milestone's registries and repositories
into the named dashboards — Market Health, Confidence, Accuracy, Prediction Drift, Alerts — plus
the `export` Admin Action for predictions. `Approve`/`Reject` live on `PredictionCacheService`,
`Rollback` on `ModelRegistryService`, and market lifecycle actions (`Activate`/`Deactivate`/
`Archive`) on `MarketRegistryService` — this service does not duplicate any of them.

Deliberately scoped, same ADR-narrowing posture as every other v1 component this milestone:
"Execution Queue" and full "System Health" (Part 6) have no dedicated job-queue/infra-metrics
backing in this codebase (prediction generation isn't wired onto a Celery task queue this
milestone) — `alerts()` covers the honest subset of "system health" this platform can actually
observe from its own data: markets in PRODUCTION with no CHAMPION model, and markets whose
recent average confidence has fallen below their own configured `confidence_threshold`.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.predictions.domain.value_objects import MarketId, MarketStatus
from modules.predictions.ports.repositories import (
    MarketRepositoryPort,
    ModelRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)

_CONFIDENCE_FACTORS = (
    "feature_quality",
    "feature_freshness",
    "historical_accuracy",
    "knowledge_graph_completeness",
    "news_reliability",
    "community_reliability",
    "data_completeness",
    "model_reliability",
    "prediction_stability",
)


@dataclass
class PredictionAdminService:
    markets: MarketRepositoryPort
    models: ModelRepositoryPort
    predictions: PredictionRepositoryPort
    outcomes: PredictionOutcomeRepositoryPort

    async def market_health(self) -> dict:
        all_markets = await self.markets.list_all()
        by_status: dict[str, int] = {}
        missing_champion: list[str] = []
        for market in all_markets:
            by_status[market.status.value] = by_status.get(market.status.value, 0) + 1
            if market.status is MarketStatus.PRODUCTION:
                champion = await self.models.get_champion(market.id)
                if champion is None:
                    missing_champion.append(market.market_key)

        return {
            "total_markets": len(all_markets),
            "markets_by_status": by_status,
            "production_markets_missing_champion": missing_champion,
        }

    async def confidence_dashboard(self, market_id: MarketId, limit: int = 200) -> dict:
        predictions = await self.predictions.list_by_market(market_id, limit=limit)
        if not predictions:
            return {"sample_size": 0}

        averages = {
            factor: sum(getattr(p.confidence, factor) for p in predictions) / len(predictions)
            for factor in _CONFIDENCE_FACTORS
        }
        averages["composite"] = sum(p.confidence.composite for p in predictions) / len(predictions)
        return {"sample_size": len(predictions), **averages}

    async def accuracy_dashboard(self, market_id: MarketId, limit: int = 200) -> dict:
        outcomes = await self.outcomes.list_by_market(market_id, limit=limit)
        if not outcomes:
            return {"sample_size": 0, "historical_accuracy": None}

        correctness = [1.0 - min(max(o.error if o.error is not None else 0.0, 0.0), 1.0) for o in outcomes]
        return {"sample_size": len(outcomes), "historical_accuracy": sum(correctness) / len(correctness)}

    async def prediction_drift(self, market_id: MarketId, window: int = 50) -> dict:
        """Compares the mean probability of the most recent ``window`` predictions against the
        ``window`` before that — a positive ``drift`` means the model has been predicting higher
        probabilities more recently than before."""
        recent = await self.predictions.list_by_market(market_id, limit=window * 2)
        if len(recent) < 2:
            return {"sample_size": len(recent), "drift": None}

        recent_window = recent[:window]
        prior_window = recent[window : window * 2]
        if not prior_window:
            return {"sample_size": len(recent), "drift": None}

        recent_avg = sum(p.probability for p in recent_window) / len(recent_window)
        prior_avg = sum(p.probability for p in prior_window) / len(prior_window)
        return {
            "sample_size": len(recent),
            "recent_average_probability": recent_avg,
            "prior_average_probability": prior_avg,
            "drift": recent_avg - prior_avg,
        }

    async def alerts(self) -> list[dict]:
        alerts: list[dict] = []

        health = await self.market_health()
        for market_key in health["production_markets_missing_champion"]:
            alerts.append({"type": "missing_champion", "market_key": market_key, "severity": "critical"})

        for market in await self.markets.list_all():
            if market.status is not MarketStatus.PRODUCTION:
                continue
            predictions = await self.predictions.list_by_market(market.id, limit=50)
            if not predictions:
                continue
            average_confidence = sum(p.confidence.composite for p in predictions) / len(predictions)
            if average_confidence < market.confidence_threshold:
                alerts.append(
                    {
                        "type": "confidence_below_threshold",
                        "market_key": market.market_key,
                        "severity": "warning",
                        "average_confidence": average_confidence,
                        "threshold": market.confidence_threshold,
                    }
                )

        return alerts

    async def export_market_predictions(self, market_id: MarketId, limit: int = 500) -> list[dict]:
        predictions = await self.predictions.list_by_market(market_id, limit=limit)
        return [
            {
                "id": str(p.id),
                "subject_ref": p.subject_ref,
                "value": p.value,
                "probability": p.probability,
                "confidence_composite": p.confidence.composite,
                "status": p.status.value,
                "generated_at": p.generated_at.isoformat() if p.generated_at else None,
            }
            for p in predictions
        ]
