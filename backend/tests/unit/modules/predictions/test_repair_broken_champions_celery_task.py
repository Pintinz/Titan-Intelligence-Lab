from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.application.scheduled_retraining_orchestrator import RetrainingOutcome
from modules.predictions.domain.entities import MarketDefinition, ModelDefinition
from modules.predictions.domain.value_objects import MarketId, MarketKind, MarketStatus, ModelId, ModelStatus, TargetType
from modules.predictions.infrastructure.celery import tasks as tasks_module
from modules.predictions.infrastructure.ml.supabase_artifact_store import ArtifactStoreError

T0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def eager_celery():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


def _market(key: str) -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key=key, sport_code="football", name="Test", category="goals",
        market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION, status=MarketStatus.PRODUCTION,
    )


def _broken_champion(market: MarketDefinition) -> ModelDefinition:
    return ModelDefinition(
        id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.svm", version=1,
        algorithm="svm", framework="sklearn", status=ModelStatus.CHAMPION, artifact_ref="nowhere/v1.bin",
    )


def _repaired_challenger(market: MarketDefinition) -> ModelDefinition:
    return ModelDefinition(
        id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.logistic_regression", version=2,
        algorithm="logistic_regression", framework="sklearn", status=ModelStatus.CHALLENGER, artifact_ref="real/v2.bin",
    )


@dataclass
class _FakeMarketRepo:
    markets: list

    async def list_by_status(self, status):
        return self.markets

    async def get_by_key(self, market_key):
        return next((m for m in self.markets if m.market_key == market_key), None)


@dataclass
class _FakeModelRepo:
    champions_by_market_id: dict

    async def get_champion(self, market_id):
        return self.champions_by_market_id.get(market_id)


class _AlwaysMissingArtifactStore:
    """Every load() fails — makes every seeded market classify MISSING_ARTIFACT/NO_CHAMPION,
    matching the real 2026-08-29 incident's shape closely enough for this task-layer test without
    needing a genuinely deserializable model payload."""

    async def load(self, ref: str) -> bytes:
        raise ArtifactStoreError(f"download failed for '{ref}'")


@dataclass
class _FakeModelSelection:
    artifact_store: object


class FakeRepairOrchestrator:
    def __init__(self, markets, champions_by_market_id, repair_outcomes=None, raise_for=None):
        self.markets = _FakeMarketRepo(markets)
        self.models = _FakeModelRepo(champions_by_market_id)
        self.model_selection = _FakeModelSelection(artifact_store=_AlwaysMissingArtifactStore())
        self.repair_outcomes = repair_outcomes or {}
        self.raise_for = raise_for or {}
        self.repair_calls = []

    async def repair_broken_champion(self, market, now):
        self.repair_calls.append(market.market_key)
        if market.market_key in self.raise_for:
            raise self.raise_for[market.market_key]
        if market.market_key in self.repair_outcomes:
            return self.repair_outcomes[market.market_key]
        return RetrainingOutcome(
            market_key=market.market_key, should_retrain=True, reason="artifact repair",
            challenger=_repaired_challenger(market), bootstrapped=True,
        )


@pytest.fixture
def broken_market():
    return _market("football.both_teams_to_score")


@pytest.fixture
def no_champion_market():
    return _market("basketball.moneyline")


@pytest.fixture
def fake_orchestrator(broken_market, no_champion_market):
    return FakeRepairOrchestrator(
        markets=[broken_market, no_champion_market],
        champions_by_market_id={broken_market.id: _broken_champion(broken_market)},
    )


@pytest.fixture(autouse=True)
def wire_factory(fake_orchestrator):
    async def factory():
        return fake_orchestrator

    tasks_module.set_retraining_orchestrator_factory(factory)
    yield
    tasks_module.set_retraining_orchestrator_factory(None)


# --- Dispatcher (predictions.repair_broken_champions): audits and fans out, never repairs inline ---


class _FakeDispatchResult:
    def __init__(self, task_id: str):
        self.id = task_id


def test_dispatcher_audits_and_dispatches_one_task_per_broken_market(
    monkeypatch, fake_orchestrator, broken_market, no_champion_market
):
    # The dispatcher's own job is audit + call .delay() with the right market_key — the actual
    # repair logic is covered separately by the repair_one_champion_task tests below. Monkeypatched
    # rather than left to really fire: under task_always_eager, .delay() runs the per-market task
    # SYNCHRONOUSLY inside the dispatcher's own asyncio.run() call, which is a real
    # "asyncio.run() cannot be called from a running event loop" error — a test-harness artifact of
    # eager mode (a genuine `.delay()` in production just publishes and returns immediately), not a
    # production bug, but it means this test must isolate dispatch from execution to be valid.
    dispatch_calls = []

    def fake_delay(market_key, now_iso=None):
        dispatch_calls.append((market_key, now_iso))
        return _FakeDispatchResult(task_id=f"task-for-{market_key}")

    monkeypatch.setattr(tasks_module.repair_one_champion_task, "delay", fake_delay)

    result = tasks_module.repair_broken_champions_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result["total_production_markets"] == 2
    assert result["already_healthy"] == 0
    assert result["dispatched_repairs"] == 2
    dispatched_keys = {r["market_key"] for r in result["results"]}
    assert dispatched_keys == {broken_market.market_key, no_champion_market.market_key}
    for entry in result["results"]:
        assert entry["task_id"] == f"task-for-{entry['market_key']}"
    assert {key for key, _ in dispatch_calls} == {broken_market.market_key, no_champion_market.market_key}
    # The orchestrator's real repair method was never called by the dispatcher itself.
    assert fake_orchestrator.repair_calls == []


