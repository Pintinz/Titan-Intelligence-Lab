from __future__ import annotations

from uuid import uuid4

import pytest

from modules.predictions.domain.value_objects import ModelId, TargetType
from modules.predictions.infrastructure.ml.local_artifact_store import LocalFilesystemArtifactStore
from modules.predictions.infrastructure.ml.model_loader import (
    ArtifactIntegrityError,
    ModelLoaderService,
    UnknownModelFrameworkError,
    compute_artifact_checksum,
)
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

    # --- Forensic audit §15 "Model Artifact Integrity" ------------------------------------------

    async def test_matching_checksum_loads_normally(self, loader, artifact_store):
        model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        await model.fit(_classification_samples())
        payload = model.serialize()
        ref = await artifact_store.save("football/match_result/v1.bin", payload)
        checksum = compute_artifact_checksum(payload)

        loaded = await loader.load(
            ModelId(uuid4()), "sklearn", "random_forest", TargetType.CLASSIFICATION, ref, checksum,
        )

        assert loaded.is_fitted()

    async def test_mismatched_checksum_raises_artifact_integrity_error(self, loader, artifact_store):
        """The exact scenario §15 exists to catch: the artifact at `artifact_ref` no longer hashes
        to what was recorded when this model version was registered — corrupted, overwritten, or
        swapped out-of-band since training."""
        model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        await model.fit(_classification_samples())
        ref = await artifact_store.save("football/match_result/v1.bin", model.serialize())

        with pytest.raises(ArtifactIntegrityError):
            await loader.load(
                ModelId(uuid4()), "sklearn", "random_forest", TargetType.CLASSIFICATION, ref,
                "0" * 64,  # a checksum that cannot possibly match the real artifact
            )

    async def test_no_checksum_recorded_skips_verification(self, loader, artifact_store):
        """A model registered before this field existed (or by a training path that hasn't been
        updated to compute one) must load exactly as before — `None` is "never checked", not
        itself a failure."""
        model = SklearnAdapter(algorithm=MLAlgorithm.RANDOM_FOREST, target_type=TargetType.CLASSIFICATION)
        await model.fit(_classification_samples())
        ref = await artifact_store.save("football/match_result/v1.bin", model.serialize())

        loaded = await loader.load(
            ModelId(uuid4()), "sklearn", "random_forest", TargetType.CLASSIFICATION, ref, None,
        )

        assert loaded.is_fitted()

    def test_compute_artifact_checksum_is_deterministic_and_content_sensitive(self):
        assert compute_artifact_checksum(b"abc") == compute_artifact_checksum(b"abc")
        assert compute_artifact_checksum(b"abc") != compute_artifact_checksum(b"abd")
