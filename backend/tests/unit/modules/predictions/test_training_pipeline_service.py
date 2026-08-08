from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.dataset_registry_service import DatasetRegistryService
from modules.predictions.application.training_pipeline_service import (
    DatasetNotTrainableError,
    RetrainingScheduler,
    TrainingPipelineService,
)
from modules.predictions.domain.dataset import (
    Dataset,
    DatasetId,
    DatasetLineage,
    DatasetQualityIssue,
    DatasetStatistics,
    DatasetStatus,
    SplitStrategy,
)
from modules.predictions.domain.ml_value_objects import MLAlgorithm
from modules.predictions.domain.value_objects import MarketId, TargetType
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.ports.ml_model import TrainingSample

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _classification_dataset(market_id, n=60, status=DatasetStatus.APPROVED, quality_issues=()):
    samples = []
    for i in range(n):
        x1 = float(i % 10) - 5.0
        x2 = float((i * 3) % 10) - 5.0
        label = 1.0 if (x1 + x2) > 0 else 0.0
        samples.append(TrainingSample(features={"x1": x1, "x2": x2}, label=label))

    return Dataset(
        id=DatasetId(uuid4()),
        market_id=market_id,
        version=1,
        content_hash="hash",
        samples=samples,
        statistics=DatasetStatistics(sample_count=n, feature_count=2, positive_rate=0.5),
        lineage=DatasetLineage(market_id=market_id, source_prediction_ids=(), feature_keys=("x1", "x2"), built_at=T0),
        quality_issues=quality_issues,
        status=status,
        created_at=T0,
    )


MULTICLASS_LABELS = ("LOW", "MID", "HIGH")


def _multiclass_dataset(market_id, n=90, status=DatasetStatus.APPROVED):
    samples = []
    for i in range(n):
        x1 = float(i % 10) - 5.0
        x2 = float((i * 3) % 10) - 5.0
        class_index = 0 if x1 < -1.5 else (2 if x1 > 1.5 else 1)
        samples.append(TrainingSample(features={"x1": x1, "x2": x2}, label=float(class_index)))

    return Dataset(
        id=DatasetId(uuid4()),
        market_id=market_id,
        version=1,
        content_hash="hash",
        samples=samples,
        statistics=DatasetStatistics(sample_count=n, feature_count=2, positive_rate=None),
        lineage=DatasetLineage(
            market_id=market_id, source_prediction_ids=(), feature_keys=("x1", "x2"), built_at=T0,
            class_labels=MULTICLASS_LABELS,
        ),
        status=status,
        created_at=T0,
    )


@pytest.fixture
def service():
    return TrainingPipelineService()


async def test_train_evaluates_multiclass_via_real_label_equality(service):
    """(2026-08-06) `_evaluate_classification`'s tp/fp/tn/fn framing assumes a binary 0/1 label —
    meaningless once the label is a class index. A multiclass model (class_labels set on the
    adapter before fit()) is evaluated by decoded-label equality instead, via _evaluate_multiclass."""
    market_id = MarketId(uuid4())
    dataset = _multiclass_dataset(market_id)
    model = SklearnAdapter(
        algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION, class_labels=MULTICLASS_LABELS
    )

    result = await service.train(model, dataset, split_strategy=SplitStrategy.TRAIN_TEST, test_ratio=0.25)

    assert result.model.is_fitted()
    assert result.test_metrics.accuracy is not None
    assert 0.0 <= result.test_metrics.accuracy <= 1.0
    # Precision/recall/f1 are binary-only concepts — honestly None for multiclass, never a
    # fabricated micro/macro-average.
    assert result.test_metrics.precision is None
    assert result.test_metrics.recall is None


async def test_train_produces_fitted_model_and_metrics(service):
    market_id = MarketId(uuid4())
    dataset = _classification_dataset(market_id)
    model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)

    result = await service.train(model, dataset, split_strategy=SplitStrategy.TRAIN_TEST, test_ratio=0.25)

    assert result.model.is_fitted()
    assert result.train_metrics.sample_count > 0
    assert result.test_metrics.accuracy is not None
    assert 0.0 <= result.test_metrics.accuracy <= 1.0
    assert result.feature_order == ("x1", "x2")
    assert result.selected_features == ("x1", "x2")


async def test_train_rejects_non_approved_dataset(service):
    market_id = MarketId(uuid4())
    dataset = _classification_dataset(market_id, status=DatasetStatus.DRAFT)
    model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)

    with pytest.raises(DatasetNotTrainableError):
        await service.train(model, dataset)


async def test_train_rejects_dataset_with_quality_issues(service):
    market_id = MarketId(uuid4())
    dataset = _classification_dataset(
        market_id, status=DatasetStatus.APPROVED, quality_issues=(DatasetQualityIssue.TOO_FEW_SAMPLES,)
    )
    model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)

    with pytest.raises(DatasetNotTrainableError):
        await service.train(model, dataset)


async def test_train_applies_feature_selection(service):
    market_id = MarketId(uuid4())
    dataset = _classification_dataset(market_id, n=80)
    model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)

    result = await service.train(
        model, dataset, split_strategy=SplitStrategy.TRAIN_TEST, feature_selection_top_k=1
    )

    assert len(result.selected_features) == 1
    assert set(model.feature_order) == set(result.selected_features)


async def test_train_early_stopping_with_train_val_test_split(service):
    market_id = MarketId(uuid4())
    dataset = _classification_dataset(market_id, n=100)
    model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)

    result = await service.train(
        model, dataset, split_strategy=SplitStrategy.TRAIN_VAL_TEST, val_ratio=0.2, test_ratio=0.2
    )

    assert result.model.is_fitted()


async def test_on_checkpoint_hook_is_called(service):
    market_id = MarketId(uuid4())
    dataset = _classification_dataset(market_id)
    model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
    checkpoints = []

    await service.train(model, dataset, on_checkpoint=lambda m, metrics: checkpoints.append(metrics))

    assert len(checkpoints) == 1


class TestRetrainingScheduler:
    async def test_no_dataset_means_no_retrain(self, dataset_repo):
        registry = DatasetRegistryService(datasets=dataset_repo)
        scheduler = RetrainingScheduler(dataset_registry=registry)

        result = await scheduler.should_retrain(MarketId(uuid4()), now=T0)

        assert result == {"should_retrain": False, "reason": "no dataset built yet"}

    async def test_stale_dataset_triggers_retrain(self, dataset_repo):
        registry = DatasetRegistryService(datasets=dataset_repo)
        market_id = MarketId(uuid4())
        old_dataset = _classification_dataset(market_id, status=DatasetStatus.APPROVED)
        old_dataset.created_at = T0
        await registry.register(old_dataset)

        result = await scheduler_check(registry, market_id, now=T0 + timedelta(days=10))

        assert result["should_retrain"] is True
        assert result["is_stale"] is True

    async def test_fresh_dataset_no_drift_does_not_trigger_retrain(self, dataset_repo):
        registry = DatasetRegistryService(datasets=dataset_repo)
        market_id = MarketId(uuid4())
        dataset = _classification_dataset(market_id, status=DatasetStatus.APPROVED)
        dataset.created_at = T0
        await registry.register(dataset)

        result = await scheduler_check(registry, market_id, now=T0 + timedelta(hours=1))

        assert result["should_retrain"] is False
        assert result["is_stale"] is False


async def scheduler_check(registry, market_id, now):
    scheduler = RetrainingScheduler(dataset_registry=registry, max_dataset_age=timedelta(days=7))
    return await scheduler.should_retrain(market_id, now=now)
