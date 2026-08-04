"""Calibration Fitting Service.

Audit finding (2026-08-02): `CalibratorPort.calibrate()` is real and genuinely wired into
`PredictionEngine.generate()` on every call — but `CalibratorPort.fit()` (the port's own docstring
already names its intended caller: "Called by `ModelRegistryService` whenever enough new outcomes
have accumulated to re-calibrate") had zero real call sites anywhere. `PlattScalingCalibrator`'s
unfitted default (`a=1.0, b=0.0`) is mathematically an identity transform
(`sigmoid(logit(p)) == p`), so every "calibrated" probability ever produced has actually just been
the raw, unfitted probability passed through unchanged. This service is that missing caller.

For each PRODUCTION market's CHAMPION model, gathers real `(probability, actual_outcome)` pairs
from outcome history — `real_outcome_is_positive` recovers the real polarity the same way the
Dataset Builder does, from what the prediction claimed plus whether that claim matched reality —
and calls `calibrator.fit()`.

**`Prediction.probability` is P(the published `value`), not P("positive") (Universal Probability
Engine, 2026-08-02)**: `PredictionEngine._shape_outcome` reads the published confidence back out
of the calibrated `probability_distribution` at `value`'s own key, so it always means "confidence
in the outcome actually published" — not "confidence in the positive side," which is what the two
weighted predictors' own raw `probability` field means internally. The calibrator itself, though,
was fit (and must keep being fit) against a consistent single reference class — P("positive") —
same as any binary-classifier calibration curve. `real_label_is_positive` recovers which side
`value` actually was; when it's the negative side, `1 - prediction.probability` reconstructs the
raw P("positive") the calibrator needs, exactly undoing `_shape_outcome`'s read-back.

**Known v1 scope limitation, documented rather than silently wrong**: the "raw probability" fed
to `fit()` is still derived from `Prediction.probability` — the value already returned by
`calibrator.calibrate()` at generation time. For a model's *first* fit this is exactly right
(calibration was the identity transform when those predictions were generated, so the recovered
P("positive") genuinely is the raw score). For a *second* fit after calibration parameters already
exist, predictions generated in between carry an already-calibrated probability, not the raw one —
feeding that back into `fit()` treats a partially-transformed score as if it were raw. Persisting
the true pre-calibration probability as its own field would fix this properly; that's real,
separable schema work, not undertaken here (same "documented proxy, not fabricated" posture as
every other honestly-scoped v1 metric in this codebase).

**Deployment-topology note**: `PlattScalingCalibrator` itself is explicitly an in-memory,
per-process singleton (its own docstring: "accumulates fitted per-model parameters in memory
across requests") — it was never designed to persist across a restart or share state between
separate OS processes. If Celery workers run in a different process from the API server, fitted
parameters won't reach the API process's own calibrator instance until a real DB-backed
`CalibratorPort` implementation exists — future work, not undertaken here, same posture as
`get_dataset_repo`'s own documented in-memory-only scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.predictions.application.outcome_label_mapper import real_label_is_positive, real_outcome_is_positive
from modules.predictions.domain.entities import MarketDefinition
from modules.predictions.domain.value_objects import MarketStatus, ModelId
from modules.predictions.ports.calibrator import CalibratorPort
from modules.predictions.ports.repositories import (
    MarketRepositoryPort,
    ModelRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)

DEFAULT_MIN_SAMPLES = 20


@dataclass(frozen=True)
class CalibrationFitOutcome:
    market_key: str
    model_id: ModelId | None
    sample_count: int
    fitted: bool
    reason: str | None = None


@dataclass
class CalibrationFittingService:
    markets: MarketRepositoryPort
    models: ModelRepositoryPort
    predictions: PredictionRepositoryPort
    outcomes: PredictionOutcomeRepositoryPort
    calibrator: CalibratorPort
    min_samples: int = DEFAULT_MIN_SAMPLES

    async def fit_all_production_markets(self, now: datetime) -> list[CalibrationFitOutcome]:
        """Checked, and (re)fitted where enough real outcome history exists, every PRODUCTION
        market's Champion — the periodic sweep a Celery beat task calls."""
        outcomes = []
        for market in await self.markets.list_by_status(MarketStatus.PRODUCTION):
            outcomes.append(await self._fit_market(market, now))
        return outcomes

    async def _fit_market(self, market: MarketDefinition, now: datetime) -> CalibrationFitOutcome:
        champion = await self.models.get_champion(market.id)
        if champion is None:
            return CalibrationFitOutcome(
                market_key=market.market_key, model_id=None, sample_count=0, fitted=False,
                reason="no champion model",
            )

        recorded_outcomes = await self.outcomes.list_by_market(market.id, limit=2000)
        samples: list[tuple[float, bool]] = []
        for outcome in recorded_outcomes:
            prediction = await self.predictions.get(outcome.prediction_id)
            if prediction is None or prediction.model_id != champion.id:
                continue
            is_positive = real_outcome_is_positive(market.market_key, prediction.value, outcome.error)
            if is_positive is None:
                continue
            # `prediction.probability` is P(`prediction.value`), not always P("positive") — undo
            # that read-back to recover the raw P("positive") sample the calibrator needs (see this
            # module's docstring). `real_label_is_positive` can't be None here: it's the same check
            # `real_outcome_is_positive` already made above to produce a non-None `is_positive`.
            value_is_positive = real_label_is_positive(market.market_key, prediction.value)
            raw_positive_probability = prediction.probability if value_is_positive else 1.0 - prediction.probability
            samples.append((raw_positive_probability, is_positive))

        if len(samples) < self.min_samples:
            return CalibrationFitOutcome(
                market_key=market.market_key, model_id=champion.id, sample_count=len(samples), fitted=False,
                reason=f"fewer than {self.min_samples} usable outcome samples",
            )

        await self.calibrator.fit(champion.id, samples)
        return CalibrationFitOutcome(
            market_key=market.market_key, model_id=champion.id, sample_count=len(samples), fitted=True,
        )
