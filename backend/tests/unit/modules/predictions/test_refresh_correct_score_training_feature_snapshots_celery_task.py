from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.infrastructure.celery import tasks as tasks_module

T0 = datetime(2026, 8, 31, tzinfo=timezone.utc)

_HOME_ATTACK = "football.fixture.home_attack_strength"
_HOME_DEFENCE = "football.fixture.home_defence_strength"
_AWAY_ATTACK = "football.fixture.away_attack_strength"
_AWAY_DEFENCE = "football.fixture.away_defence_strength"


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


@dataclass
class _FakePredictionRow:
    id: object
    feature_snapshot: dict = field(default_factory=dict)


@dataclass
class _FakeAllResult:
    rows: list

    def all(self):
        return self.rows


@dataclass
class _FakeScalarResult:
    value: object

    def first(self):
        return None if self.value is None else (self.value,)


@dataclass
class _FakeSnapshotSession:
    """Distinguishes the one discovery query (no `feature_key` param) from the many per-feature
    value lookups (params carry `feature_key`/`entity_id`) — the task issues both kinds of query
    against the same session, so the fake must route each execute() call correctly rather than
    return one fixed result for everything."""

    discovery_rows: list  # (prediction_id, subject_ref, scheduled_at)
    feature_values: dict = field(default_factory=dict)  # (feature_key, entity_id) -> float | None
    models: dict = field(default_factory=dict)  # prediction_id -> _FakePredictionRow
    committed: bool = False
    commit_count: int = 0
    closed: bool = False
    value_lookup_calls: int = 0

    async def execute(self, _stmt, params=None):
        if params is not None and "feature_key" in params:
            self.value_lookup_calls += 1
            value = self.feature_values.get((params["feature_key"], params["entity_id"]))
            return _FakeScalarResult(value)
        return _FakeAllResult(self.discovery_rows)

    async def get(self, _model_cls, pk):
        return self.models.get(pk)

    async def commit(self):
        self.committed = True
        self.commit_count += 1

    async def close(self):
        self.closed = True


def _row(subject_ref=None, scheduled_at=None):
    return (uuid4(), subject_ref or str(uuid4()), scheduled_at or (T0 - timedelta(days=30)))


@pytest.fixture
def fake_context_factory():
    def _build(session):
        async def factory():
            return tasks_module.MarketFeatureRepairContext(
                seeder=None, mappings=None, venue_strength_calculator=None, expected_goals_calculator=None, session=session,
            )
        return factory
    return _build


@pytest.fixture(autouse=True)
def wired_factory(request):
    tasks_module.set_market_feature_repair_context_factory(None)
    yield
    tasks_module.set_market_feature_repair_context_factory(None)


def _wire(factory):
    tasks_module.set_market_feature_repair_context_factory(factory)


def test_merges_real_venue_strength_values_into_training_snapshots(fake_context_factory):
    prediction_id, subject_ref, scheduled_at = _row()
    session = _FakeSnapshotSession(
        discovery_rows=[(prediction_id, subject_ref, scheduled_at)],
        feature_values={
            (_HOME_ATTACK, subject_ref): 1.2, (_HOME_DEFENCE, subject_ref): 0.9,
            (_AWAY_ATTACK, subject_ref): 1.1, (_AWAY_DEFENCE, subject_ref): 0.8,
        },
        models={prediction_id: _FakePredictionRow(id=prediction_id, feature_snapshot={"expected_home_goals": 1.4})},
    )
    _wire(fake_context_factory(session))

    result = tasks_module.refresh_correct_score_training_feature_snapshots_task.apply(
        kwargs={"now_iso": T0.isoformat()}
    ).get()

    assert result["training_predictions_checked"] == 1
    assert result["training_predictions_updated"] == 1
    assert result["venue_strength_values_added"] == 4

    updated_snapshot = session.models[prediction_id].feature_snapshot
    assert updated_snapshot["expected_home_goals"] == 1.4  # existing key preserved — additive, not destructive
    assert updated_snapshot[_HOME_ATTACK] == 1.2
    assert updated_snapshot[_HOME_DEFENCE] == 0.9
    assert updated_snapshot[_AWAY_ATTACK] == 1.1
    assert updated_snapshot[_AWAY_DEFENCE] == 0.8
    assert session.committed is True
    assert session.closed is True


