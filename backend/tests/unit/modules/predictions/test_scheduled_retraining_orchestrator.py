from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.dataset_registry_service import DatasetRegistryService
from modules.predictions.application.experiment_tracking_service import ExperimentTrackingService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.model_selection_service import AutomaticModelSelectionService
from modules.predictions.application.scheduled_retraining_orchestrator import (
    SYSTEM_APPROVER,
    ScheduledRetrainingOrchestrator,
)
from modules.predictions.application.training_pipeline_service import RetrainingScheduler, TrainingPipelineService
from modules.predictions.domain.dataset import (
    Dataset,
    DatasetId,
    DatasetLineage,
    DatasetStatistics,
    DatasetStatus,
)
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    MarketDefinition,
    ModelDefinition,
    Prediction,
    PredictionOutcome,
)
from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.model_selection import CandidateSpec
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

T0 = datetime(2026, 8, 2, tzinfo=timezone.utc)

FAST_CANDIDATES = (
    CandidateSpec(MLAlgorithm.RANDOM_FOREST, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.LOGISTIC_REGRESSION, MLFramework.SKLEARN),
)

CONFIDENCE = ConfidenceBreakdown(*([0.7] * 9))


@dataclass
class _ExperimentRepoFake:
    store: dict = field(default_factory=dict)

    async def get(self, experiment_id):
        return self.store.get(experiment_id)

    async def record(self, experiment):
        self.store[experiment.id] = experiment
        return experiment

    async def update(self, experiment):
        self.store[experiment.id] = experiment
        return experiment

    async def list_by_market(self, market_id, limit=50):
        return [e for e in self.store.values() if e.market_id == market_id][:limit]


@dataclass
class _InMemoryArtifactStore:
    store: dict = field(default_factory=dict)

    async def save(self, key: str, payload: bytes) -> str:
        self.store[key] = payload
        return key

    async def load(self, ref: str) -> bytes:
        return self.store[ref]


def _market(market_key="football.both_teams_to_score") -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key=market_key, sport_code="football", name="Test",
        category="goals", market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


def _stale_dataset(market_id: MarketId, now: datetime) -> Dataset:
    return Dataset(
        id=DatasetId(uuid4()), market_id=market_id, version=1, content_hash="stale",
        samples=[], statistics=DatasetStatistics(sample_count=0, feature_count=0, positive_rate=None),
        lineage=DatasetLineage(market_id=market_id, source_prediction_ids=(), feature_keys=(), built_at=now - timedelta(days=8)),
        status=DatasetStatus.APPROVED, created_at=now - timedelta(days=8),
    )


def _fresh_dataset(market_id: MarketId, now: datetime) -> Dataset:
    return Dataset(
        id=DatasetId(uuid4()), market_id=market_id, version=1, content_hash="fresh",
        samples=[], statistics=DatasetStatistics(sample_count=0, feature_count=0, positive_rate=None),
        lineage=DatasetLineage(market_id=market_id, source_prediction_ids=(), feature_keys=(), built_at=now),
        status=DatasetStatus.APPROVED, created_at=now,
    )


async def _seed_champion(model_repo, market: MarketDefinition) -> ModelDefinition:
    """An already-live CHAMPION — the "this market has an established life" scenario every
    pre-existing test in this file assumes (staleness/drift retraining, human-gated promotion).
    Distinct from the bootstrap ("never trained") scenario the ML-architecture consolidation
    (2026-08-04) added, where a market genuinely has no CHAMPION row at all."""
    champion = ModelDefinition(
        id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.heuristic",
        version=1, algorithm="heuristic_logistic_v1", status=ModelStatus.CHAMPION,
    )
    return await model_repo.upsert(champion)


async def _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60):
    """Real, resolvable BTTS outcomes — half positive, half negative, with enough distinct
    feature values to avoid ZERO_VARIANCE_FEATURE/SEVERE_CLASS_IMBALANCE quality flags."""
    for i in range(n):
        prediction = Prediction(
            id=PredictionId(uuid4()), market_id=market.id, model_id=ModelId(uuid4()), subject_ref=f"fx-{i}",
            value="positive", probability=0.6, confidence=CONFIDENCE, explanation=ExplanationBundle(),
            feature_snapshot={"feature_a": float(i % 20), "feature_b": float((i * 3) % 17)},
            model_version="1", status=PredictionStatus.PUBLISHED, generated_at=T0,
        )
        await prediction_repo.record(prediction)
        error = 0.0 if i < n // 2 else 1.0  # half "matched", half "missed" -> ~50/50 real label split
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                actual_value="btts_yes" if error == 0.0 else "btts_no", error=error, evaluated_at=T0,
            )
        )


@pytest.fixture
def orchestrator(market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo):
    dataset_registry = DatasetRegistryService(datasets=dataset_repo)
    return ScheduledRetrainingOrchestrator(
        markets=market_repo,
        models=model_repo,
        scheduler=RetrainingScheduler(dataset_registry=dataset_registry),
        dataset_builder=DatasetBuilder(markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo),
        dataset_registry=dataset_registry,
        model_selection=AutomaticModelSelectionService(
            training_pipeline=TrainingPipelineService(),
            model_registry=ModelRegistryService(models=model_repo),
            experiments=ExperimentTrackingService(experiments=_ExperimentRepoFake()),
            artifact_store=_InMemoryArtifactStore(),
        ),
    )


