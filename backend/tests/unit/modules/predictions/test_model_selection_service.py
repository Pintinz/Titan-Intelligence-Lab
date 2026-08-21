from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.experiment_tracking_service import ExperimentTrackingService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.model_selection_service import (
    DEFAULT_CLASSIFICATION_CANDIDATES,
    DEFAULT_REGRESSION_CANDIDATES,
    AutomaticModelSelectionService,
)
from modules.predictions.application.training_pipeline_service import TrainingPipelineService
from modules.predictions.domain.dataset import Dataset, DatasetId, DatasetLineage, DatasetStatistics, DatasetStatus, SplitStrategy
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
    # Milestone 18: select()'s default split strategy is TIME_SERIES_SPLIT, which now fails closed
    # without a real reference_time on every sample — give each a strictly increasing timestamp
    # (built already in chronological order; test_dataset_splitter.py separately proves the
    # splitter is correct even for shuffled input).
    samples = [
        TrainingSample(
            features={"x1": float(i % 10) - 5.0, "x2": float((i * 3) % 10) - 5.0},
            label=1.0 if (i % 10 - 5) + ((i * 3) % 10 - 5) > 0 else 0.0,
            reference_time=T0 + timedelta(hours=i),
        )
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


MULTICLASS_LABELS = ("LOW", "MID", "HIGH")


def _multiclass_dataset(n: int = 90, status: DatasetStatus = DatasetStatus.APPROVED) -> Dataset:
    """(2026-08-06) x1 alone linearly separates 3 classes — class index is the label, decoded back
    through `MULTICLASS_LABELS` the same way football.match_winner/football.correct_score do."""
    samples = []
    for i in range(n):
        x1 = float(i % 10) - 5.0
        x2 = float((i * 3) % 10) - 5.0
        class_index = 0 if x1 < -1.5 else (2 if x1 > 1.5 else 1)
        samples.append(
            TrainingSample(
                features={"x1": x1, "x2": x2}, label=float(class_index), reference_time=T0 + timedelta(hours=i)
            )
        )
    return Dataset(
        id=DatasetId(uuid4()),
        market_id=MarketId(uuid4()),
        version=1,
        content_hash="hash",
        samples=samples,
        statistics=DatasetStatistics(sample_count=n, feature_count=2, positive_rate=None),
        lineage=DatasetLineage(
            market_id=MarketId(uuid4()), source_prediction_ids=(), feature_keys=("x1", "x2"), built_at=T0,
            class_labels=MULTICLASS_LABELS,
        ),
        status=status,
        created_at=T0,
    )


def _count_regression_dataset(n: int = 60, status: DatasetStatus = DatasetStatus.APPROVED) -> Dataset:
    """Non-negative, count-shaped labels — `PoissonRegressor`/`TweedieRegressor` require `y >= 0`,
    unlike `_classification_dataset`'s signed regression variant used elsewhere in this file."""
    samples = [
        TrainingSample(
            features={"x1": float(i % 10), "x2": float((i * 2) % 10)},
            label=max(0.0, round(0.5 * (i % 10) + 0.3 * ((i * 2) % 10))),
            reference_time=T0 + timedelta(hours=i),
        )
        for i in range(n)
    ]
    feature_order = ["x1", "x2"]
    return Dataset(
        id=DatasetId(uuid4()),
        market_id=MarketId(uuid4()),
        version=1,
        content_hash="hash",
        samples=samples,
        statistics=DatasetStatistics(sample_count=n, feature_count=2, positive_rate=None),
        lineage=DatasetLineage(market_id=MarketId(uuid4()), source_prediction_ids=(), feature_keys=tuple(feature_order), built_at=T0),
        status=status,
        created_at=T0,
    )


@dataclass
class _InMemoryArtifactStore:
    store: dict = field(default_factory=dict)

    async def save(self, key: str, payload: bytes) -> str:
        self.store[key] = payload
        return key

    async def load(self, ref: str) -> bytes:
        return self.store[ref]


@pytest.fixture
def artifact_store():
    return _InMemoryArtifactStore()


@pytest.fixture
def service(model_repo, experiment_repo_fake, artifact_store):
    return AutomaticModelSelectionService(
        training_pipeline=TrainingPipelineService(),
        model_registry=ModelRegistryService(models=model_repo),
        experiments=ExperimentTrackingService(experiments=experiment_repo_fake),
        artifact_store=artifact_store,
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


@pytest.fixture
def training_run_repo_fake():
    @dataclass
    class _Repo:
        store: dict = field(default_factory=dict)

        async def record(self, run):
            self.store[run.id] = run
            return run

        async def get(self, run_id):
            return self.store.get(run_id)

        async def list_by_market(self, market_id, limit=50):
            return [r for r in self.store.values() if r.market_id == market_id][:limit]

    return _Repo()


@pytest.fixture
def service_with_training_runs(model_repo, experiment_repo_fake, artifact_store, training_run_repo_fake):
    return AutomaticModelSelectionService(
        training_pipeline=TrainingPipelineService(),
        model_registry=ModelRegistryService(models=model_repo),
        experiments=ExperimentTrackingService(experiments=experiment_repo_fake),
        artifact_store=artifact_store,
        training_runs=training_run_repo_fake,
    )


class TestSelect:
    async def test_ranks_candidates_and_returns_a_winner(self, service):
        dataset = _classification_dataset()

        result = await service.select(dataset, TargetType.CLASSIFICATION, candidates=FAST_CLASSIFICATION_CANDIDATES)

        assert result.winning_candidate in FAST_CLASSIFICATION_CANDIDATES
        assert result.ranking_metric == "log_loss"
        assert result.ranking_value >= 0.0
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
            TrainingSample(features=s.features, label=float(s.label) * 10.0, reference_time=s.reference_time) for s in dataset.samples
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

        # Milestone 4: `select()`'s default split strategy is now TIME_SERIES_SPLIT (Rule 14 —
        # random TRAIN_TEST is no longer the production default). This test is specifically
        # about TRAIN_TEST's own `test_ratio=0.0` edge case, so it requests that strategy
        # explicitly — exactly the escape hatch the milestone's own default-flip preserves.
        with pytest.raises(NoViableCandidateError):
            await service.select(
                dataset, TargetType.CLASSIFICATION, candidates=FAST_CLASSIFICATION_CANDIDATES,
                split_strategy=SplitStrategy.TRAIN_TEST, test_ratio=0.0,
            )

    async def test_unsupported_algorithm_for_target_type_is_skipped_not_fatal(self, service):
        dataset = _classification_dataset()
        dataset.statistics = DatasetStatistics(sample_count=60, feature_count=2, positive_rate=0.5)
        # GAUSSIAN_NB has no regression form — selecting for REGRESSION should skip it, not raise.
        regression_dataset = _classification_dataset()
        regression_dataset.samples = [
            TrainingSample(features=s.features, label=float(s.label) * 10.0, reference_time=s.reference_time) for s in regression_dataset.samples
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

    async def test_multiclass_dataset_produces_a_real_multiclass_winner(self, service):
        """(2026-08-06) `dataset.lineage.class_labels` (non-empty) is threaded onto every candidate
        adapter before fit() — the winning model decodes a real label (not "positive"/"negative")
        and reports a full distribution, the shape football.match_winner/football.correct_score
        now train through."""
        dataset = _multiclass_dataset()

        result = await service.select(dataset, TargetType.CLASSIFICATION, candidates=FAST_CLASSIFICATION_CANDIDATES)

        assert result.winning_model.class_labels == MULTICLASS_LABELS
        prediction = result.winning_model.predict_one({"x1": -4.0, "x2": 0.0})
        assert prediction.value in MULTICLASS_LABELS
        assert set(prediction.distribution.keys()) == set(MULTICLASS_LABELS)


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

    async def test_leaves_training_run_ref_unset_when_no_repository_wired(self, service, model_repo):
        """`service` (no `training_runs` port) matches every pre-existing caller/test — proves
        this stays a true no-op rather than raising or silently misbehaving."""
        dataset = _classification_dataset()

        challenger, _ = await service.select_and_register_challenger(
            market_id=dataset.market_id, dataset=dataset, target_type=TargetType.CLASSIFICATION,
            model_key_prefix="football.match_result", next_version=1, now=T0,
            candidates=FAST_CLASSIFICATION_CANDIDATES,
        )

        assert challenger.training_run_ref is None

    async def test_persists_a_real_training_run_row_when_repository_is_wired(
        self, service_with_training_runs, model_repo, training_run_repo_fake,
    ):
        """The audit trail behind `ModelDefinition.training_run_ref` — Phase 3 audit gap #7:
        `training_runs` table was defined but nothing ever wrote to it."""
        dataset = _classification_dataset()

        challenger, selection = await service_with_training_runs.select_and_register_challenger(
            market_id=dataset.market_id, dataset=dataset, target_type=TargetType.CLASSIFICATION,
            model_key_prefix="football.match_result", next_version=1, now=T0,
            candidates=FAST_CLASSIFICATION_CANDIDATES,
        )

        assert challenger.training_run_ref is not None
        run = next(iter(training_run_repo_fake.store.values()))
        assert str(run.id.value) == challenger.training_run_ref

        assert run.market_id == dataset.market_id
        assert run.model_id == challenger.id
        assert run.dataset_id == dataset.id
        assert run.algorithm == selection.winning_candidate.algorithm.value
        assert run.framework == selection.winning_candidate.framework.value
        assert run.samples_used > 0
        assert run.feature_order == ("x1", "x2")
        assert run.test_metrics["log_loss"] == selection.ranking_value
        assert run.started_at == T0
        assert run.completed_at == T0

        runs_for_market = await training_run_repo_fake.list_by_market(dataset.market_id)
        assert len(runs_for_market) == 1
        assert runs_for_market[0].id == run.id

    async def test_persists_a_real_artifact_the_winning_model_can_be_reloaded_from(
        self, service, artifact_store
    ):
        """Audit fix: registration previously left artifact_ref unset, so a Challenger's real
        fitted weights were never persisted anywhere — TrainedModelPredictor/ModelLoaderService
        had nothing to load. The saved payload must be the actual serialized winning model, not
        a placeholder."""
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

        assert challenger.artifact_ref is not None
        assert challenger.artifact_ref in artifact_store.store
        assert artifact_store.store[challenger.artifact_ref] == selection.winning_model.serialize()

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


class TestStatisticalBaselineRoster:
    """Statistical-baseline charter: every trainable market should have a simple statistical
    baseline (Poisson/Tweedie/Ridge/Logistic) competing in the same roster as the ML candidates,
    not assumed inferior — these tests confirm the roster wiring and audit-trail additions."""

    def test_poisson_and_tweedie_in_default_regression_roster(self):
        algorithms = {c.algorithm for c in DEFAULT_REGRESSION_CANDIDATES}
        assert MLAlgorithm.POISSON_GLM in algorithms
        assert MLAlgorithm.TWEEDIE_GLM in algorithms

    def test_poisson_and_tweedie_absent_from_classification_roster(self):
        algorithms = {c.algorithm for c in DEFAULT_CLASSIFICATION_CANDIDATES}
        assert MLAlgorithm.POISSON_GLM not in algorithms
        assert MLAlgorithm.TWEEDIE_GLM not in algorithms

    def test_baseline_tags_on_expected_candidates_only(self):
        classification_baselines = {c.algorithm for c in DEFAULT_CLASSIFICATION_CANDIDATES if c.is_baseline}
        assert classification_baselines == {MLAlgorithm.LOGISTIC_REGRESSION}

        regression_baselines = {c.algorithm for c in DEFAULT_REGRESSION_CANDIDATES if c.is_baseline}
        assert regression_baselines == {MLAlgorithm.RIDGE, MLAlgorithm.POISSON_GLM, MLAlgorithm.TWEEDIE_GLM}

    async def test_select_populates_candidate_scores_for_every_non_skipped_candidate(self, service):
        dataset = _count_regression_dataset()
        candidates = (
            CandidateSpec(MLAlgorithm.RIDGE, MLFramework.SKLEARN, is_baseline=True),
            CandidateSpec(MLAlgorithm.POISSON_GLM, MLFramework.SKLEARN, is_baseline=True),
            CandidateSpec(MLAlgorithm.RANDOM_FOREST, MLFramework.SKLEARN),
        )

        result = await service.select(dataset, TargetType.REGRESSION, candidates=candidates)

        scored_algorithms = {c.algorithm for c, _ in result.candidate_scores}
        assert scored_algorithms == {MLAlgorithm.RIDGE, MLAlgorithm.POISSON_GLM, MLAlgorithm.RANDOM_FOREST}
        for _, value in result.candidate_scores:
            assert value >= 0.0

    async def test_poisson_can_win_the_roster(self, service):
        """Proves the ranking logic doesn't structurally exclude the new baseline — a real
        candidate on its own always wins by definition, confirming Poisson is a fully viable,
        non-skipped roster member end to end (fit -> train -> rank -> select)."""
        dataset = _count_regression_dataset()
        candidates = (CandidateSpec(MLAlgorithm.POISSON_GLM, MLFramework.SKLEARN, is_baseline=True),)

        result = await service.select(dataset, TargetType.REGRESSION, candidates=candidates)

        assert result.winning_candidate.algorithm is MLAlgorithm.POISSON_GLM
        assert result.winning_candidate.is_baseline is True
