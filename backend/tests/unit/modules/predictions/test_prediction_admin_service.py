from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.prediction_admin_service import PredictionAdminService
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    ModelDefinition,
    Prediction,
    PredictionOutcome,
)
from modules.predictions.domain.value_objects import (
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    ModelStatus,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture
def service(market_repo, model_repo, prediction_repo, prediction_outcome_repo):
    return PredictionAdminService(
        markets=market_repo, models=model_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo
    )


async def _market(market_repo, key, status=MarketStatus.PRODUCTION, confidence_threshold=0.5):
    from modules.predictions.domain.entities import MarketDefinition

    market = MarketDefinition(
        id=MarketId(uuid4()),
        market_key=key,
        sport_code="football",
        name="Test",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        status=status,
        confidence_threshold=confidence_threshold,
    )
    return await market_repo.upsert(market)


def _prediction(market_id, model_id, probability=0.6, confidence_composite=0.7, subject_ref="fixture-1"):
    factor = confidence_composite
    return Prediction(
        id=PredictionId(uuid4()),
        market_id=market_id,
        model_id=model_id,
        subject_ref=subject_ref,
        value="positive",
        probability=probability,
        confidence=ConfidenceBreakdown(*([factor] * 9)),
        explanation=ExplanationBundle(),
        feature_snapshot={},
        model_version="1",
        status=PredictionStatus.PUBLISHED,
        generated_at=T0,
    )


@pytest.mark.asyncio
async def test_market_health_counts_by_status(service, market_repo):
    await _market(market_repo, "football.a", status=MarketStatus.PRODUCTION)
    await _market(market_repo, "football.b", status=MarketStatus.DRAFT)

    health = await service.market_health()

    assert health["total_markets"] == 2
    assert health["markets_by_status"] == {"production": 1, "draft": 1}


@pytest.mark.asyncio
async def test_market_health_flags_production_market_missing_champion(service, market_repo, model_repo):
    market = await _market(market_repo, "football.no_champion")

    health = await service.market_health()

    assert health["production_markets_missing_champion"] == ["football.no_champion"]


@pytest.mark.asyncio
async def test_market_health_does_not_flag_market_with_champion(service, market_repo, model_repo):
    market = await _market(market_repo, "football.has_champion")
    await model_repo.upsert(
        ModelDefinition(
            id=ModelId(uuid4()), market_id=market.id, model_key="m1", version=1, algorithm="heuristic_logistic_v1",
            status=ModelStatus.CHAMPION,
        )
    )

    health = await service.market_health()

    assert health["production_markets_missing_champion"] == []


@pytest.mark.asyncio
async def test_confidence_dashboard_averages_all_nine_factors(service, market_repo, prediction_repo):
    market = await _market(market_repo, "football.confidence_market")
    await prediction_repo.record(_prediction(market.id, ModelId(uuid4()), confidence_composite=0.8))
    await prediction_repo.record(_prediction(market.id, ModelId(uuid4()), confidence_composite=0.4))

    dashboard = await service.confidence_dashboard(market.id)

    assert dashboard["sample_size"] == 2
    assert dashboard["composite"] == pytest.approx(0.6)
    assert dashboard["feature_quality"] == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_confidence_dashboard_empty_market(service, market_repo):
    market = await _market(market_repo, "football.empty_confidence_market")

    dashboard = await service.confidence_dashboard(market.id)

    assert dashboard == {"sample_size": 0}


@pytest.mark.asyncio
async def test_accuracy_dashboard_computes_historical_accuracy(service, market_repo, prediction_repo, prediction_outcome_repo):
    market = await _market(market_repo, "football.accuracy_market")
    prediction = await prediction_repo.record(_prediction(market.id, ModelId(uuid4())))
    await prediction_outcome_repo.record(
        PredictionOutcome(id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id, actual_value="positive", error=0.0, evaluated_at=T0)
    )

    dashboard = await service.accuracy_dashboard(market.id)

    assert dashboard["sample_size"] == 1
    assert dashboard["historical_accuracy"] == 1.0


@pytest.mark.asyncio
async def test_accuracy_dashboard_with_no_outcomes(service, market_repo):
    market = await _market(market_repo, "football.no_outcomes_market")

    dashboard = await service.accuracy_dashboard(market.id)

    assert dashboard == {"sample_size": 0, "historical_accuracy": None}


@pytest.mark.asyncio
async def test_prediction_drift_compares_recent_vs_prior_window(service, market_repo, prediction_repo):
    market = await _market(market_repo, "football.drift_market")
    for _ in range(3):
        await prediction_repo.record(_prediction(market.id, ModelId(uuid4()), probability=0.8))
    for _ in range(3):
        await prediction_repo.record(_prediction(market.id, ModelId(uuid4()), probability=0.4))

    drift = await service.prediction_drift(market.id, window=3)

    assert drift["sample_size"] == 6
    assert drift["recent_average_probability"] == pytest.approx(0.8)
    assert drift["prior_average_probability"] == pytest.approx(0.4)
    assert drift["drift"] == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_prediction_drift_insufficient_history(service, market_repo, prediction_repo):
    market = await _market(market_repo, "football.short_drift_market")
    await prediction_repo.record(_prediction(market.id, ModelId(uuid4())))

    drift = await service.prediction_drift(market.id, window=10)

    assert drift == {"sample_size": 1, "drift": None}


@pytest.mark.asyncio
async def test_alerts_reports_missing_champion_and_low_confidence(service, market_repo, prediction_repo):
    no_champion_market = await _market(market_repo, "football.alert_no_champion")
    low_confidence_market = await _market(market_repo, "football.alert_low_confidence", confidence_threshold=0.9)
    await prediction_repo.record(_prediction(low_confidence_market.id, ModelId(uuid4()), confidence_composite=0.5))

    alerts = await service.alerts()

    alert_types = {(a["type"], a["market_key"]) for a in alerts}
    assert ("missing_champion", "football.alert_no_champion") in alert_types
    assert ("confidence_below_threshold", "football.alert_low_confidence") in alert_types


@pytest.mark.asyncio
async def test_export_market_predictions(service, market_repo, prediction_repo):
    market = await _market(market_repo, "football.export_market")
    prediction = await prediction_repo.record(_prediction(market.id, ModelId(uuid4())))

    exported = await service.export_market_predictions(market.id)

    assert len(exported) == 1
    assert exported[0]["id"] == str(prediction.id)
    assert exported[0]["confidence_composite"] == prediction.confidence.composite
