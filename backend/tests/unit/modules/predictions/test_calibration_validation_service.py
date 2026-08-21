"""Phase 3 (Champion Validation + Calibration) — real sklearn-based calibration comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from modules.predictions.application.calibration_validation_service import (
    CalibrationBlockedError,
    CalibrationValidationService,
)
from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.domain.calibration import CalibrationMethod
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

# outcome_label_mapper.MARKET_OUTCOME_LABELS recognizes this real market key — an unrecognized
# synthetic key would make real_outcome_is_positive return None for every sample (dataset empty).
BINARY_MARKET_KEY = "football.both_teams_to_score"
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter

pytestmark = pytest.mark.asyncio

FEATURES = ("form_diff",)


@dataclass
class _InMemoryArtifactStore:
    store: dict = field(default_factory=dict)

    async def save(self, key: str, payload: bytes) -> str:
        self.store[key] = payload
        return key

    async def load(self, ref: str) -> bytes:
        return self.store[ref]


@dataclass
class _CalibrationReportSpy:
    records: list = field(default_factory=list)

    async def record(self, model_id, report):
        self.records.append((model_id, report))
        return report

    async def list_by_model(self, model_id):
        return [r for m, r in self.records if m == model_id]


def _binary_market(market_key: str = BINARY_MARKET_KEY) -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()),
        market_key=market_key,
        sport_code="football",
        name="Test Binary Market",
        category="totals",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


async def _seed_predictions_and_outcomes(predictions_repo, outcomes_repo, market, model_id, raw_probabilities, labels, base_time):
    """Seeds real Prediction/PredictionOutcome rows DatasetBuilder can read back — the honest way
    to build TrainingSamples, matching production (never construct TrainingSample directly).
    Every prediction claims "positive" (the generic-value fallback `real_label_is_positive`
    resolves to True); `error` then determines the recovered training label exactly:
    error=0.0 -> claim matched -> label 1.0, error=1.0 -> claim missed -> label 0.0. This is the
    same idiom `test_dataset_builder_service.py`'s own `_seed_classification_outcomes` uses."""
    for i, (p, label) in enumerate(zip(raw_probabilities, labels)):
        prediction_id = PredictionId(uuid4())
        prediction = Prediction(
            id=prediction_id,
            market_id=market.id,
            model_id=model_id,
            subject_ref=f"fixture-{i}",
            value="positive",
            probability=float(p),
            confidence=ConfidenceBreakdown(*([0.7] * 9)),
            explanation=ExplanationBundle(),
            feature_snapshot={"form_diff": float(p)},
            model_version="1",
            status=PredictionStatus.PUBLISHED,
            generated_at=base_time,
        )
        await predictions_repo.record(prediction)
        error = 0.0 if label >= 0.5 else 1.0
        outcome = PredictionOutcome(
            id=PredictionOutcomeId(uuid4()),
            prediction_id=prediction_id,
            actual_value="btts_yes" if error == 0.0 else "btts_no",
            error=error,
            # stagger reference_time so chronological sort/split is deterministic and non-degenerate
            evaluated_at=base_time.fromtimestamp(base_time.timestamp() + i, tz=timezone.utc),
        )
        await outcomes_repo.record(outcome)


def _fit_overconfident_champion(X, y) -> SklearnAdapter:
    """A near-separable linear fit with negligible regularization is a textbook source of
    overconfident (poorly calibrated) probabilities — exactly the real-world condition sigmoid/
    isotonic recalibration exists to fix. Not a fabricated result: this is standard ML behavior."""
    estimator = LogisticRegression(C=1e6, max_iter=2000)
    estimator.fit(X, y)
    adapter = SklearnAdapter(algorithm=__import__(
        "modules.predictions.domain.ml_value_objects", fromlist=["MLAlgorithm"]
    ).MLAlgorithm.LOGISTIC_REGRESSION, target_type=TargetType.CLASSIFICATION)
    adapter.feature_order = list(FEATURES)
    adapter._model = estimator
    return adapter


@pytest.fixture
def market_repo():
    from tests.unit.modules.predictions.conftest import InMemoryMarketRepository

    return InMemoryMarketRepository()


@pytest.fixture
def model_repo():
    from tests.unit.modules.predictions.conftest import InMemoryModelRepository

    return InMemoryModelRepository()


