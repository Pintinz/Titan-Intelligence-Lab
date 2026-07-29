from __future__ import annotations

from uuid import uuid4

import pytest

from modules.predictions.domain.value_objects import ModelId, TargetType
from modules.predictions.infrastructure.ml.local_artifact_store import LocalFilesystemArtifactStore
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService, UnknownModelFrameworkError
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.domain.ml_value_objects import MLAlgorithm
from modules.predictions.ports.ml_model import TrainingSample


def _classification_samples(n: int = 40) -> list[TrainingSample]:
    return [TrainingSample(features={"x1": float(i % 10) - 5.0}, label=1.0 if i % 2 == 0 else 0.0) for i in range(n)]


@pytest.fixture
def artifact_store(tmp_path):
    return LocalFilesystemArtifactStore(root_dir=str(tmp_path / "artifacts"))


@pytest.fixture
def loader(artifact_store):
    return ModelLoaderService(artifact_store=artifact_store)


class TestModelLoaderService:
    async def test_loads_and_deserializes_a_stored_model(self, loader, artifact_store):
        model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        await model.fit(_classification_samples())
        ref = await artifact_store.save("football/match_result/v1.bin", model.serialize())

        model_id = ModelId(uuid4())
        loaded = await loader.load(model_id, "sklearn", "random_forest", TargetType.CLASSIFICATION, ref)

        assert loaded.is_fitted()
        assert loaded.predict_one({"x1": 1.0}).value in {"positive", "negative"}

    async def test_second_load_returns_cached_instance(self, loader, artifact_store):
        model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        await model.fit(_classification_samples())
        ref = await artifact_store.save("football/match_result/v1.bin", model.serialize())
        model_id = ModelId(uuid4())

        first = await loader.load(model_id, "sklearn", "random_forest", TargetType.CLASSIFICATION, ref)
        second = await loader.load(model_id, "sklearn", "random_forest", TargetType.CLASSIFICATION, ref)

        assert first is second
        assert loader.cache_size() == 1

    async def test_invalidate_forces_a_fresh_load(self, loader, artifact_store):
        model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        await model.fit(_classification_samples())
        ref = await artifact_store.save("football/match_result/v1.bin", model.serialize())
        model_id = ModelId(uuid4())

        first = await loader.load(model_id, "sklearn", "random_forest", TargetType.CLASSIFICATION, ref)
        loader.invalidate(model_id)
        assert loader.cache_size() == 0
        second = await loader.load(model_id, "sklearn", "random_forest", TargetType.CLASSIFICATION, ref)

        assert first is not second

    async def test_unknown_framework_raises(self, loader):
        with pytest.raises(UnknownModelFrameworkError):
            await loader.load(ModelId(uuid4()), "tensorflow", "dnn", TargetType.CLASSIFICATION, "unused-ref")

    async def test_loads_lightgbm_framework(self, loader, artifact_store):
        from modules.predictions.infrastructure.ml.lightgbm_adapter import LightGBMAdapter

        model = LightGBMAdapter(target_type=TargetType.CLASSIFICATION)
        await model.fit(_classification_samples())
        ref = await artifact_store.save("football/match_result/lgbm_v1.bin", model.serialize())

        loaded = await loader.load(ModelId(uuid4()), "lightgbm", "lightgbm_gbm", TargetType.CLASSIFICATION, ref)

        assert loaded.is_fitted()
