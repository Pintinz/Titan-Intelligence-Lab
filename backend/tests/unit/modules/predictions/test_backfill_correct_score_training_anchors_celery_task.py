"""Real-DB (file-based SQLite) tests for `backfill_correct_score_training_anchors_task` — unlike
its sibling backfill tasks, this one writes real `Prediction`/`PredictionOutcome` rows through the
real repository classes (`SqlAlchemyMarketRepository`, `ModelRegistryService`,
`SqlAlchemyPredictionRepository`, `SqlAlchemyPredictionOutcomeRepository`), so a bare fake session
can't stand in for it the way the other backfill tasks' pure-SQL sessions can. `_DiscoverySession`
below intercepts only the one raw-SQL discovery query (fake rows, since it references Postgres-
schema-qualified tables this test DB doesn't have) and delegates every other call — the ORM
selects/inserts the real repositories issue — straight through to a real SQLite session.

A *file-based* SQLite DB, not the conftest `sqlite_session:memory:` fixture, is deliberate: the
Celery task always runs its own body inside a fresh `asyncio.run()` loop, so the session it uses
must be constructed lazily inside that loop (aiosqlite connections are loop-bound) — while this
test's own setup/verification queries run in pytest-asyncio's own loop. A true in-memory SQLite DB
would vanish the moment either connection closes; a temp file persists real state across every
independently-loop-scoped connection that opens against it."""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.sql.elements import TextClause

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.domain.entities import MarketDefinition
from modules.predictions.domain.market_outcome_registry import MARKET_OUTCOME_CATALOG
from modules.predictions.domain.value_objects import MarketId, MarketKind, TargetType
from modules.predictions.infrastructure.celery import tasks as tasks_module
from modules.predictions.infrastructure.persistence.models import (
    Base,
    ModelDefinitionModel,
    PredictionModel,
    PredictionOutcomeModel,
)
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository

T0 = datetime(2026, 9, 2, tzinfo=timezone.utc)
MARKET_KEY = "football.correct_score"
ANCHOR_MODEL_KEY = "football.correct_score.historical-backfill"


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


@pytest.fixture(autouse=True)
def clear_factory():
    yield
    tasks_module.set_market_feature_repair_context_factory(None)


def _run(coro):
    return asyncio.run(coro)


def _engine(db_path):
    return create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", execution_options={"schema_translate_map": {"predictions": None}}
    )


async def _create_schema(db_path):
    engine = _engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _seed_market(db_path):
    engine = _engine(db_path)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await SqlAlchemyMarketRepository(session=session).upsert(
            MarketDefinition(
                id=MarketId(uuid4()), market_key=MARKET_KEY, sport_code="football", name="Correct Score",
                category="score", market_kind=MarketKind.CORRECT_SCORE, target_type=TargetType.CLASSIFICATION,
            )
        )
        await session.commit()
    await engine.dispose()


async def _fetch_all(db_path, stmt):
    engine = _engine(db_path)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        rows = (await session.execute(stmt)).scalars().all()
    await engine.dispose()
    return rows


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.db"
    _run(_create_schema(str(path)))
    _run(_seed_market(str(path)))
    return str(path)


def _fresh_task_session(db_path):
    """A session object it's safe to construct here (no I/O yet — aiosqlite only actually opens a
    connection on first real query) and hand to the task's own factory; the connection itself
    opens lazily inside the task's own `asyncio.run()`-created loop, not this one."""
    return async_sessionmaker(_engine(db_path), expire_on_commit=False)()


