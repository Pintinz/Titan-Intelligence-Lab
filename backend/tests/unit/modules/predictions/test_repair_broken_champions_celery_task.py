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


def test_repairs_every_broken_market_and_summarizes_results(fake_orchestrator, broken_market, no_champion_market):
    result = tasks_module.repair_broken_champions_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result["total_production_markets"] == 2
    assert result["already_healthy"] == 0
    assert result["attempted_repairs"] == 2
    assert result["repaired"] == 2
    assert result["failed"] == 0
    assert set(fake_orchestrator.repair_calls) == {broken_market.market_key, no_champion_market.market_key}

    entry = next(r for r in result["results"] if r["market_key"] == broken_market.market_key)
    assert entry["was_status"] == "MISSING_ARTIFACT"
    assert entry["repaired"] is True
    assert entry["new_champion_model_key"] == f"{broken_market.market_key}.logistic_regression"

    entry2 = next(r for r in result["results"] if r["market_key"] == no_champion_market.market_key)
    assert entry2["was_status"] == "NO_CHAMPION"


def test_one_market_failing_to_repair_never_blocks_the_rest(fake_orchestrator, broken_market, no_champion_market):
    fake_orchestrator.raise_for = {broken_market.market_key: RuntimeError("dataset build failed")}

    result = tasks_module.repair_broken_champions_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    assert result["attempted_repairs"] == 2
    assert result["repaired"] == 1
    assert result["failed"] == 1
    failed_entry = next(r for r in result["results"] if r["market_key"] == broken_market.market_key)
    assert failed_entry["repaired"] is False
    assert "dataset build failed" in failed_entry["error"]
    # The other market still got a real attempt, unaffected by the first one's crash.
    assert no_champion_market.market_key in fake_orchestrator.repair_calls


def test_a_repair_that_returns_a_skipped_reason_is_not_counted_as_repaired(fake_orchestrator, broken_market, no_champion_market):
    fake_orchestrator.repair_outcomes = {
        broken_market.market_key: RetrainingOutcome(
            market_key=broken_market.market_key, should_retrain=True, reason="artifact repair",
            skipped_reason="preflight failed — insufficient data",
        )
    }

    result = tasks_module.repair_broken_champions_task.apply(kwargs={"now_iso": T0.isoformat()}).get()

    entry = next(r for r in result["results"] if r["market_key"] == broken_market.market_key)
    assert entry["repaired"] is False
    assert entry["skipped_reason"] == "preflight failed — insufficient data"


def test_task_defaults_now_to_current_time_when_not_supplied(fake_orchestrator):
    tasks_module.repair_broken_champions_task.apply(kwargs={}).get()
    assert len(fake_orchestrator.repair_calls) == 2


class _HangingRepairOrchestrator:
    """Simulates a stuck audit/repair (mirrors test_scheduled_retraining_celery_task.py's own
    equivalent) — proves the overall asyncio.wait_for() bound around the whole batch actually
    fires rather than just existing in the source."""

    class markets:
        @staticmethod
        async def list_by_status(status):
            await asyncio.sleep(3600)
            return []  # pragma: no cover — unreachable, the timeout fires first

    models = None
    model_selection = _FakeModelSelection(artifact_store=_AlwaysMissingArtifactStore())


def test_task_times_out_instead_of_hanging_forever(monkeypatch):
    monkeypatch.setattr(tasks_module, "_REPAIR_TASK_TIMEOUT_SECONDS", 0.05)

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
