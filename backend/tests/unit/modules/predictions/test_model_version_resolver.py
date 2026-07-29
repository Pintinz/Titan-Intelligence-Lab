from __future__ import annotations

from uuid import uuid4

import pytest

from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.model_version_resolver import (
    ModelVersionNotFoundError,
    ModelVersionResolver,
    PinnedVersionRequiresModelKeyError,
)
from modules.predictions.domain.value_objects import MarketId

T0 = None


@pytest.fixture
def market_id():
    return MarketId(uuid4())


@pytest.fixture
def registry(model_repo):
    return ModelRegistryService(models=model_repo)


@pytest.fixture
def resolver(model_repo):
    return ModelVersionResolver(models=model_repo)


class TestResolve:
    async def test_resolves_champion_by_default(self, resolver, registry, market_id):
        from datetime import datetime, timezone

        now = datetime(2026, 7, 26, tzinfo=timezone.utc)
        model = await registry.register(market_id, "football.match_result", 1, "heuristic_logistic_v1", now=now)
        await registry.promote_to_challenger(model.id)
        champion = await registry.promote_to_champion(model.id, approved_by="cto", now=now)

        resolved = await resolver.resolve(market_id)

        assert resolved.id == champion.id

    async def test_no_champion_raises(self, resolver, market_id):
        with pytest.raises(ModelVersionNotFoundError):
            await resolver.resolve(market_id)

    async def test_resolves_pinned_version(self, resolver, registry, market_id):
        from datetime import datetime, timezone

        now = datetime(2026, 7, 26, tzinfo=timezone.utc)
        v1 = await registry.register(market_id, "football.match_result", 1, "heuristic_logistic_v1", now=now)
        await registry.register(market_id, "football.match_result", 2, "lightgbm_gbm", now=now)

        resolved = await resolver.resolve(market_id, model_key="football.match_result", pinned_version=1)

        assert resolved.id == v1.id

    async def test_pinned_version_requires_model_key(self, resolver, market_id):
        with pytest.raises(PinnedVersionRequiresModelKeyError):
            await resolver.resolve(market_id, pinned_version=1)

    async def test_unknown_pinned_version_raises(self, resolver, registry, market_id):
        from datetime import datetime, timezone

        now = datetime(2026, 7, 26, tzinfo=timezone.utc)
        await registry.register(market_id, "football.match_result", 1, "heuristic_logistic_v1", now=now)

        with pytest.raises(ModelVersionNotFoundError):
            await resolver.resolve(market_id, model_key="football.match_result", pinned_version=99)
