"""Model Loader + Cache (Milestone 9.1 Model Serving). Reconstructs a fitted `PredictionModelPort`
from a `ModelDefinition`'s ``framework``/``algorithm`` (Milestone 9.1 task #163) + a serialized
payload from `ModelArtifactStorePort`, and caches loaded instances in memory keyed by `ModelId` so
repeated predictions against the same champion don't repeatedly deserialize.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.value_objects import ModelId, TargetType
from modules.predictions.infrastructure.ml.catboost_adapter import CatBoostAdapter
from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import FootballGoalsPoissonAdapter
from modules.predictions.infrastructure.ml.lightgbm_adapter import LightGBMAdapter
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.infrastructure.ml.xgboost_adapter import XGBoostAdapter
from modules.predictions.ports.ml_model import ModelArtifactStorePort, PredictionModelPort


class UnknownModelFrameworkError(ValueError):
    pass


def _empty_adapter(framework: str, algorithm: str, target_type: TargetType) -> PredictionModelPort:
    try:
        fw = MLFramework(framework)
    except ValueError as exc:
        raise UnknownModelFrameworkError(f"unknown framework '{framework}'") from exc

    if fw is MLFramework.LIGHTGBM:
        return LightGBMAdapter(target_type=target_type)
    if fw is MLFramework.XGBOOST:
        return XGBoostAdapter(target_type=target_type)
    if fw is MLFramework.CATBOOST:
        return CatBoostAdapter(target_type=target_type)
    if fw is MLFramework.SKLEARN:
        return SklearnAdapter(algorithm=MLAlgorithm(algorithm), target_type=target_type)
    if fw is MLFramework.POISSON_GOALS:
        # `params`/`class_labels`/`feature_order` all round-trip through `deserialize()` below —
        # an empty adapter here only needs `target_type` to satisfy the constructor.
        return FootballGoalsPoissonAdapter(target_type=target_type)
    raise UnknownModelFrameworkError(f"unknown framework '{framework}'")


@dataclass
class ModelLoaderService:
    artifact_store: ModelArtifactStorePort
    _cache: dict = field(default_factory=dict)  # ModelId -> PredictionModelPort

    async def load(
        self, model_id: ModelId, framework: str, algorithm: str, target_type: TargetType, artifact_ref: str
    ) -> PredictionModelPort:
        cached = self._cache.get(model_id)
        if cached is not None:
            return cached

        adapter = _empty_adapter(framework, algorithm, target_type)
        payload = await self.artifact_store.load(artifact_ref)
        adapter.deserialize(payload)
        self._cache[model_id] = adapter
        return adapter

    def invalidate(self, model_id: ModelId) -> None:
        """Called on rollback/re-promotion (Milestone 9's `ModelRegistryService.rollback`/
        `promote_to_champion`) so a stale cached model never keeps serving after its
        `ModelDefinition` has changed."""
        self._cache.pop(model_id, None)

    def cache_size(self) -> int:
        return len(self._cache)
