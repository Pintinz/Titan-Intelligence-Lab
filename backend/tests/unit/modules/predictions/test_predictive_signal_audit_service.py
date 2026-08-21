from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.features.domain.entities import FeatureDefinition
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
)
from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.predictive_signal_audit_service import (
    MarketNotFoundError,
    PredictiveSignalAuditService,
)
from modules.predictions.application.training_preflight_service import TrainingPreflightService
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    Experiment,
    ExplanationBundle,
    FeatureMarketMapping,
    MarketDefinition,
    ModelDefinition,
    ModelEvaluation,
    Prediction,
    PredictionOutcome,
)
from modules.predictions.domain.value_objects import (
    ExperimentId,
    FeatureMarketMappingId,
    MarketId,
    MarketKind,
    MarketStatus,
    ModelEvaluationId,
    ModelId,
    ModelStatus,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)

T0 = datetime(2026, 8, 17, tzinfo=timezone.utc)
MARKET_KEY = "football.audit_test_market"


@pytest.fixture
def builder(market_repo, prediction_repo, prediction_outcome_repo):
    return DatasetBuilder(markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo)


@pytest.fixture
def preflight(market_repo, feature_mapping_repo, feature_definition_repo, builder, dataset_repo):
    return TrainingPreflightService(
        markets=market_repo,
        mappings=feature_mapping_repo,
        feature_definitions=feature_definition_repo,
        dataset_builder=builder,
        dataset_repo=dataset_repo,
    )


@pytest.fixture
def service(
    market_repo, feature_mapping_repo, feature_definition_repo, dataset_repo, model_repo,
    model_evaluation_repo, prediction_repo, prediction_outcome_repo, experiment_repo, preflight,
):
    return PredictiveSignalAuditService(
        markets=market_repo,
        mappings=feature_mapping_repo,
        feature_definitions=feature_definition_repo,
        dataset_repo=dataset_repo,
        models=model_repo,
        model_evaluations=model_evaluation_repo,
        predictions=prediction_repo,
        outcomes=prediction_outcome_repo,
        experiments=experiment_repo,
        preflight=preflight,
    )


async def _market(market_repo, key: str = MARKET_KEY, sport_code: str = "football") -> MarketDefinition:
    market = MarketDefinition(
        id=MarketId(uuid4()),
        market_key=key,
        sport_code=sport_code,
        name="Audit Test Market",
        category="match_outcome",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.REGRESSION,
        status=MarketStatus.PRODUCTION,
    )
    return await market_repo.upsert(market)


def _prediction(market_id, feature_snapshot, value):
    return Prediction(
        id=PredictionId(uuid4()),
        market_id=market_id,
        model_id=ModelId(uuid4()),
        subject_ref="fixture-1",
        value=value,
        probability=0.6,
        confidence=ConfidenceBreakdown(*([0.7] * 9)),
        explanation=ExplanationBundle(),
        feature_snapshot=feature_snapshot,
        model_version="1",
        status=PredictionStatus.PUBLISHED,
        generated_at=T0,
    )


async def _seed(market, prediction_repo, prediction_outcome_repo, n, feature_fn, ref_time_fn=None):
    ref_time_fn = ref_time_fn or (lambda i: T0)
    for i in range(n):
        prediction = await prediction_repo.record(_prediction(market.id, feature_fn(i), value=f"{float(i):.4f}"))
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                actual_value=f"{float(i):.4f}", error=0.0, evaluated_at=ref_time_fn(i),
            )
        )


async def _feature(
    feature_definition_repo, key: str, status: FeatureStatus = FeatureStatus.ACTIVE,
    leakage_classification: str = "PRE_MATCH_SAFE",
) -> FeatureDefinition:
    definition = FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey(key),
        name=key,
        description="test feature",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="test",
        data_type=FeatureDataType.FLOAT,
        owner="data-team",
        entity_type=EntityType.FIXTURE,
        status=status,
        leakage_classification=leakage_classification,
    )
    return await feature_definition_repo.upsert(definition)


async def _map(feature_mapping_repo, market_id, feature_key: str, is_required: bool = True):
    mapping = FeatureMarketMapping(
        id=FeatureMarketMappingId(uuid4()), market_id=market_id, feature_key=feature_key, is_required=is_required,
    )
    return await feature_mapping_repo.upsert(mapping)


