"""Model Monitoring (Milestone 9.1) — extends the EXISTING `PredictionAdminService` (Milestone 9)
with the monitoring dimensions it didn't cover: latency, volume, concept drift, confidence drift,
model health. Composes rather than duplicates for the two dimensions Milestone 9/9.1 already
compute correctly: probability drift reuses `PredictionAdminService.prediction_drift()`, feature
drift reuses `DatasetRegistryService.detect_drift()` (Milestone 9.1 task #160).
"""

from __future__ import annotations

import statistics as pystats
from dataclasses import dataclass
from datetime import datetime, timedelta

from modules.predictions.application.calibration_reporting_service import CalibrationReportBuilder
from modules.predictions.application.dataset_registry_service import DatasetRegistryService
from modules.predictions.application.prediction_admin_service import PredictionAdminService
from modules.predictions.domain.calibration import CalibrationMethod
from modules.predictions.domain.value_objects import MarketId
from modules.predictions.ports.monitoring import LatencySampleRepositoryPort
from modules.predictions.ports.repositories import PredictionOutcomeRepositoryPort, PredictionRepositoryPort

_LATENCY_P95_ALERT_MS = 2000.0
_CONCEPT_DRIFT_ALERT_THRESHOLD = 0.15  # absolute accuracy drop between windows
_CONFIDENCE_DRIFT_ALERT_THRESHOLD = 0.15


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(len(ordered) * p), len(ordered) - 1)
    return ordered[index]


