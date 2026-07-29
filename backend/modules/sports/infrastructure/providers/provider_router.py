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


@dataclass
class SportsProviderRouter:
    admin_service: ProviderManagementService
    quota_engine: QuotaIntelligenceEngine
    circuit_breaker: CircuitBreaker
    real_adapters: dict[str, SportsDataProviderPort]  # keyed by SportCode.value
    mock_adapters: dict[str, SportsDataProviderPort]  # keyed by SportCode.value
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
        self, sport_code: str, competition_ref: str, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderTeamRecord]:
        return await self._execute(
            sport_code,
            ("teams", sport_code, competition_ref),
            now,
            low_priority,
            lambda adapter: adapter.fetch_teams(competition_ref),
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
            lambda adapter: adapter.fetch_fixtures(competition_ref, season_label),
        )

    async def fetch_countries(
        self, sport_code: str, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderCountryRecord]:
        return await self._execute(
            sport_code, ("countries", sport_code), now, low_priority,
            lambda adapter: adapter.fetch_countries(),
        )

    async def fetch_players(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderPlayerRecord]:
        return await self._execute(
            sport_code, ("players", sport_code, team_ref.provider, team_ref.external_id), now, low_priority,
            lambda adapter: adapter.fetch_players(team_ref),
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