class _DiscoverySession:
    """Wraps a real AsyncSession: the one raw `text()` discovery query returns fake rows (it
    references sports.fixtures/features.feature_values_offline, tables this test DB never
    creates); every other call — the real repositories' ORM selects/inserts — passes straight
    through."""

    def __init__(self, real_session, discovery_rows):
        self._real = real_session
        self._discovery_rows = discovery_rows
        self.discovery_call_count = 0
        self.last_discovery_query = ""

    async def execute(self, stmt, *args, **kwargs):
        if isinstance(stmt, TextClause):
            self.discovery_call_count += 1
            self.last_discovery_query = str(stmt)
            return _FakeResult(self._discovery_rows)
        return await self._real.execute(stmt, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _fixture_row(fixture_id=None, home_score=1, away_score=1, scheduled_at=None, eh=1.4, ea=1.1):
    return (fixture_id or str(uuid4()), home_score, away_score, scheduled_at or (T0 - timedelta(days=30)), eh, ea)


def _wire(session):
    async def factory():
        return tasks_module.MarketFeatureRepairContext(
            seeder=None, mappings=None, venue_strength_calculator=None, expected_goals_calculator=None,
            session=session,
        )

    tasks_module.set_market_feature_repair_context_factory(factory)


def test_creates_a_real_prediction_and_outcome_with_raw_goals_set(db):
    """The core bug this task exists to avoid: the original local-only backfill script never set
    raw_home_goals/raw_away_goals, so FootballGoalsPoissonAdapter.fit()'s `is not None` filter
    would silently exclude every anchor it creates from Poisson training. Both must be real ints
    from the fixture's own final score, on the actual persisted PredictionOutcome row."""
    fixture_id = str(uuid4())
    row = _fixture_row(fixture_id=fixture_id, home_score=2, away_score=1, eh=1.8, ea=0.9)
    _wire(_DiscoverySession(_fresh_task_session(db), [row]))

    result = tasks_module.backfill_correct_score_training_anchors_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result["training_anchors_created"] == 1
    assert result["skipped_missing_expected_goals"] == 0

    (pred,) = _run(_fetch_all(db, select(PredictionModel).where(PredictionModel.subject_ref == fixture_id)))
    assert pred.feature_snapshot == {
        "football.fixture.expected_home_goals": 1.8,
        "football.fixture.expected_away_goals": 0.9,
    }
    assert pred.value == "insufficient_historical_data"  # honest inert placeholder, never fabricated
    assert pred.status == "draft"

    (outcome,) = _run(_fetch_all(db, select(PredictionOutcomeModel).where(PredictionOutcomeModel.prediction_id == pred.id)))
    assert outcome.raw_home_goals == 2
    assert outcome.raw_away_goals == 1
    assert outcome.actual_value == "2-1"


def test_a_scoreline_outside_the_allowed_grid_buckets_to_other(db):
    allowed = set(MARKET_OUTCOME_CATALOG[MARKET_KEY].allowed_values)
    # A genuine blowout, outside _correct_score_grid's MAX_GOALS-bounded universe.
    home, away = 9, 9
    assert f"{home}-{away}" not in allowed
    _wire(_DiscoverySession(_fresh_task_session(db), [_fixture_row(home_score=home, away_score=away)]))

    tasks_module.backfill_correct_score_training_anchors_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    (outcome,) = _run(_fetch_all(db, select(PredictionOutcomeModel)))
    assert outcome.actual_value == "OTHER"
    assert outcome.raw_home_goals == home  # OTHER-bucketed label still carries the real goal counts
    assert outcome.raw_away_goals == away


def test_a_fixture_missing_expected_goals_is_skipped_not_fabricated(db):
    _wire(_DiscoverySession(_fresh_task_session(db), [_fixture_row(eh=None, ea=None)]))

    result = tasks_module.backfill_correct_score_training_anchors_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result["training_anchors_created"] == 0
    assert result["skipped_missing_expected_goals"] == 1
    assert _run(_fetch_all(db, select(PredictionModel))) == []


def test_discovery_query_excludes_fixtures_already_anchored(db):
    session = _DiscoverySession(_fresh_task_session(db), [])
    _wire(session)

    tasks_module.backfill_correct_score_training_anchors_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert "NOT EXISTS" in session.last_discovery_query
    assert "predictions.predictions" in session.last_discovery_query


def test_rerunning_reuses_the_same_anchor_model_instead_of_crashing(db):
    """ModelAlreadyRegisteredError must be caught and the existing anchor reused — the same
    idempotent-registration posture the original local-only script used."""
    _wire(_DiscoverySession(_fresh_task_session(db), [_fixture_row()]))
    tasks_module.backfill_correct_score_training_anchors_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    _wire(_DiscoverySession(_fresh_task_session(db), [_fixture_row()]))
    result2 = tasks_module.backfill_correct_score_training_anchors_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result2["training_anchors_created"] == 1  # second, distinct fixture — not blocked
    anchors = _run(_fetch_all(db, select(ModelDefinitionModel).where(ModelDefinitionModel.model_key == ANCHOR_MODEL_KEY)))
    assert len(anchors) == 1  # exactly one anchor model registered across both runs, never duplicated


def test_commits_in_batches_instead_of_only_once_at_the_end(db, monkeypatch):
    monkeypatch.setattr(tasks_module, "_TRAINING_ANCHOR_BACKFILL_COMMIT_BATCH_SIZE", 2)
    rows = [_fixture_row() for _ in range(5)]

    real_session = _fresh_task_session(db)
    commit_calls = {"n": 0}
    real_commit = real_session.commit

    async def counting_commit():
        commit_calls["n"] += 1
        await real_commit()

    real_session.commit = counting_commit
    _wire(_DiscoverySession(real_session, rows))

    tasks_module.backfill_correct_score_training_anchors_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert commit_calls["n"] == 3  # 2 mid-loop batches of 2 + 1 final partial batch of 1


class _HangingSession:
    """Hangs on the very first `execute()` — `markets.get_by_key()`, the task's first real DB
    call — same "any await inside _do() is bounded by the outer asyncio.wait_for" posture every
    sibling backfill task's own hanging-session test already uses; which specific call hangs
    doesn't matter, only that the timeout wrapper actually fires."""

    async def execute(self, *args, **kwargs):
        await asyncio.sleep(3600)
        return _FakeResult([])  # pragma: no cover — unreachable, the timeout fires first

    async def commit(self):  # pragma: no cover
        pass

    async def close(self):
        pass


def test_task_times_out_instead_of_hanging_forever(monkeypatch):
    monkeypatch.setattr(tasks_module, "_TRAINING_ANCHOR_BACKFILL_TASK_TIMEOUT_SECONDS", 0.05)

    async def factory():
        return tasks_module.MarketFeatureRepairContext(
            seeder=None, mappings=None, venue_strength_calculator=None, expected_goals_calculator=None,
            session=_HangingSession(),
        )

    tasks_module.set_market_feature_repair_context_factory(factory)

    with pytest.raises(Exception) as exc_info:
        tasks_module.backfill_correct_score_training_anchors_task.apply(kwargs={"now_iso": T0.isoformat()}).get()
    causes = []
    err = exc_info.value
    while err is not None and err not in causes:
        causes.append(err)
        err = getattr(err, "exc", None) or err.__cause__
    assert any(isinstance(c, TimeoutError) for c in causes), f"expected a TimeoutError in {causes!r}"
