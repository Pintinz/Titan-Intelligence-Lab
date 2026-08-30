from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.infrastructure.celery import tasks as tasks_module

T0 = datetime(2026, 8, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


@dataclass
class _FakeVenueStrengthCalculator:
    unwritable_fixture_ids: set = field(default_factory=set)
    compute_calls: list = field(default_factory=list)  # (fixture_id, cutoff)
    ensure_registered_calls: list = field(default_factory=list)

    async def ensure_registered(self, now):
        self.ensure_registered_calls.append(now)

    async def compute_and_write(self, fixture_id, home_team_id, away_team_id, sport_id, season_id, cutoff):
        self.compute_calls.append((fixture_id, cutoff))
        if fixture_id in self.unwritable_fixture_ids:
            return None, None, None, None
        return "home_attack", "home_defence", "away_attack", "away_defence"


@dataclass
class _FakeResult:
    rows: list

    def all(self):
        return self.rows


@dataclass
class _FakeSession:
    rows: list
    committed: bool = False
    closed: bool = False
    commit_count: int = 0

    async def execute(self, _stmt):
        return _FakeResult(self.rows)

    async def commit(self):
        self.committed = True
        self.commit_count += 1

    async def close(self):
        self.closed = True


def _completed_fixture_row(scheduled_at=None, tz_aware=True):
    kickoff = scheduled_at or (T0 - timedelta(days=30))
    if not tz_aware:
        kickoff = kickoff.replace(tzinfo=None)
    return (str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()), kickoff, str(uuid4()))


@pytest.fixture
def completed_rows():
    return [_completed_fixture_row(), _completed_fixture_row()]


@pytest.fixture
def fake_calculator():
    return _FakeVenueStrengthCalculator()


@pytest.fixture
def fake_session(completed_rows):
    return _FakeSession(rows=completed_rows)


@pytest.fixture
def fake_context(fake_calculator, fake_session):
    return tasks_module.MarketFeatureRepairContext(
        seeder=None, mappings=None, venue_strength_calculator=fake_calculator, session=fake_session,
    )


@pytest.fixture(autouse=True)
def wire_factory(fake_context):
    async def factory():
        return fake_context

    tasks_module.set_market_feature_repair_context_factory(factory)
    yield
    tasks_module.set_market_feature_repair_context_factory(None)


def test_backfills_every_completed_fixture_using_its_own_kickoff_as_cutoff(
    fake_calculator, fake_session, completed_rows
):
    result = tasks_module.backfill_venue_strength_for_completed_fixtures_task.apply(
        kwargs={"now_iso": T0.isoformat()}
    ).get()

    assert len(fake_calculator.ensure_registered_calls) == 1
    assert len(fake_calculator.compute_calls) == len(completed_rows)
    # Point-in-time safety: each fixture's own scheduled_at is the cutoff, never `now` — a real
    # incident class (a historical fixture's own later result leaking into its own pre-match
    # feature) this must never regress into.
    for (_, cutoff), (_, _, _, _, scheduled_at, _) in zip(fake_calculator.compute_calls, completed_rows):
        assert cutoff == scheduled_at
        assert cutoff != T0
    assert fake_session.committed is True
    assert fake_session.closed is True

    assert result["completed_football_fixtures_checked"] == len(completed_rows)
    assert result["venue_strength_backfilled"] == len(completed_rows)


def test_commits_in_batches_instead_of_only_once_at_the_end(fake_calculator):
    """Real production incident (2026-08-30): the first live run of this task hit its own task
    timeout with the single commit() still at the very end of the loop — every fixture computed
    in that run was discarded uncommitted, and the autoretry that followed repeated the exact
    same all-or-nothing failure from scratch. A single-batch row count must commit only once (at
    the end); a row count spanning multiple batches must commit partway through too, so an
    interruption anywhere in the loop keeps whatever full batches already completed."""
    batch_size = tasks_module._VENUE_STRENGTH_BACKFILL_COMMIT_BATCH_SIZE
    many_rows = [_completed_fixture_row() for _ in range(batch_size * 2 + 3)]
    session = _FakeSession(rows=many_rows)

    async def factory():
        return tasks_module.MarketFeatureRepairContext(
            seeder=None, mappings=None, venue_strength_calculator=fake_calculator, session=session,
        )

    tasks_module.set_market_feature_repair_context_factory(factory)

    tasks_module.backfill_venue_strength_for_completed_fixtures_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    # 2 mid-loop batch commits (after fixture 50 and fixture 100) + 1 final commit for the
    # remaining partial batch (3 more fixtures) = 3 total, not 1.
    assert session.commit_count == 3


def test_a_fixture_the_calculator_cant_compute_for_is_not_counted_as_backfilled(fake_calculator, completed_rows):
    unwritable_id = completed_rows[0][0]
    fake_calculator.unwritable_fixture_ids = {unwritable_id}

    result = tasks_module.backfill_venue_strength_for_completed_fixtures_task.apply(
        kwargs={"now_iso": T0.isoformat()}
    ).get()

    assert result["venue_strength_backfilled"] == len(completed_rows) - 1
    assert result["completed_football_fixtures_checked"] == len(completed_rows)


def test_naive_scheduled_at_is_stamped_utc_not_left_ambiguous(fake_calculator):
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — a naive
    scheduled_at from the DB must still resolve to a real, comparable UTC cutoff, not silently
    compare unequal/incomparable against timezone-aware values elsewhere in the pipeline."""
    naive_row = _completed_fixture_row(tz_aware=False)

    async def factory():
        return tasks_module.MarketFeatureRepairContext(
            seeder=None, mappings=None, venue_strength_calculator=fake_calculator,
            session=_FakeSession(rows=[naive_row]),
        )

    tasks_module.set_market_feature_repair_context_factory(factory)

    tasks_module.backfill_venue_strength_for_completed_fixtures_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    (_, cutoff), = fake_calculator.compute_calls
    assert cutoff.tzinfo is not None
    assert cutoff == naive_row[4].replace(tzinfo=timezone.utc)


def test_task_defaults_now_to_current_time_when_not_supplied(fake_calculator):
    tasks_module.backfill_venue_strength_for_completed_fixtures_task.apply(kwargs={}).get()
    assert len(fake_calculator.ensure_registered_calls) == 1


class _HangingSession:
    async def execute(self, _stmt):
        await asyncio.sleep(3600)
        return _FakeResult([])  # pragma: no cover — unreachable, the timeout fires first

    async def commit(self):  # pragma: no cover
        pass

    async def close(self):
        pass


def test_task_times_out_instead_of_hanging_forever(monkeypatch, fake_calculator):
    monkeypatch.setattr(tasks_module, "_VENUE_STRENGTH_BACKFILL_TASK_TIMEOUT_SECONDS", 0.05)

    async def factory():
        return tasks_module.MarketFeatureRepairContext(
            seeder=None, mappings=None, venue_strength_calculator=fake_calculator, session=_HangingSession(),
        )

    tasks_module.set_market_feature_repair_context_factory(factory)

    with pytest.raises(Exception) as exc_info:
        tasks_module.backfill_venue_strength_for_completed_fixtures_task.apply(kwargs={"now_iso": T0.isoformat()}).get()
    causes = []
    err = exc_info.value
    while err is not None and err not in causes:
        causes.append(err)
        err = getattr(err, "exc", None) or err.__cause__
    assert any(isinstance(c, TimeoutError) for c in causes), f"expected a TimeoutError in {causes!r}"
