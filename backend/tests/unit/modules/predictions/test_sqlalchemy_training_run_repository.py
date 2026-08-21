"""Phase 3 audit fix — `training_runs` (`TrainingRunModel`) was defined in the schema but nothing
ever wrote to it (`ModelDefinition.training_run_ref` pointed at rows that never existed). These
tests confirm `SqlAlchemyTrainingRunRepository` round-trips a `TrainingRun` correctly and that
`get`/`list_by_market` behave as the port promises.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.domain.dataset import DatasetId
from modules.predictions.domain.training_run import TrainingRun, TrainingRunId
from modules.predictions.domain.value_objects import MarketId, ModelId
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyTrainingRunRepository

pytestmark = pytest.mark.asyncio


def _run(market_id: MarketId, completed_at: datetime) -> TrainingRun:
    return TrainingRun(
        id=TrainingRunId(uuid4()),
        market_id=market_id,
        model_id=ModelId(uuid4()),
        dataset_id=DatasetId(uuid4()),
        algorithm="lightgbm_gbm",
        framework="lightgbm",
        train_metrics={"sample_count": 100, "metric_name": "log_loss", "metric_value": 0.42},
        test_metrics={"log_loss": 0.45, "accuracy": 0.71},
        feature_order=("x1", "x2"),
        selected_features=("x1", "x2"),
        samples_used=100,
        outliers_removed=3,
        started_at=completed_at - timedelta(seconds=5),
        completed_at=completed_at,
    )


class TestSqlAlchemyTrainingRunRepository:
    async def test_record_and_get_round_trip(self, sqlite_session):
        repo = SqlAlchemyTrainingRunRepository(session=sqlite_session)
        market_id = MarketId(uuid4())
        run = _run(market_id, datetime(2026, 8, 8, tzinfo=timezone.utc))

        await repo.record(run)
        await sqlite_session.commit()

        result = await repo.get(run.id)
        assert result is not None
        assert result.market_id == market_id
        assert result.model_id == run.model_id
        assert result.dataset_id == run.dataset_id
        assert result.algorithm == "lightgbm_gbm"
        assert result.framework == "lightgbm"
        assert result.train_metrics == {"sample_count": 100, "metric_name": "log_loss", "metric_value": 0.42}
        assert result.test_metrics == {"log_loss": 0.45, "accuracy": 0.71}
        assert result.feature_order == ("x1", "x2")
        assert result.selected_features == ("x1", "x2")
        assert result.samples_used == 100
        assert result.outliers_removed == 3

    async def test_get_returns_none_when_no_run_recorded(self, sqlite_session):
        repo = SqlAlchemyTrainingRunRepository(session=sqlite_session)
        assert await repo.get(TrainingRunId(uuid4())) is None

    async def test_round_trips_null_model_and_dataset_ids(self, sqlite_session):
        """A run persisted before its model was registered (or without a resolvable dataset) must
        still round-trip cleanly — both FKs are nullable in the schema."""
        repo = SqlAlchemyTrainingRunRepository(session=sqlite_session)
        run = TrainingRun(
            id=TrainingRunId(uuid4()), market_id=MarketId(uuid4()), model_id=None, dataset_id=None,
            algorithm="ridge", framework="sklearn", train_metrics={}, test_metrics={},
            feature_order=(), selected_features=(), samples_used=0, outliers_removed=0,
        )

        await repo.record(run)
        await sqlite_session.commit()

        result = await repo.get(run.id)
        assert result.model_id is None
        assert result.dataset_id is None
        assert result.started_at is None
        assert result.completed_at is None

    async def test_list_by_market_scopes_and_orders_descending(self, sqlite_session):
        repo = SqlAlchemyTrainingRunRepository(session=sqlite_session)
        market_a = MarketId(uuid4())
        market_b = MarketId(uuid4())
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        first = _run(market_a, base)
        second = _run(market_a, base + timedelta(days=1))
        other_market = _run(market_b, base + timedelta(days=2))

        for r in (first, second, other_market):
            await repo.record(r)
        await sqlite_session.commit()

        results = await repo.list_by_market(market_a)
        assert [r.id for r in results] == [second.id, first.id]

    async def test_list_by_market_respects_limit(self, sqlite_session):
        repo = SqlAlchemyTrainingRunRepository(session=sqlite_session)
        market_id = MarketId(uuid4())
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        for i in range(5):
            await repo.record(_run(market_id, base + timedelta(days=i)))
        await sqlite_session.commit()

        results = await repo.list_by_market(market_id, limit=2)
        assert len(results) == 2

    async def test_survives_a_fresh_session_against_the_same_engine(self, sqlite_session):
        market_id = MarketId(uuid4())
        run = _run(market_id, datetime(2026, 8, 8, tzinfo=timezone.utc))

        writer = SqlAlchemyTrainingRunRepository(session=sqlite_session)
        await writer.record(run)
        await sqlite_session.commit()

        reader = SqlAlchemyTrainingRunRepository(session=sqlite_session)
        result = await reader.get(run.id)
        assert result is not None
        assert result.id == run.id
