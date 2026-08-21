"""POST-M24 Phase 3: `SourceSelectionService` tests — capability -> configuration -> health ->
quota -> (competition) -> priority, and fallback that only ever selects a capable provider."""

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
from modules.sports.application.capability_resolver import CapabilityResolver
from modules.sports.application.source_selection_service import DataRequest, SourceSelectionService
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


def _build_service():
    provider_repo = _InMemoryProviderRepo()
    credential_repo = _InMemoryCredentialRepo()
    usage_repo = _InMemoryUsageRepo()
    fixture_source_repo = _InMemoryFixtureSourceRepo()
    resolver = CapabilityResolver(
        admin_service=ProviderManagementService(providers=provider_repo, credentials=credential_repo, vault=_NoopVault()),
        circuit_breaker=CircuitBreaker(failure_threshold=2),
        quota_engine=QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo),
        fixture_source_preferences=fixture_source_repo,
    )
    service = SourceSelectionService(resolver=resolver)
    return service, provider_repo, credential_repo


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


# -- eligible_providers (pure capability filter) ---------------------------------------------------


def test_eligible_providers_football_fixtures_upcoming_returns_all_three_in_priority_order():
    service, *_ = _build_service()
    request = DataRequest(sport=SportCode.FOOTBALL, domain=ProviderDomain.FIXTURES, temporal_mode=TemporalMode.UPCOMING)

    eligible = service.eligible_providers(request)

    assert eligible == ("api_football", "football_data_org", "thesportsdb")


def test_eligible_providers_football_odds_only_api_football():
    service, *_ = _build_service()
    request = DataRequest(sport=SportCode.FOOTBALL, domain=ProviderDomain.ODDS, temporal_mode=TemporalMode.PRE_MATCH)

    assert service.eligible_providers(request) == ("api_football",)


def test_eligible_providers_basketball_live_returns_api_basketball():
    service, *_ = _build_service()
    request = DataRequest(sport=SportCode.BASKETBALL, domain=ProviderDomain.FIXTURES, temporal_mode=TemporalMode.LIVE)

    assert service.eligible_providers(request) == ("api_basketball",)


def test_eligible_providers_basketball_pre_match_returns_nothing():
    service, *_ = _build_service()
    request = DataRequest(sport=SportCode.BASKETBALL, domain=ProviderDomain.LINEUPS, temporal_mode=TemporalMode.PRE_MATCH)

    assert service.eligible_providers(request) == ()


def test_eligible_providers_table_tennis_always_empty():
    service, *_ = _build_service()
    request = DataRequest(sport=SportCode.TABLE_TENNIS, domain=ProviderDomain.FIXTURES, temporal_mode=TemporalMode.UPCOMING)

    assert service.eligible_providers(request) == ()


def test_table_tennis_resolution_does_not_affect_other_sports():
    service, provider_repo, credential_repo = _build_service()
    # exercise table tennis first — must not raise or corrupt state for the next sport
    tt_request = DataRequest(sport=SportCode.TABLE_TENNIS, domain=ProviderDomain.FIXTURES, temporal_mode=TemporalMode.UPCOMING)
    assert service.eligible_providers(tt_request) == ()

    football_request = DataRequest(sport=SportCode.FOOTBALL, domain=ProviderDomain.FIXTURES, temporal_mode=TemporalMode.UPCOMING)
    assert service.eligible_providers(football_request) == ("api_football", "football_data_org", "thesportsdb")


# -- select_provider: capability + configuration + health + quota ----------------------------------


@pytest.mark.asyncio
async def test_selects_the_capable_configured_provider():
    service, provider_repo, credential_repo = _build_service()
    await _register_active_provider(provider_repo, credential_repo, "api_football")
    request = DataRequest(sport=SportCode.FOOTBALL, domain=ProviderDomain.ODDS, temporal_mode=TemporalMode.PRE_MATCH)

    result = await service.select_provider(request, T0)

    assert result.provider_key == "api_football"
    assert result.excluded == ()


@pytest.mark.asyncio
async def test_incapable_provider_is_excluded_before_selection_even_runs():
    service, provider_repo, credential_repo = _build_service()
    await _register_active_provider(provider_repo, credential_repo, "api_basketball")
    # basketball has no ODDS/PRE_MATCH capability at all — never even a candidate
    request = DataRequest(sport=SportCode.BASKETBALL, domain=ProviderDomain.ODDS, temporal_mode=TemporalMode.PRE_MATCH)

    result = await service.select_provider(request, T0)

    assert result.provider_key is None
    assert result.eligible_providers == ()


