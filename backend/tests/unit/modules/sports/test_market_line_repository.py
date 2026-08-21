"""POST-M24 Phase 6 — persistence round-trip for `MarketLine` (append-only: `record` never
overwrites, `get_latest_for_fixture` respects the temporal `before` gate a pre-match feature/
resolver must apply)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.sports.domain.entities import MarketLine
from modules.sports.domain.value_objects import FixtureId, MarketLineId, MarketLineType
from modules.sports.infrastructure.persistence.models import Base
from modules.sports.infrastructure.persistence.repositories import SqlAlchemyMarketLineRepository

T0 = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://", execution_options={"schema_translate_map": {"sports": None}}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s
    await engine.dispose()


def _line(fixture_id: FixtureId, fetched_at: datetime, price: float = 1.9) -> MarketLine:
    return MarketLine(
        id=MarketLineId(uuid4()), fixture_id=fixture_id, sport_code="basketball", provider="api_basketball",
        bookmaker="test_book", market_type=MarketLineType.MONEYLINE, selection="HOME", line=None,
        price=price, fetched_at=fetched_at,
    )


@pytest.mark.asyncio
async def test_record_and_list_for_fixture_round_trips(session):
    repo = SqlAlchemyMarketLineRepository(session=session)
    fixture_id = FixtureId(uuid4())
    saved = await repo.record(_line(fixture_id, T0))

    rows = await repo.list_for_fixture(fixture_id)

    assert len(rows) == 1
    assert rows[0].id == saved.id
    assert rows[0].market_type is MarketLineType.MONEYLINE
    assert rows[0].price == 1.9


@pytest.mark.asyncio
async def test_record_is_append_only_a_second_quote_does_not_overwrite_the_first(session):
    repo = SqlAlchemyMarketLineRepository(session=session)
    fixture_id = FixtureId(uuid4())
    await repo.record(_line(fixture_id, T0, price=1.9))
    await repo.record(_line(fixture_id, T0 + timedelta(hours=1), price=1.85))

    rows = await repo.list_for_fixture(fixture_id)

    assert len(rows) == 2


@pytest.mark.asyncio
async def test_get_latest_for_fixture_returns_the_most_recently_fetched_quote(session):
    repo = SqlAlchemyMarketLineRepository(session=session)
    fixture_id = FixtureId(uuid4())
    await repo.record(_line(fixture_id, T0, price=1.9))
    await repo.record(_line(fixture_id, T0 + timedelta(hours=2), price=1.80))

    latest = await repo.get_latest_for_fixture(fixture_id, "moneyline")

    assert latest is not None
    assert latest.price == 1.80


@pytest.mark.asyncio
async def test_get_latest_for_fixture_respects_the_before_temporal_gate(session):
    """A pre-match feature/resolver must never see a line fetched after its own cutoff — the
    real leakage-prevention rule this port's docstring promises."""
    repo = SqlAlchemyMarketLineRepository(session=session)
    fixture_id = FixtureId(uuid4())
    await repo.record(_line(fixture_id, T0, price=1.9))
    await repo.record(_line(fixture_id, T0 + timedelta(hours=5), price=1.70))  # post-cutoff quote

    latest = await repo.get_latest_for_fixture(fixture_id, "moneyline", before=T0 + timedelta(hours=1))

    assert latest is not None
    assert latest.price == 1.9  # the post-cutoff quote is invisible to this caller


@pytest.mark.asyncio
async def test_get_latest_for_fixture_returns_none_when_nothing_recorded(session):
    repo = SqlAlchemyMarketLineRepository(session=session)
    result = await repo.get_latest_for_fixture(FixtureId(uuid4()), "moneyline")
    assert result is None


@pytest.mark.asyncio
async def test_list_for_fixture_never_leaks_another_fixtures_lines(session):
    repo = SqlAlchemyMarketLineRepository(session=session)
    fixture_a, fixture_b = FixtureId(uuid4()), FixtureId(uuid4())
    await repo.record(_line(fixture_a, T0))
    await repo.record(_line(fixture_b, T0))

    rows_a = await repo.list_for_fixture(fixture_a)

    assert len(rows_a) == 1
    assert rows_a[0].fixture_id == fixture_a
