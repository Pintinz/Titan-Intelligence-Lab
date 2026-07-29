from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.experiment_tracking_service import ExperimentTrackingService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.model_selection_service import AutomaticModelSelectionService
from modules.predictions.application.training_pipeline_service import TrainingPipelineService
from modules.predictions.domain.dataset import Dataset, DatasetId, DatasetLineage, DatasetStatistics, DatasetStatus
from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.model_selection import CandidateSpec, NoViableCandidateError
from modules.predictions.domain.value_objects import MarketId, ModelStatus, TargetType
from modules.predictions.ports.ml_model import TrainingSample

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)

FAST_CLASSIFICATION_CANDIDATES = (
    CandidateSpec(MLAlgorithm.RANDOM_FOREST, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.LOGISTIC_REGRESSION, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.GAUSSIAN_NB, MLFramework.SKLEARN),
)


def _classification_dataset(n: int = 60, status: DatasetStatus = DatasetStatus.APPROVED) -> Dataset:
    samples = [
        TrainingSample(features={"x1": float(i % 10) - 5.0, "x2": float((i * 3) % 10) - 5.0}, label=1.0 if (i % 10 - 5) + ((i * 3) % 10 - 5) > 0 else 0.0)
        for i in range(n)
    ]
    feature_order = ["x1", "x2"]
    return Dataset(
        id=DatasetId(uuid4()),
        market_id=MarketId(uuid4()),
        version=1,
        content_hash="hash",
        samples=samples,
        statistics=DatasetStatistics(sample_count=n, feature_count=2, positive_rate=0.5),
        lineage=DatasetLineage(market_id=MarketId(uuid4()), source_prediction_ids=(), feature_keys=tuple(feature_order), built_at=T0),
        status=status,
        created_at=T0,
    )


@pytest.fixture
def service(model_repo, experiment_repo_fake):
    return AutomaticModelSelectionService(
        training_pipeline=TrainingPipelineService(),
        model_registry=ModelRegistryService(models=model_repo),
        experiments=ExperimentTrackingService(experiments=experiment_repo_fake),
    )


@pytest.fixture
def experiment_repo_fake():
    from dataclasses import dataclass, field

    @dataclass
    class _Repo:
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

    return _Repo()


