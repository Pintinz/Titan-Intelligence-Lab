from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from modules.admin.application.feature_flag_service import (
    FeatureFlagService,
    FlagAlreadyExistsError,
    FlagNotFoundError,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@dataclass
class InMemoryFlagRepo:
    store: dict = field(default_factory=dict)

    async def get(self, flag_id):
        return self.store.get(flag_id)

    async def get_by_key(self, key):
        return next((f for f in self.store.values() if f.key == key), None)

    async def list_all(self):
        return list(self.store.values())

    async def upsert(self, flag):
        self.store[flag.id] = flag
        return flag


@pytest.fixture
def flag_repo():
    return InMemoryFlagRepo()


@pytest.fixture
def service(flag_repo):
    return FeatureFlagService(flags=flag_repo)


@pytest.mark.asyncio
async def test_create_flag_defaults_to_disabled(service):
    flag = await service.create_flag("table_tennis_predictions", "Table Tennis Predictions", "Gate TT markets")

    assert flag.enabled is False
    assert flag.rollout_percentage == 100


@pytest.mark.asyncio
async def test_create_duplicate_flag_raises(service):
    await service.create_flag("k", "n", "d")

    with pytest.raises(FlagAlreadyExistsError):
        await service.create_flag("k", "n2", "d2")


@pytest.mark.asyncio
async def test_enable_and_disable(service):
    await service.create_flag("k", "n", "d")

    enabled = await service.enable("k", T0)
    assert enabled.enabled is True

    disabled = await service.disable("k", T0)
    assert disabled.enabled is False


@pytest.mark.asyncio
async def test_operations_on_unknown_flag_raise(service):
    with pytest.raises(FlagNotFoundError):
        await service.enable("nope", T0)


@pytest.mark.asyncio
async def test_set_rollout_validates_range(service):
    await service.create_flag("k", "n", "d")

    with pytest.raises(ValueError):
        await service.set_rollout("k", 150, T0)


@pytest.mark.asyncio
async def test_is_enabled_false_when_disabled(service):
    await service.create_flag("k", "n", "d", enabled=False)

    assert not await service.is_enabled("k")


@pytest.mark.asyncio
async def test_is_enabled_true_at_full_rollout(service):
    await service.create_flag("k", "n", "d", enabled=True, rollout_percentage=100)

    assert await service.is_enabled("k")
    assert await service.is_enabled("k", context_id="anyone")


@pytest.mark.asyncio
async def test_is_enabled_false_at_zero_rollout(service):
    await service.create_flag("k", "n", "d", enabled=True, rollout_percentage=0)

    assert not await service.is_enabled("k", context_id="anyone")


@pytest.mark.asyncio
async def test_is_enabled_unknown_flag_defaults_false(service):
    assert not await service.is_enabled("nope")


@pytest.mark.asyncio
async def test_partial_rollout_without_context_id_is_false(service):
    await service.create_flag("k", "n", "d", enabled=True, rollout_percentage=50)

    assert not await service.is_enabled("k")  # no context_id to bucket against


@pytest.mark.asyncio
async def test_partial_rollout_is_deterministic_per_context(service):
    await service.create_flag("k", "n", "d", enabled=True, rollout_percentage=50)

    first = await service.is_enabled("k", context_id="user-123")
    second = await service.is_enabled("k", context_id="user-123")

    assert first == second


@pytest.mark.asyncio
async def test_partial_rollout_distributes_across_contexts(service):
    await service.create_flag("k", "n", "d", enabled=True, rollout_percentage=50)

    results = [await service.is_enabled("k", context_id=f"user-{i}") for i in range(200)]

    enabled_count = sum(results)
    # Not asserting an exact number (hash-based bucketing, not a controlled RNG) — just that
    # both outcomes occur and roughly half do, proving it isn't all-or-nothing.
    assert 40 < enabled_count < 160
    assert any(results) and not all(results)
