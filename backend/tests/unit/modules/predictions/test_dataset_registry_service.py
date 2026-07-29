from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.dataset_registry_service import (
    DatasetHasQualityIssuesError,
    DatasetNotFoundError,
    DatasetRegistryService,
    InvalidDatasetLifecycleTransitionError,
)
from modules.predictions.domain.dataset import (
    Dataset,
    DatasetId,
    DatasetLineage,
    DatasetQualityIssue,
    DatasetStatistics,
    DatasetStatus,
)
from modules.predictions.domain.value_objects import MarketId

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _dataset(market_id, version=1, mean=None, quality_issues=(), status=DatasetStatus.DRAFT):
    return Dataset(
        id=DatasetId(uuid4()),
        market_id=market_id,
        version=version,
        content_hash=f"hash-{version}",
        samples=[],
        statistics=DatasetStatistics(
            sample_count=40, feature_count=2, positive_rate=0.5, mean=mean or {"x": 1.0}, std={"x": 0.5}
        ),
        lineage=DatasetLineage(market_id=market_id, source_prediction_ids=(), feature_keys=("x",), built_at=T0),
        quality_issues=quality_issues,
        status=status,
        created_at=T0,
    )


@pytest.fixture
def service(dataset_repo):
    return DatasetRegistryService(datasets=dataset_repo)


async def test_register_persists_dataset(service, dataset_repo):
    market_id = MarketId(uuid4())
    dataset = _dataset(market_id)

    registered = await service.register(dataset)

    assert await dataset_repo.get(registered.id) is registered


async def test_validate_transitions_draft_to_validated(service):
    market_id = MarketId(uuid4())
    dataset = await service.register(_dataset(market_id))

    validated = await service.validate(dataset.id)

    assert validated.status is DatasetStatus.VALIDATED


async def test_validate_rejects_dataset_with_too_few_samples(service):
    market_id = MarketId(uuid4())
    dataset = await service.register(_dataset(market_id, quality_issues=(DatasetQualityIssue.TOO_FEW_SAMPLES,)))

    with pytest.raises(DatasetHasQualityIssuesError):
        await service.validate(dataset.id)


async def test_validate_rejects_non_draft_dataset(service):
    market_id = MarketId(uuid4())
    dataset = await service.register(_dataset(market_id, status=DatasetStatus.VALIDATED))

    with pytest.raises(InvalidDatasetLifecycleTransitionError):
        await service.validate(dataset.id)


async def test_approve_requires_validated_status(service):
    market_id = MarketId(uuid4())
    dataset = await service.register(_dataset(market_id, status=DatasetStatus.DRAFT))

    with pytest.raises(InvalidDatasetLifecycleTransitionError):
        await service.approve(dataset.id, approved_by="analyst-1", now=T0)


async def test_approve_records_approver_and_timestamp(service):
    market_id = MarketId(uuid4())
    dataset = await service.register(_dataset(market_id, status=DatasetStatus.VALIDATED))

    approved = await service.approve(dataset.id, approved_by="analyst-1", now=T0)

    assert approved.status is DatasetStatus.APPROVED
    assert approved.approved_by == "analyst-1"
    assert approved.approved_at == T0


async def test_archive_transitions_to_archived(service):
    market_id = MarketId(uuid4())
    dataset = await service.register(_dataset(market_id, status=DatasetStatus.APPROVED))

    archived = await service.archive(dataset.id)

    assert archived.status is DatasetStatus.ARCHIVED


async def test_archive_twice_raises(service):
    market_id = MarketId(uuid4())
    dataset = await service.register(_dataset(market_id, status=DatasetStatus.ARCHIVED))

    with pytest.raises(InvalidDatasetLifecycleTransitionError):
        await service.archive(dataset.id)


async def test_unknown_dataset_raises_not_found(service):
    with pytest.raises(DatasetNotFoundError):
        await service.validate(DatasetId(uuid4()))


async def test_detect_drift_with_no_dataset(service):
    result = await service.detect_drift(MarketId(uuid4()))
    assert result == {"drift_detected": False, "reason": "no dataset built yet"}


async def test_detect_drift_with_no_baseline(service):
    market_id = MarketId(uuid4())
    await service.register(_dataset(market_id, version=1))

    result = await service.detect_drift(market_id)

    assert result == {"drift_detected": False, "reason": "no baseline dataset to compare against"}


async def test_detect_drift_flags_large_mean_shift(service):
    market_id = MarketId(uuid4())
    await service.register(_dataset(market_id, version=1, mean={"x": 1.0}))
    await service.register(_dataset(market_id, version=2, mean={"x": 5.0}))

    result = await service.detect_drift(market_id)

    assert result["drift_detected"] is True
    assert "x" in result["drifted_features"]
    assert result["baseline_version"] == 1
    assert result["latest_version"] == 2


async def test_detect_drift_no_drift_for_similar_means(service):
    market_id = MarketId(uuid4())
    await service.register(_dataset(market_id, version=1, mean={"x": 1.0}))
    await service.register(_dataset(market_id, version=2, mean={"x": 1.05}))

    result = await service.detect_drift(market_id)

    assert result["drift_detected"] is False
