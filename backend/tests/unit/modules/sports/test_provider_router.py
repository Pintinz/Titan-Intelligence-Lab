import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import fakeredis
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
from modules.ingestion.infrastructure.cache.redis_lock import RedisDistributedLock
from modules.ingestion.infrastructure.cache.redis_sync_cache import RedisSyncCache
from modules.sports.domain.value_objects import ProviderRef
from modules.sports.infrastructure.providers.api_sports_adapter import ProviderErrorKind, ProviderRequestError
from modules.sports.infrastructure.providers.mock_provider import MockSportsDataProvider
from modules.sports.infrastructure.providers.provider_router import (
    ProviderNotConfiguredError,
    ProviderThrottledError,
    SportsProviderRouter,
    _cache_ttl_for,
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


def _build_router(real_adapters=None, fixture_schedule_adapters=None, mock_adapters=None, cache=None, lock=None):
    provider_repo = _InMemoryProviderRepo()
    credential_repo = _InMemoryCredentialRepo()
    usage_repo = _InMemoryUsageRepo()
    admin_service = ProviderManagementService(providers=provider_repo, credentials=credential_repo, vault=_NoopVault())
    quota_engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)
    kwargs = {}
    if cache is not None:
        kwargs["cache"] = cache
    if lock is not None:
        kwargs["lock"] = lock
    router = SportsProviderRouter(
        admin_service=admin_service,
        quota_engine=quota_engine,
        circuit_breaker=CircuitBreaker(failure_threshold=2),
        real_adapters=real_adapters or {},
        mock_adapters=mock_adapters or {
            "football": MockSportsDataProvider(provider_key="mock_football", sport_code="football"),
        },
        fixture_schedule_adapters=fixture_schedule_adapters or {},
        **kwargs,
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
async def test_fetch_team_statistics_refuses_a_cross_provider_fixture_ref():
    """Real production incident (2026-08-30): a fixture reconciled only via football-data.org
    had its own numeric external id sent straight to api-sports.io's /fixtures/statistics as if
    it were an api-sports.io fixture id — TitanIQ has no cross-provider fixture-id mapping, so an
    honest-looking HTTP 200/empty response was really luck, not correctness (a numeric collision
    could have silently attributed a real, unrelated match's stats to the wrong fixture). The
    router must refuse this outright rather than ever call the mismatched adapter."""
    calls = []

    @dataclass
    class _RecordingStatsAdapter:
        provider_key: str

        async def fetch_team_statistics(self, fixture_ref):
            calls.append(fixture_ref)
            return ["should never be reached"]

    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _RecordingStatsAdapter(provider_key="api_football")}
    )
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="api_football", name="API-Football",
        category=ProviderCategory.SPORTS_DATA, status=ProviderStatus.ACTIVE,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )
    mismatched_ref = ProviderRef(provider="football_data_org", external_id="560571")

    with pytest.raises(ProviderNotConfiguredError):
        await router.fetch_team_statistics("football", mismatched_ref, T0)

    assert calls == []  # the mismatched adapter must never actually be called

    # And this refusal must never count as a circuit-breaker failure against api-football, since
    # it's a caller-side routing mismatch, not evidence api-football itself is unhealthy — even
    # well past _build_router's failure_threshold=2, the circuit must stay closed.
    for _ in range(5):
        with pytest.raises(ProviderNotConfiguredError):
            await router.fetch_team_statistics("football", mismatched_ref, T0, low_priority=True)
    assert router.circuit_breaker.allow_request("api_football", T0) is True


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


# -- POST-M24 Phase 2: Redis-shared cache --------------------------------------------------------


async def _active_provider_with_credential(provider_repo, credential_repo, key="api_football", **overrides):
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key=key, name=key, category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE, **overrides,
    )
    await provider_repo.upsert(provider)
    await credential_repo.upsert(
        ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider.id, label="primary", encrypted_value="k")
    )
    return provider


