import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from modules.admin.application.circuit_breaker import CircuitBreaker, ProviderCircuitOpenError
from modules.admin.application.provider_management_service import ProviderManagementService
from modules.admin.application.quota_intelligence_engine import QuotaIntelligenceEngine
from modules.admin.domain.entities import ProviderCredential, ProviderDefinition
from modules.admin.domain.value_objects import (
    CredentialId,
    ProviderCategory,
    ProviderId,
    ProviderStatus,
)
from modules.sports.infrastructure.providers.mock_provider import MockSportsDataProvider
from modules.sports.infrastructure.providers.provider_router import (
    ProviderNotConfiguredError,
    ProviderThrottledError,
    SportsProviderRouter,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


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


class _NoopVault:
    def encrypt(self, plaintext):
        return plaintext

    def decrypt(self, ciphertext):
        return ciphertext


@dataclass
class _FailingAdapter:
    provider_key: str

    async def fetch_teams(self, competition_ref, season_label=None):
        raise RuntimeError("simulated provider outage")

    async def fetch_fixtures(self, competition_ref, season_label):
        raise RuntimeError("simulated provider outage")


def _build_router(real_adapters=None, fixture_schedule_adapters=None):
    provider_repo = _InMemoryProviderRepo()
    credential_repo = _InMemoryCredentialRepo()
    usage_repo = _InMemoryUsageRepo()
    admin_service = ProviderManagementService(providers=provider_repo, credentials=credential_repo, vault=_NoopVault())
    quota_engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)
    router = SportsProviderRouter(
        admin_service=admin_service,
        quota_engine=quota_engine,
        circuit_breaker=CircuitBreaker(failure_threshold=2),
        real_adapters=real_adapters or {},
        mock_adapters={
            "football": MockSportsDataProvider(provider_key="mock_football", sport_code="football"),
        },
        fixture_schedule_adapters=fixture_schedule_adapters or {},
    )
    return router, provider_repo, credential_repo


@pytest.mark.asyncio
async def test_uses_mock_when_no_real_adapter_registered():
    router, _, _ = _build_router()

    teams = await router.fetch_teams("football", "39", T0)

    assert len(teams) == 10


@pytest.mark.asyncio
async def test_uses_mock_when_provider_inactive():
    real_adapter = _FailingAdapter(provider_key="api_football")
    router, provider_repo, _ = _build_router(real_adapters={"football": real_adapter})
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()),
        key="api_football",
        name="API-Football",
        category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.INACTIVE,
    )
    await provider_repo.upsert(provider)

    # If it tried the real (failing) adapter this would raise — reaching a result proves fallback.
    teams = await router.fetch_teams("football", "39", T0)

    assert len(teams) == 10


@pytest.mark.asyncio
async def test_uses_mock_when_active_but_no_credentials():
    real_adapter = _FailingAdapter(provider_key="api_football")
    router, provider_repo, _ = _build_router(real_adapters={"football": real_adapter})
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()),
        key="api_football",
        name="API-Football",
        category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)

    teams = await router.fetch_teams("football", "39", T0)

    assert len(teams) == 10


@pytest.mark.asyncio
async def test_real_adapter_used_when_active_with_credential():
    calls = []

    @dataclass
    class _RecordingAdapter:
        provider_key: str

        async def fetch_teams(self, competition_ref, season_label=None):
            calls.append(competition_ref)
            return ["real-result"]

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _RecordingAdapter(provider_key="api_football")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()),
        key="api_football",
        name="API-Football",
        category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    result = await router.fetch_teams("football", "39", T0)

    assert result == ["real-result"]
    assert calls == ["39"]


@pytest.mark.asyncio
async def test_circuit_opens_after_repeated_real_failures_then_short_circuits():
    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _FailingAdapter(provider_key="api_football")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()),
        key="api_football",
        name="API-Football",
        category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    for _ in range(2):  # failure_threshold=2 in _build_router
        with pytest.raises(RuntimeError):
            await router.fetch_teams("football", "39", T0)

    with pytest.raises(ProviderCircuitOpenError):
        await router.fetch_teams("football", "39", T0)


