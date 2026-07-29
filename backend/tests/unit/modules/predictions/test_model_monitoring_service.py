from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.dataset_registry_service import DatasetRegistryService
from modules.predictions.application.model_monitoring_service import ModelMonitoringService
from modules.predictions.application.prediction_admin_service import PredictionAdminService
from modules.predictions.domain.entities import ConfidenceBreakdown, ExplanationBundle, Prediction, PredictionOutcome
from modules.predictions.domain.value_objects import (
    MarketId,
    ModelId,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
)
from modules.predictions.infrastructure.monitoring.in_memory_latency_repository import (
    InMemoryLatencySampleRepository,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture
def market_id():
    return MarketId(uuid4())


@pytest.fixture
def model_id():
    return ModelId(uuid4())


@pytest.fixture
def latency_repo():
    return InMemoryLatencySampleRepository()


@pytest.fixture
def service(market_repo, model_repo, prediction_repo, prediction_outcome_repo, dataset_repo, latency_repo):
    admin = PredictionAdminService(markets=market_repo, models=model_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo)
    dataset_registry = DatasetRegistryService(datasets=dataset_repo)
    return ModelMonitoringService(
        admin=admin,
        dataset_registry=dataset_registry,
        latency=latency_repo,
        predictions=prediction_repo,
        outcomes=prediction_outcome_repo,
    )


def _prediction(market_id, model_id, confidence_composite=0.7, generated_at=T0, probability=0.6):
    return Prediction(
        id=PredictionId(uuid4()),
        market_id=market_id,
        model_id=model_id,
        subject_ref="fixture-1",
        value="positive",
        probability=probability,
        confidence=ConfidenceBreakdown(*([confidence_composite] * 9)),
        explanation=ExplanationBundle(),
        feature_snapshot={},
        model_version="1",
        status=PredictionStatus.PUBLISHED,
        generated_at=generated_at,
    )


def _outcome(prediction_id, error):
    return PredictionOutcome(id=PredictionOutcomeId(uuid4()), prediction_id=prediction_id, actual_value="positive", error=error, evaluated_at=T0)


class TestLatency:
    async def test_no_samples_reports_zero(self, service, market_id):
        stats = await service.latency_stats(market_id)
        assert stats == {"sample_size": 0}

    async def test_records_and_summarizes_latency(self, service, market_id):
        for ms in [100.0, 150.0, 200.0, 3000.0]:
            await service.record_latency(market_id, ms, T0)

        stats = await service.latency_stats(market_id)

        assert stats["sample_size"] == 4
        assert stats["mean_ms"] == pytest.approx(862.5)
        assert stats["exceeds_p95_alert_threshold"] is True


class TestVolume:
    async def test_counts_predictions_within_window(self, service, market_id, model_id, prediction_repo):
        await prediction_repo.record(_prediction(market_id, model_id, generated_at=T0))
        await prediction_repo.record(_prediction(market_id, model_id, generated_at=T0 - timedelta(hours=48)))

        volume = await service.volume(market_id, now=T0, window_hours=24)

        assert volume["prediction_count"] == 1


class TestConceptDrift:
    async def test_no_outcomes_reports_no_drift(self, service, market_id):
        result = await service.concept_drift(market_id)
        assert result["drift_detected"] is False

    async def test_detects_accuracy_degradation_between_windows(self, service, market_id, prediction_repo, prediction_outcome_repo):
        # prior window (indices 5-9): all correct (error=0.0); recent window (0-4): all wrong (error=1.0)
        for _ in range(5):
            prediction = await prediction_repo.record(_prediction(market_id, ModelId(uuid4())))
            await prediction_outcome_repo.record(_outcome(prediction.id, error=1.0))
        for _ in range(5):
            prediction = await prediction_repo.record(_prediction(market_id, ModelId(uuid4())))
            await prediction_outcome_repo.record(_outcome(prediction.id, error=0.0))

        result = await service.concept_drift(market_id, window=5)

        assert result["drift_detected"] is True
        assert result["drift"] == pytest.approx(1.0)


class TestConfidenceDrift:
    async def test_no_predictions_reports_no_drift(self, service, market_id):
        result = await service.confidence_drift(market_id)
        assert result["drift_detected"] is False

    async def test_detects_confidence_decline_between_windows(self, service, market_id, model_id, prediction_repo):
        for _ in range(5):
            await prediction_repo.record(_prediction(market_id, model_id, confidence_composite=0.5))
        for _ in range(5):
            await prediction_repo.record(_prediction(market_id, model_id, confidence_composite=0.9))

        result = await service.confidence_drift(market_id, window=5)

        assert result["drift_detected"] is True
        assert result["drift"] == pytest.approx(0.4)


class TestCalibrationDrift:
    async def test_flags_drift_when_ece_worsens(self, service):
        baseline = [(0.9, True)] * 90 + [(0.9, False)] * 10  # well-calibrated
        current = [(0.9, True)] * 50 + [(0.9, False)] * 50  # badly overconfident now

        result = await service.calibration_drift(current, baseline, T0)

        assert result["drift_detected"] is True
        assert result["ece_shift"] > 0.1

    async def test_no_drift_when_ece_unchanged(self, service):
        samples = [(0.9, True)] * 90 + [(0.9, False)] * 10
        result = await service.calibration_drift(samples, samples, T0)
        assert result["drift_detected"] is False
        assert result["ece_shift"] == pytest.approx(0.0)


class TestModelHealth:
    async def test_healthy_when_nothing_flagged(self, service, market_id, model_id, prediction_repo, prediction_outcome_repo, market_repo):
        from modules.predictions.domain.entities import MarketDefinition
        from modules.predictions.domain.value_objects import MarketKind, MarketStatus, TargetType

        await market_repo.upsert(
            MarketDefinition(
                id=market_id, market_key="football.stable", sport_code="football", name="Test", category="match_outcome",
                market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION, status=MarketStatus.DRAFT,
            )
        )

        health = await service.model_health(market_id, now=T0)

        assert health["status"] == "healthy"

    async def test_critical_when_concept_drift_detected(self, service, market_id, prediction_repo, prediction_outcome_repo):
        for _ in range(5):
            prediction = await prediction_repo.record(_prediction(market_id, ModelId(uuid4())))
            await prediction_outcome_repo.record(_outcome(prediction.id, error=1.0))
        for _ in range(5):
            prediction = await prediction_repo.record(_prediction(market_id, ModelId(uuid4())))
            await prediction_outcome_repo.record(_outcome(prediction.id, error=0.0))

        health = await service.model_health(market_id, now=T0, window=5)

        assert health["status"] == "critical"
