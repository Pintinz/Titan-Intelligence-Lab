from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.domain.dataset import Dataset, DatasetId, DatasetLineage, DatasetStatistics, DatasetStatus
from modules.predictions.domain.value_objects import MarketId
from modules.predictions.infrastructure.persistence.in_memory_dataset_repository import InMemoryDatasetRepository

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _dataset(market_id: MarketId, version: int) -> Dataset:
    return Dataset(
        id=DatasetId(uuid4()),
        market_id=market_id,
        version=version,
        content_hash=f"hash-{version}",
        samples=[],
        statistics=DatasetStatistics(sample_count=0, feature_count=0, positive_rate=None),
        lineage=DatasetLineage(market_id=market_id, source_prediction_ids=(), feature_keys=(), built_at=T0),
        status=DatasetStatus.DRAFT,
        created_at=T0,
    )


@pytest.fixture
def repo():
    return InMemoryDatasetRepository()


@pytest.fixture
def market_id():
    return MarketId(uuid4())


class TestInMemoryDatasetRepository:
    async def test_get_unknown_returns_none(self, repo):
        assert await repo.get(DatasetId(uuid4())) is None

    async def test_upsert_then_get_round_trips(self, repo, market_id):
        dataset = _dataset(market_id, version=1)
        await repo.upsert(dataset)

        fetched = await repo.get(dataset.id)

        assert fetched.id == dataset.id

    async def test_get_latest_version_returns_highest_version(self, repo, market_id):
        await repo.upsert(_dataset(market_id, version=1))
        latest = _dataset(market_id, version=3)
        await repo.upsert(latest)
        await repo.upsert(_dataset(market_id, version=2))

        result = await repo.get_latest_version(market_id)

        assert result.id == latest.id

    async def test_get_latest_version_no_datasets_returns_none(self, repo, market_id):
        assert await repo.get_latest_version(market_id) is None

    async def test_list_by_market_orders_newest_first_and_filters_by_market(self, repo, market_id):
        other_market = MarketId(uuid4())
        await repo.upsert(_dataset(market_id, version=1))
        await repo.upsert(_dataset(market_id, version=2))
        await repo.upsert(_dataset(other_market, version=1))

        results = await repo.list_by_market(market_id)

        assert [d.version for d in results] == [2, 1]

    async def test_list_by_market_respects_limit(self, repo, market_id):
        for version in range(1, 6):
            await repo.upsert(_dataset(market_id, version=version))

        results = await repo.list_by_market(market_id, limit=2)

        assert len(results) == 2