@dataclass
class ModelMonitoringService:
    admin: PredictionAdminService
    dataset_registry: DatasetRegistryService
    latency: LatencySampleRepositoryPort
    predictions: PredictionRepositoryPort
    outcomes: PredictionOutcomeRepositoryPort

    async def record_latency(self, market_id: MarketId, duration_ms: float, now: datetime) -> None:
        await self.latency.record(market_id, duration_ms, now)

    async def latency_stats(self, market_id: MarketId) -> dict:
        samples = await self.latency.list_recent(market_id)
        durations = [duration for duration, _ in samples]
        if not durations:
            return {"sample_size": 0}
        return {
            "sample_size": len(durations),
            "mean_ms": pystats.fmean(durations),
            "p50_ms": _percentile(durations, 0.50),
            "p95_ms": _percentile(durations, 0.95),
            "p99_ms": _percentile(durations, 0.99),
            "exceeds_p95_alert_threshold": _percentile(durations, 0.95) > _LATENCY_P95_ALERT_MS,
        }

    async def volume(self, market_id: MarketId, now: datetime, window_hours: float = 24.0) -> dict:
        recent = await self.predictions.list_by_market(market_id, limit=2000)
        cutoff = now - timedelta(hours=window_hours)
        in_window = [p for p in recent if p.generated_at is not None and p.generated_at >= cutoff]
        return {"window_hours": window_hours, "prediction_count": len(in_window)}

    async def probability_drift(self, market_id: MarketId, window: int = 50) -> dict:
        """Reuses `PredictionAdminService.prediction_drift()` — same computation, this is just the
        Model Monitoring surface's name for it."""
        return await self.admin.prediction_drift(market_id, window=window)

    async def concept_drift(self, market_id: MarketId, window: int = 50) -> dict:
        """Compares recent-window accuracy against the window before it — a drop indicates the
        feature-to-outcome relationship has shifted (the model's concept of "what predicts the
        outcome" no longer matches reality), distinct from `probability_drift` (which only tracks
        the model's own output distribution, not whether it's still *correct*)."""
        outcomes = await self.outcomes.list_by_market(market_id, limit=window * 2)
        if len(outcomes) < 2:
            return {"sample_size": len(outcomes), "drift_detected": False, "reason": "insufficient outcome history"}

        recent_window = outcomes[:window]
        prior_window = outcomes[window : window * 2]
        if not prior_window:
            return {"sample_size": len(outcomes), "drift_detected": False, "reason": "no prior window to compare"}

        def _accuracy(batch) -> float:
            correctness = [1.0 - min(max(o.error if o.error is not None else 0.0, 0.0), 1.0) for o in batch]
            return sum(correctness) / len(correctness)

        recent_accuracy = _accuracy(recent_window)
        prior_accuracy = _accuracy(prior_window)
        drift = prior_accuracy - recent_accuracy  # positive means accuracy has degraded
        return {
            "sample_size": len(outcomes),
            "recent_accuracy": recent_accuracy,
            "prior_accuracy": prior_accuracy,
            "drift": drift,
            "drift_detected": drift >= _CONCEPT_DRIFT_ALERT_THRESHOLD,
        }

    async def confidence_drift(self, market_id: MarketId, window: int = 50) -> dict:
        """Same before/after-window comparison shape as `probability_drift`, applied to
        `Prediction.confidence.composite` instead of raw probability — a market whose own
        confidence has fallen is flagging its own uncertainty, independent of whether its
        probabilities or accuracy have moved."""
        recent = await self.predictions.list_by_market(market_id, limit=window * 2)
        if len(recent) < 2:
            return {"sample_size": len(recent), "drift_detected": False, "reason": "insufficient prediction history"}

        recent_window = recent[:window]
        prior_window = recent[window : window * 2]
        if not prior_window:
            return {"sample_size": len(recent), "drift_detected": False, "reason": "no prior window to compare"}

        recent_avg = sum(p.confidence.composite for p in recent_window) / len(recent_window)
        prior_avg = sum(p.confidence.composite for p in prior_window) / len(prior_window)
        drift = prior_avg - recent_avg  # positive means confidence has fallen
        return {
            "sample_size": len(recent),
            "recent_average_confidence": recent_avg,
            "prior_average_confidence": prior_avg,
            "drift": drift,
            "drift_detected": drift >= _CONFIDENCE_DRIFT_ALERT_THRESHOLD,
        }

    async def feature_drift(self, market_id: MarketId) -> dict:
        """Reuses `DatasetRegistryService.detect_drift()` (Milestone 9.1 task #160) — same
        computation, exposed under Model Monitoring's naming."""
        return await self.dataset_registry.detect_drift(market_id)

    async def calibration_drift(
        self, current_samples: list[tuple[float, bool]], baseline_samples: list[tuple[float, bool]], now: datetime
    ) -> dict:
        """Compares two `CalibrationReport`s' Expected Calibration Error — a model that was
        well-calibrated at deployment but has since drifted needs recalibration, not just
        retraining."""
        builder = CalibrationReportBuilder()
        current_report = builder.build(CalibrationMethod.NONE, current_samples, now)
        baseline_report = builder.build(CalibrationMethod.NONE, baseline_samples, now)
        ece_shift = current_report.expected_calibration_error - baseline_report.expected_calibration_error
        return {
            "current_ece": current_report.expected_calibration_error,
            "baseline_ece": baseline_report.expected_calibration_error,
            "ece_shift": ece_shift,
            "drift_detected": ece_shift >= 0.1,
        }

    async def model_health(self, market_id: MarketId, now: datetime, window: int = 50) -> dict:
        """Aggregates every dimension above plus the existing `PredictionAdminService.alerts()`
        into one status: "critical" if any admin alert fired or concept drift was detected,
        "degraded" if probability/confidence/feature drift or a latency breach was flagged,
        "healthy" otherwise. ``window`` is forwarded to every windowed drift check so a caller
        with a smaller real sample size than the 50-prediction default isn't silently starved of
        a prior-window comparison."""
        admin_alerts = await self.admin.alerts()
        concept = await self.concept_drift(market_id, window=window)
        confidence = await self.confidence_drift(market_id, window=window)
        probability = await self.probability_drift(market_id, window=window)
        feature = await self.feature_drift(market_id)
        latency = await self.latency_stats(market_id)

        critical = bool(admin_alerts) or concept.get("drift_detected", False)
        degraded = (
            confidence.get("drift_detected", False)
            or bool(feature.get("drift_detected", False))
            or latency.get("exceeds_p95_alert_threshold", False)
            or (probability.get("drift") is not None and abs(probability["drift"]) >= 0.2)
        )

        status = "critical" if critical else "degraded" if degraded else "healthy"
        return {
            "status": status,
            "admin_alerts": admin_alerts,
            "concept_drift": concept,
            "confidence_drift": confidence,
            "probability_drift": probability,
            "feature_drift": feature,
            "latency": latency,
        }