class TestChampionMarket:
    async def test_populates_every_field(
        self, service, market_repo, feature_mapping_repo, feature_definition_repo, prediction_repo,
        prediction_outcome_repo, dataset_repo, model_repo, model_evaluation_repo, experiment_repo,
    ):
        market = await _market(market_repo)
        await _feature(feature_definition_repo, "core.feature_a")
        await _map(feature_mapping_repo, market.id, "core.feature_a")
        await _seed(
            market, prediction_repo, prediction_outcome_repo, 40,
            feature_fn=lambda i: {"core.feature_a": float(i)},
            ref_time_fn=lambda i: T0.replace(hour=i % 24),
        )
        dataset = await DatasetBuilder(
            markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo
        ).build(market.id, T0)
        await dataset_repo.upsert(dataset)

        champion = ModelDefinition(
            id=ModelId(uuid4()), market_id=market.id, model_key="football.audit_test_market.lightgbm",
            version=1, algorithm="lightgbm_gbm", framework="lightgbm", status=ModelStatus.CHAMPION,
            artifact_ref="artifacts/x.bin", trained_at=T0,
        )
        await model_repo.upsert(champion)
        await model_evaluation_repo.record(
            ModelEvaluation(
                id=ModelEvaluationId(uuid4()), model_id=champion.id, evaluated_at=T0,
                metrics={"mae": 2.5}, calibration_report={"ece": 0.05},
            )
        )

        experiment = Experiment(
            id=ExperimentId(uuid4()), market_id=market.id, created_at=T0,
            config={
                "kind": "model_selection", "baseline_candidates": ["ridge"],
                "winning_algorithm": "lightgbm_gbm", "winner_is_baseline": False,
            },
            metrics={"ranking.mae": 2.5, "candidate.ridge": 3.1, "candidate.lightgbm_gbm": 2.5},
        )
        await experiment_repo.record(experiment)

        record = await service.audit_market(MARKET_KEY, T0)

        assert record.has_persisted_dataset is True
        assert record.sample_count == 40
        assert record.required_feature_keys == ("core.feature_a",)
        assert record.preflight_ready is True
        assert record.champion_model_key == "football.audit_test_market.lightgbm"
        assert record.champion_algorithm == "lightgbm_gbm"
        assert record.champion_is_genuinely_trained is True
        assert record.champion_latest_evaluation_metrics == {"mae": 2.5}
        assert record.champion_latest_calibration_report == {"ece": 0.05}
        assert record.prediction_count == 40
        assert record.outcome_count == 40
        assert record.baseline_candidate_algorithms == ("ridge",)
        assert record.winner_is_baseline is False
        assert record.winning_algorithm == "lightgbm_gbm"
        assert record.candidate_scores == {"ridge": 3.1, "lightgbm_gbm": 2.5}
        assert record.ranking_metric == "mae"
        assert record.ranking_value == 2.5


class TestNoDatasetEverBuilt:
    async def test_graceful_defaults_no_build_triggered(self, service, market_repo):
        await _market(market_repo)

        record = await service.audit_market(MARKET_KEY, T0, include_preflight=False)

        assert record.has_persisted_dataset is False
        assert record.sample_count is None
        assert record.missing_rate == {}
        assert record.preflight_ready is None
        assert record.preflight_checks is None


class TestNoChampion:
    async def test_champion_fields_default(self, service, market_repo):
        await _market(market_repo)

        record = await service.audit_market(MARKET_KEY, T0, include_preflight=False)

        assert record.champion_model_key is None
        assert record.champion_algorithm is None
        assert record.champion_latest_evaluation_metrics == {}


class TestZeroFixtureMarket:
    async def test_fully_empty_but_valid_record(self, service, market_repo):
        """Shaped like table tennis in the real catalog — market registered, but zero real
        predictions/outcomes/dataset/champion/experiment ever recorded for it."""
        await _market(market_repo, sport_code="table_tennis")

        record = await service.audit_market(MARKET_KEY, T0, include_preflight=True)

        assert record.sport_code == "table_tennis"
        assert record.has_persisted_dataset is False
        assert record.prediction_count == 0
        assert record.outcome_count == 0
        assert record.preflight_ready is False  # market has no feature manifest / observations at all


class TestIncludePreflightToggle:
    async def test_only_preflight_fields_differ(self, service, market_repo):
        await _market(market_repo)

        with_preflight = await service.audit_market(MARKET_KEY, T0, include_preflight=True)
        without_preflight = await service.audit_market(MARKET_KEY, T0, include_preflight=False)

        assert with_preflight.preflight_ready is not None
        assert without_preflight.preflight_ready is None
        assert without_preflight.preflight_checks is None
        assert with_preflight.sport_code == without_preflight.sport_code
        assert with_preflight.prediction_count == without_preflight.prediction_count


class TestMarketNotFound:
    async def test_raises(self, service):
        with pytest.raises(MarketNotFoundError):
            await service.audit_market("football.does_not_exist", T0)


class TestAuditAll:
    async def test_one_record_per_market_no_duplicates(self, service, market_repo):
        await _market(market_repo, key="football.audit_all_a")
        await _market(market_repo, key="football.audit_all_b")
        await _market(market_repo, key="football.audit_all_c")

        records = await service.audit_all(T0, include_preflight=False)

        assert {r.market_key for r in records} == {
            "football.audit_all_a", "football.audit_all_b", "football.audit_all_c",
        }
        assert len(records) == 3
