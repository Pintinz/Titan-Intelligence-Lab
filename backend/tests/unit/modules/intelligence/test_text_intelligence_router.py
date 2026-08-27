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

    async def assess_prediction_context(self, payload: dict) -> tuple[str, str]:
        from modules.intelligence.infrastructure.gemini_adapter import GeminiRequestError

        raise GeminiRequestError("simulated 429 rate limited")


@dataclass
class _RecordingClaudeAdapter:
    provider_key: str = "claude"

    async def explain(self, context: dict) -> str:
        return "claude explanation"

    async def assess_prediction_context(self, payload: dict) -> tuple[str, str]:
        return '{"prediction_review": {"status": "SUPPORTED"}}', "claude"


def _build_router(real_adapter=None, fallback_adapters=()):
    provider_repo = _InMemoryProviderRepo()
    credential_repo = _InMemoryCredentialRepo()
    admin_service = ProviderManagementService(providers=provider_repo, credentials=credential_repo, vault=_NoopVault())
    router = TextIntelligenceRouter(
        admin_service=admin_service,
        real_adapter=real_adapter or _RecordingRealAdapter(),
        mock_adapter=MockGeminiAdapter(),
        fallback_adapters=fallback_adapters,
    )
    return router, provider_repo, credential_repo


async def _register_provider(provider_repo, credential_repo, key: str, name: str):
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key=key, name=name,
        category=ProviderCategory.AI, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )
    return provider


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


class TestFallbackChain:
    """News Intelligence audit (2026-08-27) — `fallback_adapters`: a chain of further real
    providers tried in order after `real_adapter`, before finally falling to `mock_adapter`."""

    async def test_falls_through_to_a_credentialed_fallback_when_primary_has_no_credential(self):
        """Gemini registered but with no usable credential yet — Claude, which IS credentialed,
        must be used instead of jumping straight to mock."""
        router, provider_repo, credential_repo = _build_router(fallback_adapters=(_RecordingClaudeAdapter(),))
        await provider_repo.upsert(
            ProviderDefinition(id=ProviderId(uuid.uuid4()), key="gemini", name="Gemini API", category=ProviderCategory.AI, status=ProviderStatus.ACTIVE)
        )
        await _register_provider(provider_repo, credential_repo, "claude", "Claude (Anthropic)")

        result = await router.explain({})

        assert result == "claude explanation"

    async def test_falls_through_to_fallback_when_primary_raises(self):
        """The scenario that motivated this feature: Gemini quota-exhausted (raises on every
        call) but Claude is credentialed and working — the chain must reach it rather than
        degrading straight to the mock explanation."""
        router, provider_repo, credential_repo = _build_router(
            real_adapter=_FailingRealAdapter(), fallback_adapters=(_RecordingClaudeAdapter(),),
        )
        await _register_provider(provider_repo, credential_repo, "gemini", "Gemini API")
        await _register_provider(provider_repo, credential_repo, "claude", "Claude (Anthropic)")

        result = await router.explain({})

        assert result == "claude explanation"

    async def test_falls_back_to_mock_when_every_adapter_in_the_chain_fails(self):
        failing_claude = _FailingRealAdapter(provider_key="claude")
        router, provider_repo, credential_repo = _build_router(
            real_adapter=_FailingRealAdapter(), fallback_adapters=(failing_claude,),
        )
        await _register_provider(provider_repo, credential_repo, "gemini", "Gemini API")
        await _register_provider(provider_repo, credential_repo, "claude", "Claude (Anthropic)")

        result = await router.explain({})

        assert result == "This verdict is grounded in the match's available data — no single factor dominates it."

    async def test_falls_back_to_mock_when_no_adapter_in_the_chain_is_credentialed(self):
        router, _provider_repo, _credential_repo = _build_router(fallback_adapters=(_RecordingClaudeAdapter(),))

        result = await router.explain({})

        assert result == "This verdict is grounded in the match's available data — no single factor dominates it."

    async def test_primary_is_preferred_over_fallback_when_both_are_usable(self):
        """Gemini stays primary — Claude is only ever tried when Gemini genuinely fails or isn't
        credentialed, never used just because it's also available."""
        router, provider_repo, credential_repo = _build_router(fallback_adapters=(_RecordingClaudeAdapter(),))
        await _register_provider(provider_repo, credential_repo, "gemini", "Gemini API")
        await _register_provider(provider_repo, credential_repo, "claude", "Claude (Anthropic)")

        result = await router.explain({})

        assert result == "real explanation"

    async def test_assess_prediction_context_reports_the_real_source_that_actually_answered(self):
        router, provider_repo, credential_repo = _build_router(
            real_adapter=_FailingRealAdapter(), fallback_adapters=(_RecordingClaudeAdapter(),),
        )
        await _register_provider(provider_repo, credential_repo, "gemini", "Gemini API")
        await _register_provider(provider_repo, credential_repo, "claude", "Claude (Anthropic)")

        raw, source = await router.assess_prediction_context({"context": {}})

        assert raw == '{"prediction_review": {"status": "SUPPORTED"}}'
        assert source == "claude"

    async def test_no_fallback_adapters_behaves_exactly_like_the_single_adapter_router(self):
        """Default `fallback_adapters=()` — every existing caller/test that only ever passed
        `real_adapter` is completely unaffected by this feature."""
        router, provider_repo, credential_repo = _build_router(real_adapter=_FailingRealAdapter())
        await _register_provider(provider_repo, credential_repo, "gemini", "Gemini API")

        result = await router.explain({})

        assert result == "This verdict is grounded in the match's available data — no single factor dominates it."
