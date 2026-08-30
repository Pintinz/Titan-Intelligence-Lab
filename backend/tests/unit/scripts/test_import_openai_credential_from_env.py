"""Tests for `scripts/import_openai_credential_from_env.py`'s `import_openai_credential` — the
one-time activation path for the OpenAI adapter (now `TextIntelligenceRouter`'s `real_adapter`).
Pure logic over an injected `ProviderManagementService`, no real DB or network involved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from modules.admin.application.provider_management_service import ProviderManagementService
from modules.intelligence.infrastructure.openai_adapter import OpenAIAdapter
from scripts.import_openai_credential_from_env import import_openai_credential

T0 = datetime(2026, 8, 30, tzinfo=timezone.utc)


@dataclass
class _InMemoryProviderRepo:
    store: dict = field(default_factory=dict)

    async def get(self, provider_id):
        return self.store.get(provider_id)

    async def get_by_key(self, key):
        return next((p for p in self.store.values() if p.key == key), None)

    async def list_all(self):
        return list(self.store.values())

    async def upsert(self, provider):
        self.store[provider.id] = provider
        return provider


@dataclass
class _InMemoryCredentialRepo:
    store: dict = field(default_factory=dict)

    async def get(self, credential_id):
        return self.store.get(credential_id)

    async def list_by_provider(self, provider_id):
        return [c for c in self.store.values() if c.provider_id == provider_id]

    async def upsert(self, credential):
        self.store[credential.id] = credential
        return credential

    async def delete(self, credential_id):
        self.store.pop(credential_id, None)


class _NoopVault:
    def encrypt(self, plaintext):
        return plaintext

    def decrypt(self, ciphertext):
        return ciphertext


def _admin_service():
    return ProviderManagementService(providers=_InMemoryProviderRepo(), credentials=_InMemoryCredentialRepo(), vault=_NoopVault())


async def test_returns_none_when_env_var_is_not_set(monkeypatch):
    monkeypatch.delenv("TITANIQ_OPENAI_API_KEY", raising=False)
    admin_service = _admin_service()

    result = await import_openai_credential(admin_service, T0)

    assert result is None
    assert await admin_service.providers.get_by_key("openai") is None


async def test_registers_the_openai_provider_and_credential(monkeypatch):
    monkeypatch.setenv("TITANIQ_OPENAI_API_KEY", "sk-test-key")
    admin_service = _admin_service()

    result = await import_openai_credential(admin_service, T0)

    assert result is not None
    provider, credential = result
    assert provider.key == OpenAIAdapter.provider_key
    assert provider.name == "OpenAI"
    usable = await admin_service.usable_credentials(provider.id)
    assert len(usable) == 1
    assert await admin_service.reveal_plaintext(credential.id) == "sk-test-key"


async def test_running_twice_recredentials_the_same_provider_not_a_duplicate(monkeypatch):
    monkeypatch.setenv("TITANIQ_OPENAI_API_KEY", "sk-first-key")
    admin_service = _admin_service()
    first = await import_openai_credential(admin_service, T0)

    monkeypatch.setenv("TITANIQ_OPENAI_API_KEY", "sk-second-key")
    second = await import_openai_credential(admin_service, T0)

    assert first is not None and second is not None
    assert first[0].id == second[0].id  # same provider, not a duplicate registration
    providers = await admin_service.providers.list_all()
    assert len([p for p in providers if p.key == "openai"]) == 1