def test_dispatcher_defaults_now_to_current_time_when_not_supplied(monkeypatch, fake_orchestrator):
    dispatch_calls = []
    monkeypatch.setattr(
        tasks_module.repair_one_champion_task, "delay",
        lambda market_key, now_iso=None: dispatch_calls.append(market_key) or _FakeDispatchResult(task_id="x"),
    )

    tasks_module.repair_broken_champions_task.apply(kwargs={}).get()

    assert len(dispatch_calls) == 2


class _HangingRepairOrchestrator:
    """Simulates a stuck audit (mirrors test_scheduled_retraining_celery_task.py's own
    equivalent) — proves the dispatcher's own asyncio.wait_for() bound actually fires rather than
    just existing in the source. The dispatcher is audit-only now, so this only needs to hang the
    audit's own list_by_status call, not a full repair loop."""

    class markets:
        @staticmethod
        async def list_by_status(status):
            await asyncio.sleep(3600)
            return []  # pragma: no cover — unreachable, the timeout fires first

    models = None
    model_selection = _FakeModelSelection(artifact_store=_AlwaysMissingArtifactStore())


def test_dispatcher_times_out_instead_of_hanging_forever(monkeypatch):
    monkeypatch.setattr(tasks_module, "_AUDIT_ONLY_TIMEOUT_SECONDS", 0.05)

    async def factory():
        return _HangingRepairOrchestrator()

    tasks_module.set_retraining_orchestrator_factory(factory)

    with pytest.raises(Exception) as exc_info:
        tasks_module.repair_broken_champions_task.apply(kwargs={"now_iso": T0.isoformat()}).get()
    causes = []
    err = exc_info.value
    while err is not None and err not in causes:
        causes.append(err)
        err = getattr(err, "exc", None) or err.__cause__
    assert any(isinstance(c, TimeoutError) for c in causes), f"expected a TimeoutError in {causes!r}"


# --- Per-market unit of work (predictions.repair_one_champion) --------------------------------


def test_repair_one_champion_repairs_the_named_market(fake_orchestrator, broken_market):
    result = tasks_module.repair_one_champion_task.apply(
        kwargs={"market_key": broken_market.market_key, "now_iso": T0.isoformat()}
    ).get()

    assert result["market_key"] == broken_market.market_key
    assert result["repaired"] is True
    assert result["new_champion_model_key"] == f"{broken_market.market_key}.logistic_regression"
    assert fake_orchestrator.repair_calls == [broken_market.market_key]


def test_repair_one_champion_reports_a_raised_error_without_crashing(fake_orchestrator, broken_market):
    fake_orchestrator.raise_for = {broken_market.market_key: RuntimeError("dataset build failed")}

    result = tasks_module.repair_one_champion_task.apply(
        kwargs={"market_key": broken_market.market_key, "now_iso": T0.isoformat()}
    ).get()

    assert result["repaired"] is False
    assert "dataset build failed" in result["error"]


def test_repair_one_champion_with_a_skipped_reason_is_not_counted_as_repaired(fake_orchestrator, broken_market):
    fake_orchestrator.repair_outcomes = {
        broken_market.market_key: RetrainingOutcome(
            market_key=broken_market.market_key, should_retrain=True, reason="artifact repair",
            skipped_reason="preflight failed — insufficient data",
        )
    }

    result = tasks_module.repair_one_champion_task.apply(
        kwargs={"market_key": broken_market.market_key, "now_iso": T0.isoformat()}
    ).get()

    assert result["repaired"] is False
    assert result["skipped_reason"] == "preflight failed — insufficient data"


def test_repair_one_champion_for_a_market_that_no_longer_exists_reports_honestly(fake_orchestrator):
    result = tasks_module.repair_one_champion_task.apply(
        kwargs={"market_key": "football.deleted_market", "now_iso": T0.isoformat()}
    ).get()

    assert result["repaired"] is False
    assert "no longer exists" in result["error"]
    assert fake_orchestrator.repair_calls == []


def test_one_markets_failure_never_reaches_the_others_separate_invocation(fake_orchestrator, broken_market, no_champion_market):
    """The whole point of the dispatch split — each market is its own task invocation, so one
    market raising can never affect another's, unlike the old inline-loop shape."""
    fake_orchestrator.raise_for = {broken_market.market_key: RuntimeError("dataset build failed")}

    failed = tasks_module.repair_one_champion_task.apply(
        kwargs={"market_key": broken_market.market_key, "now_iso": T0.isoformat()}
    ).get()
    healthy_attempt = tasks_module.repair_one_champion_task.apply(
        kwargs={"market_key": no_champion_market.market_key, "now_iso": T0.isoformat()}
    ).get()

    assert failed["repaired"] is False
    assert healthy_attempt["repaired"] is True


def test_repair_one_champion_times_out_instead_of_hanging_forever(monkeypatch):
    monkeypatch.setattr(tasks_module, "_REPAIR_ONE_MARKET_TIMEOUT_SECONDS", 0.05)

    class _HangingOneMarketOrchestrator:
        class markets:
            @staticmethod
            async def get_by_key(market_key):
                await asyncio.sleep(3600)
                return None  # pragma: no cover — unreachable, the timeout fires first

    async def factory():
        return _HangingOneMarketOrchestrator()

    tasks_module.set_retraining_orchestrator_factory(factory)

    with pytest.raises(Exception) as exc_info:
        tasks_module.repair_one_champion_task.apply(kwargs={"market_key": "football.x", "now_iso": T0.isoformat()}).get()
    causes = []
    err = exc_info.value
    while err is not None and err not in causes:
        causes.append(err)
        err = getattr(err, "exc", None) or err.__cause__
    assert any(isinstance(c, TimeoutError) for c in causes), f"expected a TimeoutError in {causes!r}"