@pytest.mark.asyncio
async def test_low_priority_request_throttled_near_quota_exhaustion():
    @dataclass
    class _AlwaysSucceedsAdapter:
        provider_key: str

        async def fetch_teams(self, competition_ref, season_label=None):
            return [f"team-{competition_ref}"]

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _AlwaysSucceedsAdapter(provider_key="api_football")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()),
        key="api_football",
        name="API-Football",
        category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE,
        daily_quota_limit=10,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    # Burn through 9/10 of quota with distinct competition_refs so caching doesn't short-circuit calls.
    for i in range(9):
        await router.fetch_teams("football", str(i), T0)

    with pytest.raises(ProviderThrottledError):
        await router.fetch_teams("football", "low-priority-call", T0, low_priority=True)


@pytest.mark.asyncio
async def test_fetch_odds_uses_mock_when_no_real_adapter_registered():
    router, _, _ = _build_router()
    fixture_ref = (await router.mock_adapters["football"].fetch_fixtures("39", "2026", T0))[0].external_ref

    odds = await router.fetch_odds("football", fixture_ref, T0)

    assert odds is not None
    assert odds.home_win > 1.0


@pytest.mark.asyncio
async def test_response_is_cached_within_ttl():
    calls = []

    @dataclass
    class _CountingAdapter:
        provider_key: str

        async def fetch_teams(self, competition_ref, season_label=None):
            calls.append(1)
            return ["result"]

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _CountingAdapter(provider_key="api_football")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()),
        key="api_football",
        name="API-Football",
        category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE,
        cache_ttl_seconds=3600,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    await router.fetch_teams("football", "39", T0)
    await router.fetch_teams("football", "39", T0)

    assert len(calls) == 1


# -- fetch_upcoming_fixtures (fixture_schedule_adapters) ---------------------------------------


@pytest.mark.asyncio
async def test_fetch_upcoming_fixtures_raises_when_provider_key_not_registered():
    router, _, _ = _build_router()

    with pytest.raises(ProviderNotConfiguredError):
        await router.fetch_upcoming_fixtures("football", "football_data_org", "PL", "2026", T0)


