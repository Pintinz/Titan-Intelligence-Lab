"""Forensic audit finding #8 (2026-08-30): `get_model_artifact_store` must never silently fall
back to `LocalFilesystemArtifactStore` outside development — that credential-presence-only gate
is exactly how the 2026-08-23 incident happened (40/53 production markets lost their trained
Champion artifacts on the next deploy, because a missing TITANIQ_SUPABASE_SERVICE_ROLE_KEY
silently degraded storage to the container's ephemeral local disk instead of failing loudly)."""

from __future__ import annotations

import pytest

from apps.api import composition
from modules.predictions.infrastructure.ml.local_artifact_store import LocalFilesystemArtifactStore
from modules.predictions.infrastructure.ml.supabase_artifact_store import SupabaseStorageArtifactStore


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.delenv("TITANIQ_ENVIRONMENT", raising=False)
    monkeypatch.delenv("TITANIQ_SUPABASE_SERVICE_ROLE_KEY", raising=False)
    composition.get_model_artifact_store.cache_clear()
    yield
    composition.get_model_artifact_store.cache_clear()


def test_uses_supabase_storage_when_credential_is_present(monkeypatch):
    monkeypatch.setenv("TITANIQ_SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("TITANIQ_SUPABASE_PROJECT_URL", "https://example.supabase.co")

    store = composition.get_model_artifact_store()

    assert isinstance(store, SupabaseStorageArtifactStore)


def test_falls_back_to_local_storage_in_development_without_the_credential():
    store = composition.get_model_artifact_store()

    assert isinstance(store, LocalFilesystemArtifactStore)


def test_refuses_to_start_in_staging_without_the_credential(monkeypatch):
    monkeypatch.setenv("TITANIQ_ENVIRONMENT", "staging")

    with pytest.raises(RuntimeError, match="TITANIQ_SUPABASE_SERVICE_ROLE_KEY is not set"):
        composition.get_model_artifact_store()


def test_refuses_to_start_in_production_without_the_credential(monkeypatch):
    monkeypatch.setenv("TITANIQ_ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="TITANIQ_SUPABASE_SERVICE_ROLE_KEY is not set"):
        composition.get_model_artifact_store()


def test_production_with_the_credential_still_uses_durable_storage(monkeypatch):
    monkeypatch.setenv("TITANIQ_ENVIRONMENT", "production")
    monkeypatch.setenv("TITANIQ_SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("TITANIQ_SUPABASE_PROJECT_URL", "https://example.supabase.co")

    store = composition.get_model_artifact_store()

    assert isinstance(store, SupabaseStorageArtifactStore)