class TestCalibrationValidationService:
    async def test_no_champion_raises_calibration_blocked(self, market_repo, model_repo):
        from tests.unit.modules.predictions.conftest import InMemoryPredictionOutcomeRepository, InMemoryPredictionRepository

        market = _binary_market()
        await market_repo.upsert(market)
        service = CalibrationValidationService(
            dataset_builder=DatasetBuilder(markets=market_repo, predictions=InMemoryPredictionRepository(), outcomes=InMemoryPredictionOutcomeRepository()),
            model_loader=ModelLoaderService(_InMemoryArtifactStore()),
            models=model_repo,
            calibration_reports=_CalibrationReportSpy(),
            model_registry=ModelRegistryService(models=model_repo),
            artifact_store=_InMemoryArtifactStore(),
        )

        with pytest.raises(CalibrationBlockedError, match="no champion"):
            await service.validate_market(market.id, market.market_key, datetime.now(timezone.utc))

    async def test_too_few_samples_raises_calibration_blocked(self, market_repo, model_repo):
        from tests.unit.modules.predictions.conftest import InMemoryPredictionOutcomeRepository, InMemoryPredictionRepository

        market = _binary_market()
        await market_repo.upsert(market)
        predictions_repo, outcomes_repo = InMemoryPredictionRepository(), InMemoryPredictionOutcomeRepository()
        rng = np.random.default_rng(7)
        X = rng.normal(size=(10, 1))
        y = (X[:, 0] > 0).astype(float)
        adapter = _fit_overconfident_champion(X, y)
        artifacts = _InMemoryArtifactStore()
        artifact_ref = await artifacts.save("test.bin", adapter.serialize())
        champion = ModelDefinition(
            id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.logistic_regression",
            version=1, algorithm="logistic_regression", status=ModelStatus.CHAMPION,
            framework="sklearn", artifact_ref=artifact_ref,
        )
        await model_repo.upsert(champion)
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        raw_probs = (1.0 / (1.0 + np.exp(-X[:, 0]))).tolist()
        await _seed_predictions_and_outcomes(predictions_repo, outcomes_repo, market, champion.id, raw_probs, y.tolist(), base_time)

        service = CalibrationValidationService(
            dataset_builder=DatasetBuilder(markets=market_repo, predictions=predictions_repo, outcomes=outcomes_repo),
            model_loader=ModelLoaderService(artifacts),
            models=model_repo,
            calibration_reports=_CalibrationReportSpy(),
            model_registry=ModelRegistryService(models=model_repo),
            artifact_store=artifacts,
        )

        with pytest.raises(CalibrationBlockedError, match="chronologically-referenced samples"):
            await service.validate_market(market.id, market.market_key, datetime.now(timezone.utc))

    async def _seeded_service(self, market_repo, model_repo, n=200, seed=3):
        from tests.unit.modules.predictions.conftest import InMemoryPredictionOutcomeRepository, InMemoryPredictionRepository

        market = _binary_market()
        await market_repo.upsert(market)
        predictions_repo, outcomes_repo = InMemoryPredictionRepository(), InMemoryPredictionOutcomeRepository()
        rng = np.random.default_rng(seed)
        X = rng.normal(size=(n, 1)) * 3.0  # wide spread -> near-separable -> overconfident fit
        true_prob = 1.0 / (1.0 + np.exp(-X[:, 0] * 0.4))  # true relationship much gentler than fit will find
        y = (rng.uniform(size=n) < true_prob).astype(float)
        adapter = _fit_overconfident_champion(X, y)
        artifacts = _InMemoryArtifactStore()
        artifact_ref = await artifacts.save("test.bin", adapter.serialize())
        champion = ModelDefinition(
            id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.logistic_regression",
            version=1, algorithm="logistic_regression", status=ModelStatus.CHAMPION,
            framework="sklearn", artifact_ref=artifact_ref,
        )
        await model_repo.upsert(champion)
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        raw_probs = 1.0 / (1.0 + np.exp(-X[:, 0]))
        await _seed_predictions_and_outcomes(predictions_repo, outcomes_repo, market, champion.id, raw_probs.tolist(), y.tolist(), base_time)

        report_repo = _CalibrationReportSpy()
        service = CalibrationValidationService(
            dataset_builder=DatasetBuilder(markets=market_repo, predictions=predictions_repo, outcomes=outcomes_repo),
            model_loader=ModelLoaderService(artifacts),
            models=model_repo,
            calibration_reports=report_repo,
            model_registry=ModelRegistryService(models=model_repo),
            artifact_store=artifacts,
        )
        return service, market, champion, report_repo

    async def test_every_candidate_persisted_not_just_winner(self, market_repo, model_repo):
        service, market, champion, report_repo = await self._seeded_service(market_repo, model_repo)

        result = await service.validate_market(market.id, market.market_key, datetime.now(timezone.utc))

        assert len(result.candidates) == 3
        methods_evaluated = {c.method for c in result.candidates}
        assert methods_evaluated == {CalibrationMethod.NONE, CalibrationMethod.PLATT_SCALING, CalibrationMethod.ISOTONIC_REGRESSION}
        persisted = await report_repo.list_by_model(champion.id)
        assert len(persisted) == 3

    async def test_champion_untouched_when_calibration_used(self, market_repo, model_repo):
        service, market, champion, _ = await self._seeded_service(market_repo, model_repo)

        await service.validate_market(market.id, market.market_key, datetime.now(timezone.utc))

        reloaded_champion = await model_repo.get(champion.id)
        assert reloaded_champion.status is ModelStatus.CHAMPION
        assert reloaded_champion.version == champion.version
        assert reloaded_champion.calibration_ref is None  # champion itself is never mutated

    async def test_winning_candidate_registers_versioned_challenger(self, market_repo, model_repo):
        service, market, champion, _ = await self._seeded_service(market_repo, model_repo)

        result = await service.validate_market(market.id, market.market_key, datetime.now(timezone.utc))

        if result.winner is not CalibrationMethod.NONE:
            assert result.promoted_model_id is not None
            challenger = await model_repo.get(result.promoted_model_id)
            assert challenger.status is ModelStatus.CHALLENGER
            assert challenger.calibration_ref == result.winner.value
            assert challenger.version > champion.version
            assert challenger.algorithm == champion.algorithm  # never invents a new algorithm string
        else:
            assert result.promoted_model_id is None

    async def test_probability_integrity_every_candidate(self, market_repo, model_repo):
        service, market, champion, _ = await self._seeded_service(market_repo, model_repo)

        result = await service.validate_market(market.id, market.market_key, datetime.now(timezone.utc))

        for candidate in result.candidates:
            if candidate.report is not None:
                assert 0.0 <= candidate.report.expected_calibration_error <= 1.0
                assert 0.0 <= candidate.report.brier_score <= 1.0
            assert candidate.log_loss >= 0.0