@pytest.mark.asyncio
async def test_fetch_upcoming_fixtures_raises_when_provider_not_active():
    router, provider_repo, _ = _build_router(
        fixture_schedule_adapters={"football_data_org": _FailingAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.INACTIVE,
    )
    await provider_repo.upsert(provider)

    with pytest.raises(ProviderNotConfiguredError):
        await router.fetch_upcoming_fixtures("football", "football_data_org", "PL", "2026", T0)


@pytest.mark.asyncio
async def test_fetch_upcoming_fixtures_raises_when_active_but_no_credentials():
    router, provider_repo, _ = _build_router(
        fixture_schedule_adapters={"football_data_org": _FailingAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)

    with pytest.raises(ProviderNotConfiguredError):
        await router.fetch_upcoming_fixtures("football", "football_data_org", "PL", "2026", T0)


@pytest.mark.asyncio
async def test_fetch_upcoming_fixtures_calls_the_resolved_adapter_when_active_with_credential():
    calls = []

    @dataclass
    class _RecordingFixtureAdapter:
        provider_key: str

        async def fetch_fixtures(self, competition_ref, season_label, now):
            calls.append((competition_ref, season_label))
            return ["upcoming-fixture"]

    router, provider_repo, credential_repo = _build_router(
        fixture_schedule_adapters={"football_data_org": _RecordingFixtureAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    result = await router.fetch_upcoming_fixtures("football", "football_data_org", "PL", "2026", T0)

    assert result == ["upcoming-fixture"]
    assert calls == [("PL", "2026")]


@pytest.mark.asyncio
async def test_fetch_upcoming_fixtures_response_is_cached_within_ttl():
    calls = []

    @dataclass
    class _CountingFixtureAdapter:
        provider_key: str

        async def fetch_fixtures(self, competition_ref, season_label, now):
            calls.append(1)
            return ["upcoming-fixture"]

    router, provider_repo, credential_repo = _build_router(
        fixture_schedule_adapters={"football_data_org": _CountingFixtureAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE, cache_ttl_seconds=3600,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    await router.fetch_upcoming_fixtures("football", "football_data_org", "PL", "2026", T0)
    await router.fetch_upcoming_fixtures("football", "football_data_org", "PL", "2026", T0)

    assert len(calls) == 1


# -- fetch_completed_fixtures (fixture_schedule_adapters) ---------------------------------------


@pytest.mark.asyncio
async def test_fetch_completed_fixtures_raises_when_provider_key_not_registered():
    router, _, _ = _build_router()

    with pytest.raises(ProviderNotConfiguredError):
        await router.fetch_completed_fixtures("football", "football_data_org", "PL", "2026", T0)


@pytest.mark.asyncio
async def test_fetch_completed_fixtures_raises_when_adapter_lacks_the_method():
    @dataclass
    class _UpcomingOnlyAdapter:
        provider_key: str

        async def fetch_fixtures(self, competition_ref, season_label, now):
            return ["upcoming-fixture"]

    router, provider_repo, credential_repo = _build_router(
        fixture_schedule_adapters={"football_data_org": _UpcomingOnlyAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    with pytest.raises(ProviderNotConfiguredError):
        await router.fetch_completed_fixtures("football", "football_data_org", "PL", "2026", T0)


@pytest.mark.asyncio
async def test_fetch_completed_fixtures_calls_the_resolved_adapter_when_active_with_credential():
    calls = []

    @dataclass
    class _RecordingCompletedFixtureAdapter:
        provider_key: str

        async def fetch_completed_fixtures(self, competition_ref, season_label, now):
            calls.append((competition_ref, season_label))
            return ["completed-fixture"]

    router, provider_repo, credential_repo = _build_router(
        fixture_schedule_adapters={"football_data_org": _RecordingCompletedFixtureAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    result = await router.fetch_completed_fixtures("football", "football_data_org", "PL", "2026", T0)

    assert result == ["completed-fixture"]
    assert calls == [("PL", "2026")]


@pytest.mark.asyncio
async def test_fetch_completed_fixtures_response_is_cached_within_ttl():
    calls = []

    @dataclass
    class _CountingCompletedFixtureAdapter:
        provider_key: str

        async def fetch_completed_fixtures(self, competition_ref, season_label, now):
            calls.append(1)
            return ["completed-fixture"]

    router, provider_repo, credential_repo = _build_router(
        fixture_schedule_adapters={"football_data_org": _CountingCompletedFixtureAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE, cache_ttl_seconds=3600,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    await router.fetch_completed_fixtures("football", "football_data_org", "PL", "2026", T0)
    await router.fetch_completed_fixtures("football", "football_data_org", "PL", "2026", T0)

    assert len(calls) == 1


# -- fetch_standings_alt (fixture_schedule_adapters) ---------------------------------------------


@pytest.mark.asyncio
async def test_fetch_standings_alt_raises_when_provider_key_not_registered():
    router, _, _ = _build_router()

    with pytest.raises(ProviderNotConfiguredError):
        await router.fetch_standings_alt("football", "football_data_org", "PL", "2026", T0)


@pytest.mark.asyncio
async def test_fetch_standings_alt_raises_when_adapter_lacks_the_method():
    @dataclass
    class _UpcomingOnlyAdapter:
        provider_key: str

        async def fetch_fixtures(self, competition_ref, season_label, now):
            return ["upcoming-fixture"]

    router, provider_repo, credential_repo = _build_router(
        fixture_schedule_adapters={"football_data_org": _UpcomingOnlyAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    with pytest.raises(ProviderNotConfiguredError):
        await router.fetch_standings_alt("football", "football_data_org", "PL", "2026", T0)


@pytest.mark.asyncio
async def test_fetch_standings_alt_calls_the_resolved_adapter_when_active_with_credential():
    calls = []

    @dataclass
    class _RecordingStandingsAdapter:
        provider_key: str

        async def fetch_standings(self, competition_ref, season_label):
            calls.append((competition_ref, season_label))
            return ["standing-row"]

    router, provider_repo, credential_repo = _build_router(
        fixture_schedule_adapters={"football_data_org": _RecordingStandingsAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    result = await router.fetch_standings_alt("football", "football_data_org", "PL", "2026", T0)

    assert result == ["standing-row"]
    assert calls == [("PL", "2026")]


@pytest.mark.asyncio
async def test_fetch_standings_alt_response_is_cached_within_ttl():
    calls = []

    @dataclass
    class _CountingStandingsAdapter:
        provider_key: str

        async def fetch_standings(self, competition_ref, season_label):
            calls.append(1)
            return ["standing-row"]

    router, provider_repo, credential_repo = _build_router(
        fixture_schedule_adapters={"football_data_org": _CountingStandingsAdapter(provider_key="football_data_org")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="football_data_org", name="football-data.org",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE, cache_ttl_seconds=3600,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )

    await router.fetch_standings_alt("football", "football_data_org", "PL", "2026", T0)
    await router.fetch_standings_alt("football", "football_data_org", "PL", "2026", T0)

    assert len(calls) == 1
