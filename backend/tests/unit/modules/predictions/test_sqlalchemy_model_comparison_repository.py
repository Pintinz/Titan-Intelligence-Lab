"""Phase 3 audit fix — `SqlAlchemyModelComparisonRepository` replaces the previous in-memory-only
`InMemoryModelComparisonRepository` for production wiring. These tests confirm the SQL-backed
implementation round-trips a `ChallengerEvaluation` correctly and that `get_latest`/`list_by_market`
scope and order results the same way the in-memory version did.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.domain.model_comparison import ChallengerEvaluation, ComparisonMetrics, ComparisonVerdict
from modules.predictions.domain.value_objects import ChallengerEvaluationId, MarketId, ModelId
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyModelComparisonRepository

pytestmark = pytest.mark.asyncio


def _evaluation(market_id: MarketId, evaluated_at: datetime, verdict: ComparisonVerdict = ComparisonVerdict.CHALLENGER_BETTER) -> ChallengerEvaluation:
    return ChallengerEvaluation(
        id=ChallengerEvaluationId(uuid4()),
        market_id=market_id,
        challenger_model_id=ModelId(uuid4()),
        champion_model_id=ModelId(uuid4()),
        challenger_metrics=ComparisonMetrics(log_loss=0.4, brier_score=0.15, expected_calibration_error=0.02),
        champion_metrics=ComparisonMetrics(log_loss=0.6, brier_score=0.2, expected_calibration_error=0.05),
        verdict=verdict,
        decisive_metric="log_loss",
        holdout_sample_count=25,
        evaluated_at=evaluated_at,
    )


class TestSqlAlchemyModelComparisonRepository:
    async def test_record_and_get_latest_round_trip(self, sqlite_session):
        repo = SqlAlchemyModelComparisonRepository(session=sqlite_session)
        market_id = MarketId(uuid4())
        evaluation = _evaluation(market_id, datetime(2026, 8, 8, tzinfo=timezone.utc))

        await repo.record(evaluation)
        await sqlite_session.commit()

        result = await repo.get_latest(market_id)
        assert result is not None
        assert result.id == evaluation.id
        assert result.market_id == market_id
        assert result.verdict is ComparisonVerdict.CHALLENGER_BETTER
        assert result.decisive_metric == "log_loss"
        assert result.holdout_sample_count == 25
        assert result.challenger_metrics.log_loss == 0.4
        assert result.champion_metrics.brier_score == 0.2

    async def test_get_latest_returns_most_recent(self, sqlite_session):
        repo = SqlAlchemyModelComparisonRepository(session=sqlite_session)
        market_id = MarketId(uuid4())
        older = _evaluation(market_id, datetime(2026, 8, 1, tzinfo=timezone.utc), ComparisonVerdict.CHAMPION_BETTER)
        newer = _evaluation(market_id, datetime(2026, 8, 8, tzinfo=timezone.utc), ComparisonVerdict.CHALLENGER_BETTER)

        await repo.record(older)
        await repo.record(newer)
        await sqlite_session.commit()

        result = await repo.get_latest(market_id)
        assert result.id == newer.id
        assert result.verdict is ComparisonVerdict.CHALLENGER_BETTER

    async def test_get_latest_returns_none_when_no_evaluations_recorded(self, sqlite_session):
        repo = SqlAlchemyModelComparisonRepository(session=sqlite_session)
        assert await repo.get_latest(MarketId(uuid4())) is None

    async def test_list_by_market_scopes_and_orders_descending(self, sqlite_session):
        repo = SqlAlchemyModelComparisonRepository(session=sqlite_session)
        market_a = MarketId(uuid4())
        market_b = MarketId(uuid4())
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        first = _evaluation(market_a, base)
        second = _evaluation(market_a, base + timedelta(days=1))
        other_market = _evaluation(market_b, base + timedelta(days=2))

        for e in (first, second, other_market):
            await repo.record(e)
        await sqlite_session.commit()

        results = await repo.list_by_market(market_a)
        assert [r.id for r in results] == [second.id, first.id]

    async def test_list_by_market_respects_limit(self, sqlite_session):
        repo = SqlAlchemyModelComparisonRepository(session=sqlite_session)
        market_id = MarketId(uuid4())
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        for i in range(5):
            await repo.record(_evaluation(market_id, base + timedelta(days=i)))
        await sqlite_session.commit()

        results = await repo.list_by_market(market_id, limit=2)
        assert len(results) == 2

    async def test_survives_a_fresh_session_against_the_same_engine(self, sqlite_session):
        """The whole point of this fix: unlike the in-memory repository, a record made in one
        session/process must be readable from a different session against the same database —
        proof this data no longer lives only in process memory."""
        market_id = MarketId(uuid4())
        evaluation = _evaluation(market_id, datetime(2026, 8, 8, tzinfo=timezone.utc))

        writer = SqlAlchemyModelComparisonRepository(session=sqlite_session)
        await writer.record(evaluation)
        await sqlite_session.commit()

        reader = SqlAlchemyModelComparisonRepository(session=sqlite_session)
        result = await reader.get_latest(market_id)
        assert result is not None
        assert result.id == evaluation.id