@pytest.mark.asyncio
async def test_unconfigured_provider_is_excluded():
    service, *_ = _build_service()  # nothing registered
    request = DataRequest(sport=SportCode.FOOTBALL, domain=ProviderDomain.TEAMS, temporal_mode=TemporalMode.UPCOMING)

    result = await service.select_provider(request, T0)

    assert result.provider_key is None
    assert ("api_football", "not_configured") in result.excluded


@pytest.mark.asyncio
async def test_unhealthy_provider_is_excluded():
    service, provider_repo, credential_repo = _build_service()
    await _register_active_provider(provider_repo, credential_repo, "api_basketball")
    service.resolver.circuit_breaker.record_failure("api_basketball", T0)
    service.resolver.circuit_breaker.record_failure("api_basketball", T0)  # failure_threshold=2
    request = DataRequest(sport=SportCode.BASKETBALL, domain=ProviderDomain.TEAMS, temporal_mode=TemporalMode.UPCOMING)

    result = await service.select_provider(request, T0)

    assert result.provider_key is None
    assert ("api_basketball", "circuit_open") in result.excluded


@pytest.mark.asyncio
async def test_quota_exhausted_provider_is_excluded():
    service, provider_repo, credential_repo = _build_service()
    provider = await _register_active_provider(provider_repo, credential_repo, "api_baseball", daily_quota_limit=1)
    await service.resolver.quota_engine.record_request(provider.id, T0, success=True)
    request = DataRequest(sport=SportCode.BASEBALL, domain=ProviderDomain.TEAMS, temporal_mode=TemporalMode.UPCOMING)

    result = await service.select_provider(request, T0)

    assert result.provider_key is None
    assert ("api_baseball", "quota_exhausted") in result.excluded


# -- Fallback: only a capable secondary is ever selected --------------------------------------------


@pytest.mark.asyncio
async def test_primary_unconfigured_falls_back_to_capable_secondary():
    service, provider_repo, credential_repo = _build_service()
    # api_football never registered — football_data_org is
    await _register_active_provider(provider_repo, credential_repo, "football_data_org")
    request = DataRequest(sport=SportCode.FOOTBALL, domain=ProviderDomain.FIXTURES, temporal_mode=TemporalMode.UPCOMING)

    result = await service.select_provider(request, T0)

    assert result.provider_key == "football_data_org"
    assert ("api_football", "not_configured") in result.excluded


@pytest.mark.asyncio
async def test_secondary_lacking_the_capability_is_never_selected_as_fallback():
    """football_data_org/thesportsdb don't support ODDS at all — even if api_football is
    unconfigured, they must never be selected for an odds request (they're simply not eligible
    candidates in the first place)."""
    service, provider_repo, credential_repo = _build_service()
    await _register_active_provider(provider_repo, credential_repo, "football_data_org")
    await _register_active_provider(provider_repo, credential_repo, "thesportsdb")
    request = DataRequest(sport=SportCode.FOOTBALL, domain=ProviderDomain.ODDS, temporal_mode=TemporalMode.PRE_MATCH)

    result = await service.select_provider(request, T0)

    assert result.provider_key is None
    assert result.eligible_providers == ("api_football",)  # only api_football was ever a candidate


@pytest.mark.asyncio
async def test_fixture_schedule_scoped_provider_only_selected_for_its_opted_in_competition():
    from modules.ingestion.domain.entities import CompetitionFixtureSourcePreference

    service, provider_repo, credential_repo = _build_service()
    await _register_active_provider(provider_repo, credential_repo, "football_data_org")
    await service.resolver.fixture_source_preferences.upsert(
        CompetitionFixtureSourcePreference(competition_id="epl", preferred_provider_key="football_data_org", provider_competition_ref="PL")
    )
    request_opted_in = DataRequest(
        sport=SportCode.FOOTBALL, domain=ProviderDomain.RESULTS, temporal_mode=TemporalMode.HISTORICAL, competition_id="epl",
    )
    request_not_opted_in = DataRequest(
        sport=SportCode.FOOTBALL, domain=ProviderDomain.RESULTS, temporal_mode=TemporalMode.HISTORICAL, competition_id="some-other-competition",
    )

    opted_in_result = await service.select_provider(request_opted_in, T0)
    not_opted_in_result = await service.select_provider(request_not_opted_in, T0)

    assert opted_in_result.provider_key == "football_data_org"
    assert not_opted_in_result.provider_key is None
    assert ("football_data_org", "competition_not_supported") in not_opted_in_result.excluded
