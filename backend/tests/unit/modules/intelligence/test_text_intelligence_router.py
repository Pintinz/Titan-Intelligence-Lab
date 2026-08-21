import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from sqlalchemy.exc import OperationalError

from modules.admin.application.provider_management_service import ProviderManagementService
from modules.admin.domain.entities import ProviderCredential, ProviderDefinition
from modules.admin.domain.value_objects import CredentialId, ProviderCategory, ProviderId, ProviderStatus
from modules.intelligence.infrastructure.mock_gemini_adapter import MockGeminiAdapter
from modules.intelligence.infrastructure.text_intelligence_router import TextIntelligenceRouter

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


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


@dataclass
class _RecordingRealAdapter:
    provider_key: str = "gemini"

    async def explain(self, context: dict) -> str:
        return "real explanation"

    async def assess_prediction_context(self, payload: dict) -> tuple[str, str]:
        return '{"prediction_review": {"status": "SUPPORTED"}}', "gemini"


@dataclass
class _FailingRealAdapter:
    provider_key: str = "gemini"

    async def explain(self, context: dict) -> str:
        from modules.intelligence.infrastructure.gemini_adapter import GeminiRequestError

        raise GeminiRequestError("simulated 401 Unauthorized")


def _build_router(real_adapter=None):
    provider_repo = _InMemoryProviderRepo()
    credential_repo = _InMemoryCredentialRepo()
    admin_service = ProviderManagementService(providers=provider_repo, credentials=credential_repo, vault=_NoopVault())
    router = TextIntelligenceRouter(
        admin_service=admin_service,
        real_adapter=real_adapter or _RecordingRealAdapter(),
        mock_adapter=MockGeminiAdapter(),
    )
    return router, provider_repo, credential_repo


@dataclass
class _BrokenProviderRepo:
    """Simulates an execution context where the admin schema itself is unavailable (e.g. a
    narrower test database) — get_by_key raises at the DB layer rather than returning None."""

    async def get_by_key(self, key):
        raise OperationalError("SELECT ...", {}, Exception("no such table: admin.providers"))


@pytest.mark.asyncio
async def test_falls_back_to_mock_when_provider_lookup_itself_fails():
    credential_repo = _InMemoryCredentialRepo()
    admin_service = ProviderManagementService(providers=_BrokenProviderRepo(), credentials=credential_repo, vault=_NoopVault())
    router = TextIntelligenceRouter(
        admin_service=admin_service, real_adapter=_RecordingRealAdapter(), mock_adapter=MockGeminiAdapter()
    )

    result = await router.explain({})

    assert result == "This verdict is grounded in the match's available data — no single factor dominates it."


@pytest.mark.asyncio
async def test_uses_mock_when_no_provider_registered():
    router, _, _ = _build_router()

    result = await router.explain({})

    assert result == "This verdict is grounded in the match's available data — no single factor dominates it."


@pytest.mark.asyncio
async def test_uses_mock_when_provider_inactive():
    router, provider_repo, _ = _build_router()
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="gemini", name="Gemini API",
        category=ProviderCategory.AI, status=ProviderStatus.INACTIVE,
    )
    await provider_repo.upsert(provider)

    result = await router.explain({})

    assert result.startswith("This verdict")


@pytest.mark.asyncio
async def test_uses_mock_when_active_but_no_credentials():
    router, provider_repo, _ = _build_router()
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="gemini", name="Gemini API",
        category=ProviderCategory.AI, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)

    result = await router.explain({})

    assert result.startswith("This verdict")


@pytest.mark.asyncio
async def test_real_adapter_used_when_active_with_credential():
    router, provider_repo, credential_repo = _build_router()
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="gemini", name="Gemini API",
        category=ProviderCategory.AI, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    result = await router.explain({})

    assert result == "real explanation"


@pytest.mark.asyncio
async def test_falls_back_to_mock_when_real_adapter_raises():
    """A bad/expired key or a Gemini outage must degrade to the mock explanation, not blow up
    prediction generation — the verdict/confidence never came from Gemini in the first place."""
    router, provider_repo, credential_repo = _build_router(real_adapter=_FailingRealAdapter())
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="gemini", name="Gemini API",
        category=ProviderCategory.AI, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    result = await router.explain({})

    assert result == "This verdict is grounded in the match's available data — no single factor dominates it."


@pytest.mark.asyncio
async def test_assess_prediction_context_falls_back_to_mock_when_no_provider_registered():
    router, _, _ = _build_router()

    raw, source = await router.assess_prediction_context({"context": {}})

    assert "INSUFFICIENT_CONTEXT" in raw
    assert source == "mock"


@pytest.mark.asyncio
async def test_assess_prediction_context_uses_real_adapter_when_credentialed():
    router, provider_repo, credential_repo = _build_router()
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="gemini", name="Gemini API",
        category=ProviderCategory.AI, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    raw, source = await router.assess_prediction_context({"context": {}})

    assert raw == '{"prediction_review": {"status": "SUPPORTED"}}'
    assert source == "gemini"
