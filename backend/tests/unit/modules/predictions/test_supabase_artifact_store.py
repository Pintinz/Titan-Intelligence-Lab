from __future__ import annotations

import httpx
import pytest

from modules.predictions.infrastructure.ml.supabase_artifact_store import (
    ArtifactStoreError,
    SupabaseStorageArtifactStore,
)

_PROJECT_URL = "https://example.supabase.co"
_SERVICE_ROLE_KEY = "service-role-test-key"


def _store(handler) -> SupabaseStorageArtifactStore:
    client = httpx.AsyncClient(
        base_url=_PROJECT_URL,
        headers={"apikey": _SERVICE_ROLE_KEY, "Authorization": f"Bearer {_SERVICE_ROLE_KEY}"},
        transport=httpx.MockTransport(handler),
    )
    return SupabaseStorageArtifactStore(
        project_url=_PROJECT_URL, service_role_key=_SERVICE_ROLE_KEY, _client=client
    )


async def test_constructing_without_an_injected_client_builds_one_with_the_real_auth_headers():
    """The tests below inject a pre-built client (with its own headers) to isolate save/load
    logic from a real network client — this test instead exercises `__post_init__`'s own client
    construction, the code path every real (non-test) instantiation actually takes."""
    store = SupabaseStorageArtifactStore(project_url=_PROJECT_URL, service_role_key=_SERVICE_ROLE_KEY)
    try:
        assert store._client.headers["apikey"] == _SERVICE_ROLE_KEY
        assert store._client.headers["authorization"] == f"Bearer {_SERVICE_ROLE_KEY}"
        assert str(store._client.base_url).rstrip("/") == _PROJECT_URL
    finally:
        await store.aclose()


async def test_save_posts_to_the_bucket_object_path_and_returns_a_bucket_qualified_ref():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = request.content
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"Key": "model-artifacts/football/correct_score/v3.bin"})

    store = _store(handler)

    ref = await store.save("football/correct_score/v3.bin", b"pickled-model-bytes")

    assert ref == "model-artifacts/football/correct_score/v3.bin"
    assert captured["method"] == "POST"
    assert captured["url"] == f"{_PROJECT_URL}/storage/v1/object/model-artifacts/football/correct_score/v3.bin"
    assert captured["body"] == b"pickled-model-bytes"
    assert captured["headers"]["authorization"] == f"Bearer {_SERVICE_ROLE_KEY}"
    assert captured["headers"]["apikey"] == _SERVICE_ROLE_KEY


async def test_save_upserts_so_a_retrain_can_overwrite_the_same_key():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["upsert_header"] = request.headers.get("x-upsert")
        return httpx.Response(200, json={"Key": "model-artifacts/x.bin"})

    store = _store(handler)
    await store.save("x.bin", b"payload")

    assert captured["upsert_header"] == "true"


async def test_save_raises_artifact_store_error_on_a_failed_upload():
    store = _store(lambda request: httpx.Response(403, text="permission denied"))

    with pytest.raises(ArtifactStoreError, match="upload failed"):
        await store.save("x.bin", b"payload")


async def test_load_gets_from_the_bucket_object_path_and_returns_raw_bytes():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        return httpx.Response(200, content=b"pickled-model-bytes")

    store = _store(handler)

    payload = await store.load("model-artifacts/football/correct_score/v3.bin")

    assert payload == b"pickled-model-bytes"
    assert captured["method"] == "GET"
    assert captured["url"] == f"{_PROJECT_URL}/storage/v1/object/model-artifacts/football/correct_score/v3.bin"


async def test_load_accepts_a_bare_key_without_the_bucket_prefix():
    """`save()` always returns a bucket-qualified ref, but a caller (or an older ref stored before
    this format existed) might pass a bare key — both must resolve to the same object path."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, content=b"payload")

    store = _store(handler)

    payload = await store.load("football/correct_score/v3.bin")

    assert payload == b"payload"
    assert captured["url"] == f"{_PROJECT_URL}/storage/v1/object/model-artifacts/football/correct_score/v3.bin"


async def test_load_raises_artifact_store_error_when_the_object_is_missing():
    store = _store(lambda request: httpx.Response(404, text="object not found"))

    with pytest.raises(ArtifactStoreError, match="download failed"):
        await store.load("missing.bin")


async def test_save_then_load_roundtrips_through_a_single_in_memory_object_store():
    """End-to-end against a fake in-memory bucket (not just per-call header/URL assertions) —
    proves the ref `save()` returns is exactly what `load()` needs, the same contract
    `test_local_artifact_store.py` verifies for the filesystem adapter."""
    objects: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/storage/v1/object/")
        if request.method == "POST":
            objects[path] = request.content
            return httpx.Response(200, json={"Key": path})
        if path not in objects:
            return httpx.Response(404, text="not found")
        return httpx.Response(200, content=objects[path])

    store = _store(handler)

    ref = await store.save("basketball/moneyline/champion.bin", b"real-artifact-bytes")

    assert await store.load(ref) == b"real-artifact-bytes"