@pytest.mark.asyncio
async def test_cache_write_from_one_router_is_visible_to_another_sharing_redis():
    """The whole point of Phase 2: two `SportsProviderRouter` instances (standing in for two
    separate Celery worker processes) sharing the same Redis backend must see each other's cache
    writes — the pre-Phase-2 in-process dict could never do this."""
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    cache = RedisSyncCache(client=redis_client)
    lock = RedisDistributedLock(client=redis_client)
    calls = []

    @dataclass
    class _CountingAdapter:
        provider_key: str

        async def fetch_teams(self, competition_ref, season_label=None):
            calls.append(1)
            return ["result"]

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router_a, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _CountingAdapter(provider_key="api_football")}, cache=cache, lock=lock,
    )
    await _active_provider_with_credential(provider_repo, credential_repo)
    # A second router instance, its own in-memory admin/quota state, but the SAME Redis cache/lock
    # — the part that matters for this test.
    router_b, provider_repo_b, credential_repo_b = _build_router(
        real_adapters={"football": _CountingAdapter(provider_key="api_football")}, cache=cache, lock=lock,
    )
    await _active_provider_with_credential(provider_repo_b, credential_repo_b)

    await router_a.fetch_teams("football", "39", T0)
    result_from_b = await router_b.fetch_teams("football", "39", T0)

    assert result_from_b == ["result"]
    assert len(calls) == 1  # router_b's call was served entirely from the shared Redis cache


@pytest.mark.asyncio
async def test_redis_cache_expires_and_triggers_a_fresh_provider_call():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    cache = RedisSyncCache(client=redis_client)
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
        real_adapters={"football": _CountingAdapter(provider_key="api_football")}, cache=cache,
    )
    await _active_provider_with_credential(provider_repo, credential_repo)

    await router.fetch_teams("football", "39", T0)
    # `_cache_ttl_for("teams", ...)` is 24h in production; use fakeredis's own real-time TTL
    # directly to prove expiry works without waiting 24h in the test. `RedisSyncCache` prefixes
    # every key with "synccache:" on top of the router's own "providercache:" prefix.
    await redis_client.expire("synccache:providercache:teams|football|39|\x00", 0)

    await router.fetch_teams("football", "39", T0)

    assert len(calls) == 2


# -- POST-M24 Phase 2: concurrent-request deduplication -------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_identical_requests_result_in_one_provider_call():
    calls = []

    @dataclass
    class _SlowAdapter:
        provider_key: str

        async def fetch_teams(self, competition_ref, season_label=None):
            calls.append(1)
            await asyncio.sleep(0.05)  # wide enough that a naive implementation double-fetches
            return ["result"]

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _SlowAdapter(provider_key="api_football")},
    )
    await _active_provider_with_credential(provider_repo, credential_repo)

    results = await asyncio.gather(
        router.fetch_teams("football", "39", T0),
        router.fetch_teams("football", "39", T0),
        router.fetch_teams("football", "39", T0),
    )

    assert len(calls) == 1
    assert all(r == ["result"] for r in results)


@pytest.mark.asyncio
async def test_a_lock_loser_reuses_the_winners_cached_result_not_a_stale_value():
    calls = []

    @dataclass
    class _SlowAdapter:
        provider_key: str

        async def fetch_teams(self, competition_ref, season_label=None):
            calls.append(1)
            await asyncio.sleep(0.05)
            return [f"result-{len(calls)}"]

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _SlowAdapter(provider_key="api_football")},
    )
    await _active_provider_with_credential(provider_repo, credential_repo)

    first, second = await asyncio.gather(
        router.fetch_teams("football", "39", T0), router.fetch_teams("football", "39", T0),
    )

    assert first == second == ["result-1"]  # both callers got the single winner's result


# -- POST-M24 Phase 2: endpoint-category TTL -----------------------------------------------------


def test_ttl_category_overrides_a_coarser_provider_default():
    assert _cache_ttl_for("odds", 3600) == 600
    assert _cache_ttl_for("injuries", 3600) == 1800
    assert _cache_ttl_for("completed_fixtures", 3600) == 7 * 24 * 3600


def test_ttl_falls_back_to_provider_default_for_an_unlisted_kind():
    assert _cache_ttl_for("some_future_endpoint", 999) == 999


# -- POST-M24 Phase 2: bounded retry on classified transient/rate-limited errors ------------------


