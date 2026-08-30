from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.calibration_fitting_service import CalibrationFittingService
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    MarketDefinition,
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
from modules.predictions.infrastructure.calibration.platt_scaling_calibrator import PlattScalingCalibrator

T0 = datetime(2026, 8, 2, tzinfo=timezone.utc)
CONFIDENCE = ConfidenceBreakdown(*([0.7] * 9))
MARKET_KEY = "football.both_teams_to_score"  # real binary market outcome_label_mapper.py covers


def _market(market_key: str = MARKET_KEY) -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key=market_key, sport_code="football", name="Test",
        category="goals", market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


def _champion_model(market_id: MarketId) -> ModelDefinition:
    return ModelDefinition(
        id=ModelId(uuid4()), market_id=market_id, model_key="football.both_teams_to_score.logistic_regression",
        version=1, algorithm="logistic_regression", status=ModelStatus.CHAMPION,
    )


def _prediction(market_id: MarketId, model_id: ModelId, probability: float, value: str = "positive") -> Prediction:
    return Prediction(
        id=PredictionId(uuid4()), market_id=market_id, model_id=model_id, subject_ref=str(uuid4()),
        value=value, probability=probability, confidence=CONFIDENCE, explanation=ExplanationBundle(),
        feature_snapshot={}, model_version="1", status=PredictionStatus.PUBLISHED, generated_at=T0,
    )


async def _seed_outcomes(model_id, market_id, prediction_repo, prediction_outcome_repo, n, probability_fn, error_fn):
    """Every prediction claims "positive"; error_fn(i) determines whether that claim matched
    reality (0.0) or missed (1.0) — same real-outcome-recovery convention as the Dataset Builder
    tests, via real_outcome_is_positive."""
    for i in range(n):
        prediction = await prediction_repo.record(
            _prediction(market_id, model_id, probability_fn(i), value="positive")
        )
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                actual_value="btts_yes", error=error_fn(i), evaluated_at=T0,
            )
        )


@dataclass
class _CallCountingPredictionRepo:
    """Wraps a real `InMemoryPredictionRepository` to count calls — proves the fetch pattern
    itself, not just the end result, since a broken N+1 loop can produce the same final samples
    as a correctly batched one."""

    inner: object
    get_calls: int = field(default=0)
    get_many_calls: int = field(default=0)

    async def get(self, prediction_id):
        self.get_calls += 1
        return await self.inner.get(prediction_id)

    async def get_many(self, prediction_ids):
        self.get_many_calls += 1
        return await self.inner.get_many(prediction_ids)

    async def record(self, prediction):
        return await self.inner.record(prediction)

    async def update_status(self, prediction_id, status):
        return await self.inner.update_status(prediction_id, status)


@pytest.fixture
def calibrator():
    return PlattScalingCalibrator()


@pytest.fixture
def service(market_repo, model_repo, prediction_repo, prediction_outcome_repo, calibrator):
    return CalibrationFittingService(
        markets=market_repo, models=model_repo, predictions=prediction_repo,
        outcomes=prediction_outcome_repo, calibrator=calibrator, min_samples=20,
    )