class TestScheduledRetrainingOrchestrator:
    async def test_stale_market_with_enough_real_outcomes_produces_a_registered_challenger(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_stale_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.market_key == market.market_key
        assert result.should_retrain is True
        assert result.reason == "dataset stale"
        assert result.skipped_reason is None
        assert result.challenger is not None
        assert result.challenger.status is ModelStatus.CHALLENGER
        assert result.bootstrapped is False  # a live CHAMPION already existed — never auto-promoted

        persisted = await model_repo.get(result.challenger.id)
        assert persisted.status is ModelStatus.CHALLENGER

        # A new dataset version was built, validated, and system-approved — never a human gate
        # bypass, since approval is auditable via SYSTEM_APPROVER, not silently skipped.
        latest_dataset = await dataset_repo.get_latest_version(market.id)
        assert latest_dataset.version == 2
        assert latest_dataset.status is DatasetStatus.APPROVED
        assert latest_dataset.approved_by == SYSTEM_APPROVER

    async def test_fresh_market_with_no_drift_is_left_alone(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_fresh_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        assert outcomes[0].should_retrain is False
        assert outcomes[0].challenger is None
        # No new dataset version was built — the sweep genuinely skipped this market.
        latest_dataset = await dataset_repo.get_latest_version(market.id)
        assert latest_dataset.version == 1

    async def test_stale_market_with_too_few_real_outcomes_is_skipped_not_fabricated(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_stale_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=10)  # below MIN_TRAINING_SAMPLES

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.should_retrain is True
        assert result.challenger is None
        assert result.skipped_reason is not None
        assert "too_few_samples" in result.skipped_reason.lower() or "few" in result.skipped_reason.lower()

    async def test_one_markets_failure_does_not_block_the_rest_of_the_sweep(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        broken_market = await market_repo.upsert(_market(market_key="football.unmapped_market"))
        healthy_market = await market_repo.upsert(_market(market_key="football.both_teams_to_score"))
        await _seed_champion(model_repo, broken_market)
        await _seed_champion(model_repo, healthy_market)
        await dataset_repo.upsert(_stale_dataset(broken_market.id, T0))
        await dataset_repo.upsert(_stale_dataset(healthy_market.id, T0))
        # No outcome_label_mapper entry for "football.unmapped_market" -> every outcome is
        # unresolvable -> DatasetBuilder yields zero samples -> TOO_FEW_SAMPLES, not a crash.
        await _seed_outcomes(broken_market, prediction_repo, prediction_outcome_repo, n=60)
        await _seed_outcomes(healthy_market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        by_key = {o.market_key: o for o in outcomes}
        assert len(outcomes) == 2
        assert by_key["football.unmapped_market"].challenger is None
        assert by_key["football.unmapped_market"].skipped_reason is not None
        assert by_key["football.both_teams_to_score"].challenger is not None

    # -- Bootstrap: a market with no CHAMPION at all (ML-architecture consolidation, 2026-08-04) --

    async def test_market_with_no_champion_bootstraps_straight_to_champion(
        self, orchestrator, market_repo, model_repo, prediction_repo, prediction_outcome_repo
    ):
        """The "insufficient historical data" state (see `scripts/seed_football_markets.py`'s
        `NOT_YET_TRAINED_MARKET_KEYS`) — no CHAMPION, no dataset built yet. Real accumulated
        outcomes are enough to train on -> the first Challenger is auto-promoted to CHAMPION,
        the one exception to this orchestrator's human promotion gate."""
        market = await market_repo.upsert(_market())
        assert await model_repo.get_champion(market.id) is None
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.should_retrain is True
        assert result.reason == "never trained"
        assert result.skipped_reason is None
        assert result.challenger is not None
        assert result.bootstrapped is True

        persisted = await model_repo.get(result.challenger.id)
        assert persisted.status is ModelStatus.CHAMPION
        assert await model_repo.get_champion(market.id) == persisted

    async def test_market_with_no_champion_and_too_few_outcomes_is_skipped_not_promoted(
        self, orchestrator, market_repo, model_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=10)  # below MIN_TRAINING_SAMPLES

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.reason == "never trained"
        assert result.challenger is None
        assert result.bootstrapped is False
        assert result.skipped_reason is not None
        assert await model_repo.get_champion(market.id) is None  # still genuinely untrained, nothing fabricated

    async def test_market_with_no_champion_ignores_the_staleness_gate(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        """A never-trained market always gets a bootstrap attempt, even with a "fresh" dataset
        already on file (from, say, a prior failed bootstrap run) — should_retrain()'s
        staleness/drift check has no live CHAMPION to compare against and would otherwise report
        "nothing to do" forever."""
        market = await market_repo.upsert(_market())
        await dataset_repo.upsert(_fresh_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.should_retrain is True
        assert result.bootstrapped is True
        assert await model_repo.get_champion(market.id) is not None