class TestSelect:
    async def test_ranks_candidates_and_returns_a_winner(self, service):
        dataset = _classification_dataset()

        result = await service.select(dataset, TargetType.CLASSIFICATION, candidates=FAST_CLASSIFICATION_CANDIDATES)

        assert result.winning_candidate in FAST_CLASSIFICATION_CANDIDATES
        assert result.ranking_metric == "accuracy"
        assert 0.0 <= result.ranking_value <= 1.0
        assert result.winning_model.is_fitted()

    @pytest.mark.parametrize(
        "framework", [MLFramework.LIGHTGBM, MLFramework.XGBOOST, MLFramework.CATBOOST]
    )
    async def test_builds_the_right_adapter_per_boosting_framework(self, service, framework):
        algorithm = {
            MLFramework.LIGHTGBM: MLAlgorithm.LIGHTGBM_GBM,
            MLFramework.XGBOOST: MLAlgorithm.XGBOOST_GBM,
            MLFramework.CATBOOST: MLAlgorithm.CATBOOST_GBM,
        }[framework]
        dataset = _classification_dataset()

        result = await service.select(
            dataset, TargetType.CLASSIFICATION, candidates=(CandidateSpec(algorithm, framework),)
        )

        assert result.winning_candidate.framework is framework
        assert result.winning_model.is_fitted()

    async def test_regression_ranking_picks_lowest_mae_among_two_viable_candidates(self, service):
        dataset = _classification_dataset()
        dataset.samples = [
            TrainingSample(features=s.features, label=float(s.label) * 10.0) for s in dataset.samples
        ]

        result = await service.select(
            dataset,
            TargetType.REGRESSION,
            candidates=(
                CandidateSpec(MLAlgorithm.RIDGE, MLFramework.SKLEARN),
                CandidateSpec(MLAlgorithm.RANDOM_FOREST, MLFramework.SKLEARN),
            ),
        )

        assert result.ranking_metric == "mae"
        assert result.winning_candidate.algorithm in {MLAlgorithm.RIDGE, MLAlgorithm.RANDOM_FOREST}

    async def test_candidate_with_empty_test_split_is_skipped_not_selected(self, service):
        dataset = _classification_dataset()

        with pytest.raises(NoViableCandidateError):
            await service.select(
                dataset, TargetType.CLASSIFICATION, candidates=FAST_CLASSIFICATION_CANDIDATES, test_ratio=0.0
            )

    async def test_unsupported_algorithm_for_target_type_is_skipped_not_fatal(self, service):
        dataset = _classification_dataset()
        dataset.statistics = DatasetStatistics(sample_count=60, feature_count=2, positive_rate=0.5)
        # GAUSSIAN_NB has no regression form — selecting for REGRESSION should skip it, not raise.
        regression_dataset = _classification_dataset()
        regression_dataset.samples = [
            TrainingSample(features=s.features, label=float(s.label) * 10.0) for s in regression_dataset.samples
        ]

        result = await service.select(
            regression_dataset,
            TargetType.REGRESSION,
            candidates=(
                CandidateSpec(MLAlgorithm.GAUSSIAN_NB, MLFramework.SKLEARN),
                CandidateSpec(MLAlgorithm.RIDGE, MLFramework.SKLEARN),
            ),
        )

        assert result.winning_candidate.algorithm is MLAlgorithm.RIDGE
        assert any(c.algorithm is MLAlgorithm.GAUSSIAN_NB for c, _ in result.skipped_candidates)

    async def test_no_viable_candidate_raises_when_split_leaves_too_few_training_samples(self, service):
        # Exactly MIN_TRAINING_SAMPLES(30) overall, but TRAIN_TEST's default 0.2 test_ratio leaves
        # only 24 training rows post-split — every candidate's fit() legitimately refuses that.
        dataset = _classification_dataset(n=30)

        with pytest.raises(NoViableCandidateError):
            await service.select(dataset, TargetType.CLASSIFICATION, candidates=FAST_CLASSIFICATION_CANDIDATES)

    async def test_default_roster_used_when_none_supplied(self, service):
        dataset = _classification_dataset(n=45)
        result = await service.select(dataset, TargetType.CLASSIFICATION, candidates=FAST_CLASSIFICATION_CANDIDATES)
        assert len(result.all_candidates) == len(FAST_CLASSIFICATION_CANDIDATES)


class TestSelectAndRegisterChallenger:
    async def test_registers_and_promotes_winner_to_challenger(self, service, model_repo):
        dataset = _classification_dataset()

        challenger, selection = await service.select_and_register_challenger(
            market_id=dataset.market_id,
            dataset=dataset,
            target_type=TargetType.CLASSIFICATION,
            model_key_prefix="football.match_result",
            next_version=1,
            now=T0,
            candidates=FAST_CLASSIFICATION_CANDIDATES,
        )

        assert challenger.status is ModelStatus.CHALLENGER
        assert challenger.framework == selection.winning_candidate.framework.value
        assert challenger.algorithm == selection.winning_candidate.algorithm.value
        assert challenger.dataset_version == dataset.version
        assert challenger.trained_at == T0

        persisted = await model_repo.get(challenger.id)
        assert persisted.status is ModelStatus.CHALLENGER

    async def test_records_a_model_selection_experiment(self, service):
        dataset = _classification_dataset()

        _, selection = await service.select_and_register_challenger(
            market_id=dataset.market_id,
            dataset=dataset,
            target_type=TargetType.CLASSIFICATION,
            model_key_prefix="football.match_result",
            next_version=1,
            now=T0,
            candidates=FAST_CLASSIFICATION_CANDIDATES,
        )

        experiments = await service.experiments.compare(dataset.market_id)
        assert len(experiments) == 1
        assert experiments[0].config["kind"] == "model_selection"
        assert experiments[0].config["winning_algorithm"] == selection.winning_candidate.algorithm.value