class TestCalibrationFittingService:
    async def test_market_with_enough_real_outcomes_gets_fitted(
        self, service, market_repo, model_repo, prediction_repo, prediction_outcome_repo, calibrator
    ):
        market = await market_repo.upsert(_market())
        champion = await model_repo.upsert(_champion_model(market.id))
        # An overconfident model: always claims ~0.9, but is only actually right half the time —
        # a real signal PlattScalingCalibrator should pull toward the observed 0.5 rate.
        await _seed_outcomes(
            champion.id, market.id, prediction_repo, prediction_outcome_repo, n=40,
            probability_fn=lambda i: 0.9, error_fn=lambda i: 0.0 if i % 2 == 0 else 1.0,
        )

        results = await service.fit_all_production_markets(T0)

        assert len(results) == 1
        result = results[0]
        assert result.market_key == market.market_key
        assert result.model_id == champion.id
        assert result.sample_count == 40
        assert result.fitted is True
        assert result.reason is None

        calibrated = await calibrator.calibrate(champion.id, 0.9)
        assert calibrated < 0.9  # pulled down toward the true ~50% hit rate, not left at identity

    async def test_market_with_too_few_samples_is_not_fitted(
        self, service, market_repo, model_repo, prediction_repo, prediction_outcome_repo, calibrator
    ):
        market = await market_repo.upsert(_market())
        champion = await model_repo.upsert(_champion_model(market.id))
        await _seed_outcomes(
            champion.id, market.id, prediction_repo, prediction_outcome_repo, n=5,
            probability_fn=lambda i: 0.9, error_fn=lambda i: 0.0,
        )

        results = await service.fit_all_production_markets(T0)

        assert results[0].fitted is False
        assert results[0].sample_count == 5
        assert "20" in results[0].reason

        # Never fitted — calibrate() still the identity transform for this model.
        assert await calibrator.calibrate(champion.id, 0.9) == pytest.approx(0.9)

    async def test_market_with_no_champion_is_skipped(self, service, market_repo):
        market = await market_repo.upsert(_market())

        results = await service.fit_all_production_markets(T0)

        assert len(results) == 1
        assert results[0].market_key == market.market_key
        assert results[0].model_id is None
        assert results[0].fitted is False
        assert results[0].reason == "no champion model"

    async def test_only_champion_models_predictions_are_counted(
        self, service, market_repo, model_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        champion = await model_repo.upsert(_champion_model(market.id))
        retired_model_id = ModelId(uuid4())  # a superseded model — its old predictions must not count

        await _seed_outcomes(
            champion.id, market.id, prediction_repo, prediction_outcome_repo, n=25,
            probability_fn=lambda i: 0.7, error_fn=lambda i: 0.0,
        )
        await _seed_outcomes(
            retired_model_id, market.id, prediction_repo, prediction_outcome_repo, n=25,
            probability_fn=lambda i: 0.7, error_fn=lambda i: 0.0,
        )

        results = await service.fit_all_production_markets(T0)

        assert results[0].sample_count == 25

    async def test_recovers_raw_positive_probability_when_the_negative_side_won(
        self, service, market_repo, model_repo, prediction_repo, prediction_outcome_repo, calibrator
    ):
        """`Prediction.probability` is P(the published `value`), not always P("positive")
        (Universal Probability Engine) — when `value` is "negative"/"NO", the raw P("positive")
        sample fed to the calibrator must be `1 - prediction.probability`, not the stored value
        unchanged, or the calibration curve gets fit against inverted signal for every
        negative-side prediction."""
        market = await market_repo.upsert(_market())
        champion = await model_repo.upsert(_champion_model(market.id))
        # Every prediction claims "NO" (the negative side) with 0.9 confidence in that verdict —
        # i.e. raw P("positive") = 0.1 — and is actually right half the time.
        for i in range(40):
            prediction = await prediction_repo.record(
                _prediction(market.id, champion.id, probability=0.9, value="NO")
            )
            # real_outcome_is_positive: predicted "NO" (negative) + error 0.0 (claim matched) ->
            # real outcome was negative (not positive); error 1.0 (claim missed) -> outcome was
            # positive. Alternate so the recovered polarity has real spread, same shape as the
            # overconfident-model test above.
            await prediction_outcome_repo.record(
                PredictionOutcome(
                    id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                    actual_value="btts_no", error=0.0 if i % 2 == 0 else 1.0, evaluated_at=T0,
                )
            )

        results = await service.fit_all_production_markets(T0)

        assert results[0].sample_count == 40
        assert results[0].fitted is True
        # Raw P("positive") recovered from these samples is 0.1 (1 - 0.9), and the real outcome
        # was positive exactly half the time (mirroring the overconfident-model test's 50% hit
        # rate) — so calibrating 0.1 back should pull it UP toward that observed ~50%, the exact
        # mirror image of the "overconfident 0.9 pulled down" case, proving the recovery is
        # correctly inverted rather than silently reusing 0.9 as if it were P("positive").
        calibrated = await calibrator.calibrate(champion.id, 0.1)
        assert calibrated > 0.1

    async def test_unresolvable_market_never_fits_on_zero_samples(
        self, service, market_repo, model_repo, prediction_repo, prediction_outcome_repo
    ):
        """football.match_winner is 3-way — no positive/negative polarity exists to calibrate a
        binary transform against, so every outcome is unresolvable and nothing gets "fitted" on
        zero real samples."""
        market = await market_repo.upsert(_market(market_key="football.match_winner"))
        champion = await model_repo.upsert(_champion_model(market.id))
        await _seed_outcomes(
            champion.id, market.id, prediction_repo, prediction_outcome_repo, n=40,
            probability_fn=lambda i: 0.9, error_fn=lambda i: 0.0,
        )

        results = await service.fit_all_production_markets(T0)

        assert results[0].sample_count == 0
        assert results[0].fitted is False

    async def test_fetches_predictions_in_one_batch_not_one_call_per_outcome(
        self, market_repo, model_repo, prediction_repo, prediction_outcome_repo, calibrator
    ):
        """Real production incident (2026-08-30): calling `predictions.get()` once per outcome —
        up to 2000 per market — was an N+1 query pattern that alone accounted for
        `check_scheduled_calibration` blowing past its 300s task timeout. Must go through
        `get_many()` exactly once per market, and never call `get()` at all."""
        market = await market_repo.upsert(_market())
        champion = await model_repo.upsert(_champion_model(market.id))
        await _seed_outcomes(
            champion.id, market.id, prediction_repo, prediction_outcome_repo, n=40,
            probability_fn=lambda i: 0.9, error_fn=lambda i: 0.0,
        )
        counting_repo = _CallCountingPredictionRepo(inner=prediction_repo)
        service = CalibrationFittingService(
            markets=market_repo, models=model_repo, predictions=counting_repo,
            outcomes=prediction_outcome_repo, calibrator=calibrator, min_samples=20,
        )

        results = await service.fit_all_production_markets(T0)

        assert results[0].sample_count == 40
        assert counting_repo.get_calls == 0
        assert counting_repo.get_many_calls == 1
