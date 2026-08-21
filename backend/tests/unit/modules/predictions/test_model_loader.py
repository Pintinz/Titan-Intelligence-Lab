"""Tests for `ModelLoaderService`/`_empty_adapter` — specifically the `MLFramework.POISSON_GOALS`
branch that was missing entirely (confirmed via `dev.db`: reloading any of the 3 real Poisson
challenger artifacts already trained there raised `UnknownModelFrameworkError` before this fix).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from modules.predictions.domain.ml_value_objects import MLFramework
from modules.predictions.domain.value_objects import ModelId, TargetType
from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import FootballGoalsPoissonAdapter
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService, UnknownModelFrameworkError, _empty_adapter
from modules.predictions.ports.ml_model import TrainingSample


@dataclass
class _InMemoryArtifactStore:
    store: dict = field(default_factory=dict)

    async def save(self, key: str, payload: bytes) -> str:
        self.store[key] = payload
        return key

    async def load(self, ref: str) -> bytes:
        return self.store[ref]


class TestEmptyAdapter:
    def test_poisson_goals_framework_resolves_to_football_goals_poisson_adapter(self):
        adapter = _empty_adapter(MLFramework.POISSON_GOALS.value, "poisson_goals_model", TargetType.CLASSIFICATION)
        assert isinstance(adapter, FootballGoalsPoissonAdapter)

    def test_unknown_framework_still_raises(self):
        with pytest.raises(UnknownModelFrameworkError):
            _empty_adapter("not_a_real_framework", "whatever", TargetType.CLASSIFICATION)


class TestLoadRoundTrip:
    async def test_load_reconstructs_a_fitted_poisson_model_from_its_artifact(self):
        """Real fit -> serialize -> save -> load -> predict_one, the exact path a live Poisson
        Champion/Challenger reload takes — this was the concrete `UnknownModelFrameworkError`
        confirmed against dev.db's 3 existing `poisson_goals_model` v6 rows before the fix."""
        adapter = FootballGoalsPoissonAdapter(params={"market_shape": "total_threshold", "line": 2.5})
        samples = [
            TrainingSample(
                features={"x1": float(i % 10)}, label=0.0,
                raw_home_goals=max(0.0, round(0.35 * (i % 10))), raw_away_goals=max(0.0, round(0.10 * (i % 10))),
            )
            for i in range(40)
        ]
        await adapter.fit(samples)

        artifacts = _InMemoryArtifactStore()
        ref = await artifacts.save("test.poisson.bin", adapter.serialize())

        loader = ModelLoaderService(artifact_store=artifacts)
        reloaded = await loader.load(ModelId(uuid4()), MLFramework.POISSON_GOALS.value, "poisson_goals_model", TargetType.CLASSIFICATION, ref)

        assert isinstance(reloaded, FootballGoalsPoissonAdapter)
        assert reloaded.is_fitted()
        prediction = reloaded.predict_one({"x1": 5.0})
        assert 0.0 <= prediction.probability <= 1.0