def test_a_prediction_with_no_available_values_is_left_unmodified(fake_context_factory):
    """Below min_league_sample/window — the calculator's own honest partial-coverage shape.
    Must never fabricate a placeholder value for a feature genuinely unavailable at this cutoff."""
    prediction_id, subject_ref, scheduled_at = _row()
    session = _FakeSnapshotSession(
        discovery_rows=[(prediction_id, subject_ref, scheduled_at)],
        feature_values={},  # nothing available for this fixture
        models={prediction_id: _FakePredictionRow(id=prediction_id, feature_snapshot={"expected_home_goals": 1.4})},
    )
    _wire(fake_context_factory(session))

    result = tasks_module.refresh_correct_score_training_feature_snapshots_task.apply(
        kwargs={"now_iso": T0.isoformat()}
    ).get()

    assert result["training_predictions_updated"] == 0
    assert result["venue_strength_values_added"] == 0
    assert session.models[prediction_id].feature_snapshot == {"expected_home_goals": 1.4}


def test_partial_coverage_adds_only_the_available_keys(fake_context_factory):
    prediction_id, subject_ref, scheduled_at = _row()
    session = _FakeSnapshotSession(
        discovery_rows=[(prediction_id, subject_ref, scheduled_at)],
        feature_values={(_HOME_ATTACK, subject_ref): 1.2},  # only one of the four available
        models={prediction_id: _FakePredictionRow(id=prediction_id)},
    )
    _wire(fake_context_factory(session))

    result = tasks_module.refresh_correct_score_training_feature_snapshots_task.apply(
        kwargs={"now_iso": T0.isoformat()}
    ).get()

    assert result["venue_strength_values_added"] == 1
    assert session.models[prediction_id].feature_snapshot == {_HOME_ATTACK: 1.2}


def test_a_prediction_row_missing_from_the_orm_lookup_is_skipped_not_a_crash(fake_context_factory):
    prediction_id, subject_ref, scheduled_at = _row()
    session = _FakeSnapshotSession(
        discovery_rows=[(prediction_id, subject_ref, scheduled_at)],
        feature_values={(_HOME_ATTACK, subject_ref): 1.2},
        models={},  # session.get() returns None
    )
    _wire(fake_context_factory(session))

    result = tasks_module.refresh_correct_score_training_feature_snapshots_task.apply(
        kwargs={"now_iso": T0.isoformat()}
    ).get()

    assert result["training_predictions_updated"] == 0


def test_commits_in_batches_instead_of_only_once_at_the_end(fake_context_factory):
    batch_size = tasks_module._TRAINING_SNAPSHOT_REFRESH_COMMIT_BATCH_SIZE
    rows = [_row() for _ in range(batch_size * 2 + 3)]
    session = _FakeSnapshotSession(
        discovery_rows=rows,
        feature_values={(_HOME_ATTACK, subject_ref): 1.0 for _, subject_ref, _ in rows},
        models={pid: _FakePredictionRow(id=pid) for pid, _, _ in rows},
    )
    _wire(fake_context_factory(session))

    tasks_module.refresh_correct_score_training_feature_snapshots_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert session.commit_count == 3  # 2 mid-loop batches + 1 final partial batch


def test_task_defaults_now_to_current_time_when_not_supplied(fake_context_factory):
    session = _FakeSnapshotSession(discovery_rows=[])
    _wire(fake_context_factory(session))

    result = tasks_module.refresh_correct_score_training_feature_snapshots_task.apply(kwargs={}).get()

    assert result["training_predictions_checked"] == 0


class _HangingSession:
    async def execute(self, _stmt, params=None):
        await asyncio.sleep(3600)
        return _FakeAllResult([])  # pragma: no cover — unreachable, the timeout fires first

    async def get(self, _model_cls, _pk):  # pragma: no cover
        return None

    async def commit(self):  # pragma: no cover
        pass

    async def close(self):
        pass


def test_task_times_out_instead_of_hanging_forever(monkeypatch):
    monkeypatch.setattr(tasks_module, "_TRAINING_SNAPSHOT_REFRESH_TASK_TIMEOUT_SECONDS", 0.05)

    async def factory():
        return tasks_module.MarketFeatureRepairContext(
            seeder=None, mappings=None, venue_strength_calculator=None, expected_goals_calculator=None, session=_HangingSession(),
        )

    tasks_module.set_market_feature_repair_context_factory(factory)

    with pytest.raises(Exception) as exc_info:
        tasks_module.refresh_correct_score_training_feature_snapshots_task.apply(kwargs={"now_iso": T0.isoformat()}).get()
    causes = []
    err = exc_info.value
    while err is not None and err not in causes:
        causes.append(err)
        err = getattr(err, "exc", None) or err.__cause__
    assert any(isinstance(c, TimeoutError) for c in causes), f"expected a TimeoutError in {causes!r}"
