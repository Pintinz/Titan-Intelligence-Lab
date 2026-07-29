from __future__ import annotations

import shutil

import pytest

from modules.predictions.infrastructure.ml.local_artifact_store import LocalFilesystemArtifactStore


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "artifacts"
    yield LocalFilesystemArtifactStore(root_dir=str(root))
    shutil.rmtree(root, ignore_errors=True)


async def test_save_then_load_roundtrips_bytes(store):
    ref = await store.save("football/match_result/v1.bin", b"model-bytes")
    assert await store.load(ref) == b"model-bytes"


async def test_save_creates_nested_directories(store):
    ref = await store.save("a/b/c/model.bin", b"payload")
    assert await store.load(ref) == b"payload"
