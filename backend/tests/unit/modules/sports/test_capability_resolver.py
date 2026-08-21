"""POST-M24 Phase 3: `CapabilityResolver` tests — every check must be answerable from in-memory
fakes alone (zero external API calls), matching the master prompt's "capability resolution must
not make external calls" requirement literally: none of these fakes has network access at all."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from modules.admin.application.circuit_breaker import CircuitBreaker
from modules.admin.application.provider_management_service import ProviderManagementService
from modules.admin.application.quota_intelligence_engine import QuotaIntelligenceEngine
from modules.admin.domain.entities import ProviderCredential, ProviderDefinition
from modules.admin.domain.value_objects import CredentialId, ProviderCategory, ProviderId, ProviderStatus
from modules.ingestion.domain.entities import CompetitionFixtureSourcePreference
from modules.sports.application.capability_resolver import CapabilityResolver
from modules.sports.domain.provider_capabilities import ProviderDomain, TemporalMode
from modules.sports.domain.value_objects import SportCode

T0 = datetime(2026, 8, 15, tzinfo=timezone.utc)


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


@dataclass
class _InMemoryUsageRepo:
    store: dict = field(default_factory=dict)

    async def get(self, provider_id, period, window_key, credential_id=None):
        return self.store.get((provider_id, period, window_key, credential_id))

    async def upsert(self, record):
        self.store[(record.provider_id, record.period, record.window_key, record.credential_id)] = record
        return record


@dataclass
class _InMemoryFixtureSourceRepo:
    store: dict = field(default_factory=dict)

    async def get_by_competition(self, competition_id):
        return self.store.get(competition_id)

    async def upsert(self, preference):
        self.store[preference.competition_id] = preference
        return preference

    async def delete(self, competition_id):
        self.store.pop(competition_id, None)

    async def list_all(self):
        return list(self.store.values())


class _NoopVault:
    def encrypt(self, plaintext):
        return plaintext

    def decrypt(self, ciphertext):
        return ciphertext


def _build_resolver(*, failure_threshold=5):
    provider_repo = _InMemoryProviderRepo()
    credential_repo = _InMemoryCredentialRepo()
    usage_repo = _InMemoryUsageRepo()
    fixture_source_repo = _InMemoryFixtureSourceRepo()
    resolver = CapabilityResolver(
        admin_service=ProviderManagementService(providers=provider_repo, credentials=credential_repo, vault=_NoopVault()),
        circuit_breaker=CircuitBreaker(failure_threshold=failure_threshold),
        quota_engine=QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo),
        fixture_source_preferences=fixture_source_repo,
    )
    return resolver, provider_repo, credential_repo, fixture_source_repo


async def _register_active_provider(provider_repo, credential_repo, key, **overrides):
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key=key, name=key, category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE, **overrides,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )
    return provider


# -- Pure capability lookups (no I/O) --------------------------------------------------------------


def test_supports_sport_and_domain():
    resolver, *_ = _build_resolver()
    assert resolver.supports_sport("api_football", SportCode.FOOTBALL)
    assert not resolver.supports_sport("api_football", SportCode.BASKETBALL)
    assert resolver.supports_domain("api_football", ProviderDomain.ODDS)
    assert not resolver.supports_domain("api_basketball", ProviderDomain.ODDS)


def test_unknown_provider_key_returns_false_not_an_error():
    resolver, *_ = _build_resolver()
    assert resolver.supports_sport("nonexistent_provider", SportCode.FOOTBALL) is False
    assert resolver.supports_domain("nonexistent_provider", ProviderDomain.FIXTURES) is False


def test_has_real_provider_false_for_table_tennis():
    resolver, *_ = _build_resolver()
    assert resolver.has_real_provider(SportCode.TABLE_TENNIS) is False
    assert resolver.has_real_provider(SportCode.FOOTBALL) is True
    assert resolver.has_real_provider(SportCode.BASKETBALL) is True
    assert resolver.has_real_provider(SportCode.BASEBALL) is True


def test_temporal_mode_convenience_methods():
    resolver, *_ = _build_resolver()
    assert resolver.supports_live("api_football")
    assert resolver.supports_pre_match("api_football")
    assert not resolver.supports_pre_match("api_basketball")
    assert resolver.supports_post_match("football_data_org")


# -- Configuration ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_configured_false_when_not_registered():
    resolver, *_ = _build_resolver()
    assert await resolver.is_configured("api_football") is False


@pytest.mark.asyncio
async def test_is_configured_false_when_inactive():
    resolver, provider_repo, credential_repo, _ = _build_resolver()
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="api_football", name="API-Football",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.INACTIVE,
    )
    await provider_repo.upsert(provider)
    assert await resolver.is_configured("api_football") is False


@pytest.mark.asyncio
async def test_is_configured_true_when_active_with_credential():
    resolver, provider_repo, credential_repo, _ = _build_resolver()
    await _register_active_provider(provider_repo, credential_repo, "api_football")
    assert await resolver.is_configured("api_football") is True


# -- Health -----------------------------------------------------------------------------------------


def test_is_healthy_true_when_circuit_closed():
    resolver, *_ = _build_resolver()
    assert resolver.is_healthy("api_football", T0) is True


def test_is_healthy_false_when_circuit_open():
    resolver, *_ = _build_resolver(failure_threshold=1)
    resolver.circuit_breaker.record_failure("api_football", T0)
    assert resolver.is_healthy("api_football", T0) is False


# -- Quota ------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_quota_true_for_unregistered_provider():
    resolver, *_ = _build_resolver()
    assert await resolver.has_quota("api_football", T0) is True


@pytest.mark.asyncio
async def test_has_quota_false_when_exhausted_for_low_priority():
    resolver, provider_repo, credential_repo, _ = _build_resolver()
    provider = await _register_active_provider(provider_repo, credential_repo, "api_football", daily_quota_limit=10)
    for _ in range(9):
        await resolver.quota_engine.record_request(provider.id, T0, success=True)
    assert await resolver.has_quota("api_football", T0, low_priority=True) is False
    assert await resolver.has_quota("api_football", T0, low_priority=False) is True


# -- Competition scoping ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generic_provider_supports_any_competition_within_its_sport():
    resolver, *_ = _build_resolver()
    assert await resolver.supports_competition("api_football", SportCode.FOOTBALL, "any-competition-id") is True


@pytest.mark.asyncio
async def test_generic_provider_never_supports_a_competition_outside_its_sport():
    resolver, *_ = _build_resolver()
    assert await resolver.supports_competition("api_basketball", SportCode.FOOTBALL, "some-id") is False


@pytest.mark.asyncio
async def test_fixture_schedule_scoped_provider_requires_an_explicit_preference():
    resolver, *_, fixture_source_repo = _build_resolver()
    assert await resolver.supports_competition("football_data_org", SportCode.FOOTBALL, "epl") is False

    await fixture_source_repo.upsert(
        CompetitionFixtureSourcePreference(competition_id="epl", preferred_provider_key="football_data_org", provider_competition_ref="PL")
    )
    assert await resolver.supports_competition("football_data_org", SportCode.FOOTBALL, "epl") is True
    assert await resolver.supports_competition("thesportsdb", SportCode.FOOTBALL, "epl") is False  # opted into a different provider