@pytest.mark.asyncio
async def test_rate_limited_error_is_retried_and_can_still_succeed():
    attempts = []

    @dataclass
    class _FlakyAdapter:
        provider_key: str

        async def fetch_teams(self, competition_ref, season_label=None):
            attempts.append(1)
            if len(attempts) < 2:
                raise ProviderRequestError("rate limited", kind=ProviderErrorKind.RATE_LIMITED, retry_after_seconds=0.01)
            return ["result"]

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _FlakyAdapter(provider_key="api_football")},
    )
    await _active_provider_with_credential(provider_repo, credential_repo)

    result = await router.fetch_teams("football", "39", T0)

    assert result == ["result"]
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_permanent_error_is_never_retried():
    attempts = []

    @dataclass
    class _AlwaysBadRequestAdapter:
        provider_key: str

        async def fetch_teams(self, competition_ref, season_label=None):
            attempts.append(1)
            raise ProviderRequestError("bad request", kind=ProviderErrorKind.PERMANENT)

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _AlwaysBadRequestAdapter(provider_key="api_football")},
    )
    await _active_provider_with_credential(provider_repo, credential_repo)

    with pytest.raises(ProviderRequestError):
        await router.fetch_teams("football", "39", T0)

    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_retryable_error_gives_up_after_the_bound():
    attempts = []

    @dataclass
    class _AlwaysRateLimitedAdapter:
        provider_key: str

        async def fetch_teams(self, competition_ref, season_label=None):
            attempts.append(1)
            raise ProviderRequestError("rate limited", kind=ProviderErrorKind.RATE_LIMITED, retry_after_seconds=0.01)

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router, provider_repo, credential_repo = _build_router(
        real_adapters={"football": _AlwaysRateLimitedAdapter(provider_key="api_football")},
    )
    await _active_provider_with_credential(provider_repo, credential_repo)

    with pytest.raises(ProviderRequestError):
        await router.fetch_teams("football", "39", T0)

    assert len(attempts) == 3  # 1 initial + 2 bounded retries, never indefinite


# -- POST-M24 Phase 2: multi-sport cache isolation -------------------------------------------------


@pytest.mark.asyncio
async def test_same_competition_ref_across_sports_does_not_collide_in_cache():
    football_calls = []
    basketball_calls = []

    @dataclass
    class _TaggedAdapter:
        provider_key: str
        calls: list

        async def fetch_teams(self, competition_ref, season_label=None):
            self.calls.append(1)
            return [f"{self.provider_key}-result"]

        async def fetch_fixtures(self, competition_ref, season_label):
            return []

    router, provider_repo, credential_repo = _build_router(
        real_adapters={
            "football": _TaggedAdapter(provider_key="api_football", calls=football_calls),
            "basketball": _TaggedAdapter(provider_key="api_basketball", calls=basketball_calls),
        },
        mock_adapters={
            "football": MockSportsDataProvider(provider_key="mock_football", sport_code="football"),
            "basketball": MockSportsDataProvider(provider_key="mock_basketball", sport_code="basketball"),
        },
    )
    await _active_provider_with_credential(provider_repo, credential_repo, key="api_football")
    await _active_provider_with_credential(provider_repo, credential_repo, key="api_basketball")

    football_result = await router.fetch_teams("football", "39", T0)
    basketball_result = await router.fetch_teams("basketball", "39", T0)

    assert football_result == ["api_football-result"]
    assert basketball_result == ["api_basketball-result"]
    assert len(football_calls) == 1
    assert len(basketball_calls) == 1  # same competition_ref "39", different sport -> no cache collision


@pytest.mark.asyncio
async def test_table_tennis_mock_only_routing_works_through_the_same_cache_path():
    """Table tennis has no real provider (Phase 1 audit finding) — confirms the cache
    abstraction has no football-specific assumption baked in by exercising the mock-only path
    for a sport that will never have a `real_adapters` entry."""
    router, _, _ = _build_router(
        mock_adapters={"table_tennis": MockSportsDataProvider(provider_key="mock_table_tennis", sport_code="table_tennis")},
    )

    first = await router.fetch_teams("table_tennis", "world-cup", T0)
    second = await router.fetch_teams("table_tennis", "world-cup", T0)

    assert first == second
    assert len(first) > 0
