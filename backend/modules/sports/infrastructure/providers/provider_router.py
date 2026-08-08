"""ProviderRouter — the single entry point ingestion code calls to fetch sports data. Ties
together everything the provider configuration directive asked for: automatic mock/real
selection, quota-aware throttling, circuit breaking, and response caching, so callers never
see any of that machinery (docs/admin_center.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from modules.admin.application.circuit_breaker import CircuitBreaker, ProviderCircuitOpenError
from modules.admin.application.provider_management_service import ProviderManagementService
from modules.admin.application.quota_intelligence_engine import QuotaIntelligenceEngine
from modules.sports.domain.value_objects import ProviderRef
from modules.sports.ports.provider_gateway import (
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderLineupRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
    SportsDataProviderPort,
)


class ProviderThrottledError(RuntimeError):
    """Raised when quota protection defers a low-priority request. Callers should serve cached/
    last-known-good data instead of failing the user-facing request outright ("graceful
    degradation", docs/admin_center.md §2)."""


class ProviderNotConfiguredError(RuntimeError):
    """Raised by `fetch_upcoming_fixtures` when the requested `provider_key` isn't registered in
    `fixture_schedule_adapters`, or is registered but not active/credentialed. Unlike
    `_resolve_adapter`'s per-sport default (which falls back to a mock so ordinary syncing never
    breaks), this call is only ever made for a competition that explicitly opted into a specific
    alternate provider (`CompetitionFixtureSourcePreference`) — silently falling back to mock
    data here would hide a real setup mistake instead of surfacing it."""


@dataclass
class SportsProviderRouter:
    admin_service: ProviderManagementService
    quota_engine: QuotaIntelligenceEngine
    circuit_breaker: CircuitBreaker
    real_adapters: dict[str, SportsDataProviderPort]  # keyed by SportCode.value
    mock_adapters: dict[str, SportsDataProviderPort]  # keyed by SportCode.value
    # Orthogonal to `real_adapters`: a second, provider-key-keyed slot for adapters that only
    # ever serve one narrow concern (today: upcoming fixture schedules) for a subset of
    # competitions, opted into explicitly per-competition rather than replacing a sport's
    # default adapter. Empty by default so existing callers/tests that don't pass this argument
    # are unaffected. See `fetch_upcoming_fixtures`.
    fixture_schedule_adapters: dict[str, SportsDataProviderPort] = field(default_factory=dict)
    _cache: dict[tuple, tuple[datetime, object]] = field(default_factory=dict)

    async def _resolve_adapter(self, sport_code: str, now: datetime) -> tuple[SportsDataProviderPort, str]:
        real = self.real_adapters.get(sport_code)
        if real is None:
            return self.mock_adapters[sport_code], "mock"
        provider = await self.admin_service.providers.get_by_key(real.provider_key)
        if provider is None or not provider.is_usable():
            return self.mock_adapters[sport_code], "mock"
        credentials = await self.admin_service.usable_credentials(provider.id)
        if not credentials:
            return self.mock_adapters[sport_code], "mock"  # active provider, no key yet — dev mode
        return real, "real"

    def _cache_get(self, key: tuple, now: datetime):
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        return value if now < expires_at else None

    def _cache_set(self, key: tuple, value: object, now: datetime, ttl_seconds: int) -> None:
        self._cache[key] = (now + timedelta(seconds=ttl_seconds), value)

    async def _execute(
        self,
        sport_code: str,
        cache_key: tuple,
        now: datetime,
        low_priority: bool,
        call: callable,
    ):
        cached = self._cache_get(cache_key, now)
        if cached is not None:
            return cached

        adapter, mode = await self._resolve_adapter(sport_code, now)
        provider = await self.admin_service.providers.get_by_key(adapter.provider_key)
        cache_ttl = provider.cache_ttl_seconds if provider else 3600

        if mode == "real":
            if not self.circuit_breaker.allow_request(adapter.provider_key, now):
                raise ProviderCircuitOpenError(f"circuit open for '{adapter.provider_key}'")
            if provider and await self.quota_engine.should_throttle(provider.id, now, low_priority=low_priority):
                raise ProviderThrottledError(f"quota protection throttled '{adapter.provider_key}'")
            try:
                result = await call(adapter)
            except Exception:
                self.circuit_breaker.record_failure(adapter.provider_key, now)
                if provider:
                    await self.quota_engine.record_request(provider.id, now, success=False)
                raise
            else:
                self.circuit_breaker.record_success(adapter.provider_key)
                if provider:
                    await self.quota_engine.record_request(provider.id, now, success=True)
        else:
            result = await call(adapter)  # mocks are free — no circuit/quota bookkeeping needed

        self._cache_set(cache_key, result, now, cache_ttl)
        return result

    async def fetch_teams(
        self, sport_code: str, competition_ref: str, now: datetime, *,
        low_priority: bool = False, season_label: str | None = None,
    ) -> list[ProviderTeamRecord]:
        return await self._execute(
            sport_code,
            ("teams", sport_code, competition_ref, season_label),
            now,
            low_priority,
            lambda adapter: adapter.fetch_teams(competition_ref, season_label),
        )

    async def fetch_fixtures(
        self,
        sport_code: str,
        competition_ref: str,
        season_label: str,
        now: datetime,
        *,
        low_priority: bool = False,
    ) -> list[ProviderFixtureRecord]:
        return await self._execute(
            sport_code,
            ("fixtures", sport_code, competition_ref, season_label),
            now,
            low_priority,
            lambda adapter: adapter.fetch_fixtures(competition_ref, season_label, now),
        )

    async def fetch_countries(
        self, sport_code: str, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderCountryRecord]:
        return await self._execute(
            sport_code, ("countries", sport_code), now, low_priority,
            lambda adapter: adapter.fetch_countries(),
        )

    async def fetch_players(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *, low_priority: bool = False, season_label: str | None = None
    ) -> list[ProviderPlayerRecord]:
        return await self._execute(
            sport_code, ("players", sport_code, team_ref.provider, team_ref.external_id, season_label), now, low_priority,
            lambda adapter: adapter.fetch_players(team_ref, season_label),
        )

    async def fetch_standings(
        self, sport_code: str, competition_ref: str, season_label: str, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderStandingRecord]:
        return await self._execute(
            sport_code, ("standings", sport_code, competition_ref, season_label), now, low_priority,
            lambda adapter: adapter.fetch_standings(competition_ref, season_label),
        )

    async def fetch_team_statistics(
        self, sport_code: str, fixture_ref: ProviderRef, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderTeamStatisticsRecord]:
        return await self._execute(
            sport_code, ("team_statistics", sport_code, fixture_ref.provider, fixture_ref.external_id),
            now, low_priority, lambda adapter: adapter.fetch_team_statistics(fixture_ref),
        )

    async def fetch_lineups(
        self, sport_code: str, fixture_ref: ProviderRef, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderLineupRecord]:
        return await self._execute(
            sport_code, ("lineups", sport_code, fixture_ref.provider, fixture_ref.external_id),
            now, low_priority, lambda adapter: adapter.fetch_lineups(fixture_ref),
        )

    async def fetch_odds(
        self, sport_code: str, fixture_ref: ProviderRef, now: datetime, *, low_priority: bool = True
    ) -> ProviderOddsRecord | None:
        return await self._execute(
            sport_code, ("odds", sport_code, fixture_ref.provider, fixture_ref.external_id),
            now, low_priority, lambda adapter: adapter.fetch_odds(fixture_ref),
        )

    async def _resolve_fixture_schedule_adapter(self, provider_key: str) -> tuple[SportsDataProviderPort, object]:
        adapter = self.fixture_schedule_adapters.get(provider_key)
        if adapter is None:
            raise ProviderNotConfiguredError(f"no fixture-schedule adapter registered for '{provider_key}'")
        provider = await self.admin_service.providers.get_by_key(adapter.provider_key)
        if provider is None or not provider.is_usable():
            raise ProviderNotConfiguredError(f"provider '{provider_key}' is not registered/active")
        credentials = await self.admin_service.usable_credentials(provider.id)
        if not credentials:
            raise ProviderNotConfiguredError(f"provider '{provider_key}' has no usable credential configured")
        return adapter, provider

    async def fetch_upcoming_fixtures(
        self, sport_code: str, provider_key: str, competition_ref: str, season_label: str, now: datetime, *,
        low_priority: bool = False,
    ) -> list[ProviderFixtureRecord]:
        """The `fixture_schedule_adapters` counterpart to `fetch_fixtures` — resolves a specific,
        explicitly-opted-into provider (via `provider_key`, looked up by the caller from a
        `CompetitionFixtureSourcePreference`) instead of the sport's default adapter, with no
        mock fallback (see `ProviderNotConfiguredError`). Relies on the resolved adapter's own
        `fetch_fixtures` to have already scoped its request to not-yet-played matches
        (`FootballDataOrgAdapter.fetch_fixtures` does this via its `status=SCHEDULED,TIMED`
        request param) — this method does not re-filter by status, so a future fixture-schedule
        adapter that doesn't pre-filter would need to do so itself, matching this method's
        contract of "upcoming fixtures only"."""
        cache_key = ("upcoming_fixtures", provider_key, competition_ref, season_label)
        cached = self._cache_get(cache_key, now)
        if cached is not None:
            return cached

        adapter, provider = await self._resolve_fixture_schedule_adapter(provider_key)
        cache_ttl = provider.cache_ttl_seconds if provider else 3600

        if not self.circuit_breaker.allow_request(adapter.provider_key, now):
            raise ProviderCircuitOpenError(f"circuit open for '{adapter.provider_key}'")
        if provider and await self.quota_engine.should_throttle(provider.id, now, low_priority=low_priority):
            raise ProviderThrottledError(f"quota protection throttled '{adapter.provider_key}'")
        try:
            result = await adapter.fetch_fixtures(competition_ref, season_label, now)
        except Exception:
            self.circuit_breaker.record_failure(adapter.provider_key, now)
            if provider:
                await self.quota_engine.record_request(provider.id, now, success=False)
            raise
        else:
            self.circuit_breaker.record_success(adapter.provider_key)
            if provider:
                await self.quota_engine.record_request(provider.id, now, success=True)

        self._cache_set(cache_key, result, now, cache_ttl)
        return result

    async def fetch_completed_fixtures(
        self, sport_code: str, provider_key: str, competition_ref: str, season_label: str, now: datetime, *,
        low_priority: bool = False,
    ) -> list[ProviderFixtureRecord]:
        """`fetch_upcoming_fixtures`'s counterpart for final scores — same resolution, circuit-
        breaker, quota, and caching behavior, but calls the adapter's `fetch_completed_fixtures`
        instead. Not every `fixture_schedule_adapters` entry necessarily implements this (it's
        not part of `SportsDataProviderPort`), so a missing method raises `ProviderNotConfiguredError`
        rather than an opaque `AttributeError`, matching this router's existing "no silent
        fallback" discipline for provider-specific capabilities."""
        cache_key = ("completed_fixtures", provider_key, competition_ref, season_label)
        cached = self._cache_get(cache_key, now)
        if cached is not None:
            return cached

        adapter, provider = await self._resolve_fixture_schedule_adapter(provider_key)
        fetch_completed = getattr(adapter, "fetch_completed_fixtures", None)
        if fetch_completed is None:
            raise ProviderNotConfiguredError(f"provider '{provider_key}' does not support completed-fixture sync")
        cache_ttl = provider.cache_ttl_seconds if provider else 3600

        if not self.circuit_breaker.allow_request(adapter.provider_key, now):
            raise ProviderCircuitOpenError(f"circuit open for '{adapter.provider_key}'")
        if provider and await self.quota_engine.should_throttle(provider.id, now, low_priority=low_priority):
            raise ProviderThrottledError(f"quota protection throttled '{adapter.provider_key}'")
        try:
            result = await fetch_completed(competition_ref, season_label, now)
        except Exception:
            self.circuit_breaker.record_failure(adapter.provider_key, now)
            if provider:
                await self.quota_engine.record_request(provider.id, now, success=False)
            raise
        else:
            self.circuit_breaker.record_success(adapter.provider_key)
            if provider:
                await self.quota_engine.record_request(provider.id, now, success=True)

        self._cache_set(cache_key, result, now, cache_ttl)
        return result
