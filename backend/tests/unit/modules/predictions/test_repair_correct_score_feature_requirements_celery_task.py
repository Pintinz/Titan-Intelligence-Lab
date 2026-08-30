from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
class _FakeSeeder:
    seed_calls: list = field(default_factory=list)

    async def seed(self, now):
        self.seed_calls.append(now)


@dataclass
class _FakeMappings:
    raise_keyerror_for: set = field(default_factory=set)
    set_required_calls: list = field(default_factory=list)

    async def set_required(self, market_key, feature_key, is_required):
        if feature_key in self.raise_keyerror_for:
            raise KeyError(feature_key)
        self.set_required_calls.append((market_key, feature_key, is_required))


@dataclass
class _FakeVenueStrengthCalculator:
    unwritable_fixture_ids: set = field(default_factory=set)
    compute_calls: list = field(default_factory=list)

    async def compute_and_write(self, fixture_id, home_team_id, away_team_id, sport_id, season_id, now):
        self.compute_calls.append(fixture_id)
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

    async def execute(self, _stmt):
        return _FakeResult(self.rows)

    async def commit(self):
        self.committed = True

    async def close(self):
        self.closed = True


def _upcoming_fixture_row():
    return (str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()))


@pytest.fixture
def upcoming_rows():
    return [_upcoming_fixture_row(), _upcoming_fixture_row()]


@pytest.fixture
def fake_seeder():
    return _FakeSeeder()


@pytest.fixture
def fake_mappings():
    return _FakeMappings()


@pytest.fixture
def fake_calculator():
    return _FakeVenueStrengthCalculator()


@pytest.fixture
def fake_session(upcoming_rows):
    return _FakeSession(rows=upcoming_rows)


@pytest.fixture
def fake_context(fake_seeder, fake_mappings, fake_calculator, fake_session):
    return tasks_module.MarketFeatureRepairContext(
        seeder=fake_seeder, mappings=fake_mappings, venue_strength_calculator=fake_calculator, session=fake_session,
    )


@pytest.fixture(autouse=True)
def wire_factory(fake_context):
    async def factory():
        return fake_context

    tasks_module.set_market_feature_repair_context_factory(factory)
    yield
    tasks_module.set_market_feature_repair_context_factory(None)


def test_seeds_demotes_stale_features_and_backfills_upcoming_fixtures(
    fake_seeder, fake_mappings, fake_calculator, fake_session, upcoming_rows
):
    result = tasks_module.repair_correct_score_feature_requirements_task.apply(
        kwargs={"now_iso": T0.isoformat()}
    ).get()

    assert len(fake_seeder.seed_calls) == 1
    assert fake_mappings.set_required_calls == [
        ("football.correct_score", "football.fixture.expected_home_goals", False),
        ("football.correct_score", "football.fixture.expected_away_goals", False),
    ]
    assert len(fake_calculator.compute_calls) == len(upcoming_rows)
    assert fake_session.committed is True
    assert fake_session.closed is True

    assert result["demoted_to_optional"] == [
        "football.fixture.expected_home_goals", "football.fixture.expected_away_goals",
    ]
    assert result["upcoming_football_fixtures_checked"] == len(upcoming_rows)
    assert result["venue_strength_backfilled"] == len(upcoming_rows)


def test_a_fixture_the_calculator_cant_compute_for_is_not_counted_as_backfilled(fake_calculator, upcoming_rows):
    unwritable_id = upcoming_rows[0][0]
    fake_calculator.unwritable_fixture_ids = {unwritable_id}

    result = tasks_module.repair_correct_score_feature_requirements_task.apply(
        kwargs={"now_iso": T0.isoformat()}
    ).get()

    assert result["venue_strength_backfilled"] == len(upcoming_rows) - 1
    assert result["upcoming_football_fixtures_checked"] == len(upcoming_rows)


def test_a_mapping_already_demoted_is_tolerated_not_a_crash(fake_mappings):
    """`set_required` raises KeyError when the (market, feature) pair isn't mapped at all — this
    task must never crash on that, since a re-run after a prior successful run (or a market that
    was already fixed some other way) should be a safe, cheap no-op for that feature."""
    fake_mappings.raise_keyerror_for = {"football.fixture.expected_home_goals"}

    result = tasks_module.repair_correct_score_feature_requirements_task.apply(
        kwargs={"now_iso": T0.isoformat()}
    ).get()

    assert result["demoted_to_optional"] == ["football.fixture.expected_away_goals"]


def test_task_defaults_now_to_current_time_when_not_supplied(fake_seeder):
    tasks_module.repair_correct_score_feature_requirements_task.apply(kwargs={}).get()
    assert len(fake_seeder.seed_calls) == 1


class _HangingSession:
    async def execute(self, _stmt):
        await asyncio.sleep(3600)
        return _FakeResult([])  # pragma: no cover — unreachable, the timeout fires first

    async def commit(self):  # pragma: no cover
        pass

    async def close(self):
        pass


def test_task_times_out_instead_of_hanging_forever(monkeypatch, fake_seeder, fake_mappings, fake_calculator):
    monkeypatch.setattr(tasks_module, "_FEATURE_REPAIR_TASK_TIMEOUT_SECONDS", 0.05)

    async def factory():
        return tasks_module.MarketFeatureRepairContext(
            seeder=fake_seeder, mappings=fake_mappings, venue_strength_calculator=fake_calculator,
            session=_HangingSession(),
        )

    tasks_module.set_market_feature_repair_context_factory(factory)

    with pytest.raises(Exception) as exc_info:
        tasks_module.repair_correct_score_feature_requirements_task.apply(kwargs={"now_iso": T0.isoformat()}).get()
    causes = []
    err = exc_info.value
    while err is not None and err not in causes:
        causes.append(err)
        err = getattr(err, "exc", None) or err.__cause__
    assert any(isinstance(c, TimeoutError) for c in causes), f"expected a TimeoutError in {causes!r}"
