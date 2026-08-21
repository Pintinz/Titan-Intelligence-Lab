"""CapabilityResolver (POST-M24 Phase 3) — answers "can this provider serve this request" by
combining the static `ProviderCapabilities` declarations with the *existing* runtime signals
Phase 2 already built: `ProviderManagementService` (configured/credentialed), `CircuitBreaker`
(healthy), `QuotaIntelligenceEngine` (quota available). Makes zero external API calls — every
check here is either a pure in-memory lookup against `PROVIDER_CAPABILITIES` or a read against
already-persisted admin/quota state, exactly mirroring the read side of
`SportsProviderRouter._resolve_adapter`/`_execute`'s existing gating (this module does not
duplicate that gating logic, it exposes the same checks as an explicit, queryable service for
use *before* a fetch is attempted, per the master prompt's "capability check -> cache -> quota ->
circuit breaker -> API" sequencing).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.admin.application.circuit_breaker import CircuitBreaker
from modules.admin.application.provider_management_service import ProviderManagementService
from modules.admin.application.quota_intelligence_engine import QuotaIntelligenceEngine
from modules.ingestion.ports.repositories import CompetitionFixtureSourceRepositoryPort
from modules.sports.domain.provider_capabilities import (
    PROVIDER_CAPABILITIES,
    ProviderCapabilities,
    ProviderDomain,
    SourceRole,
    TemporalMode,
)
from modules.sports.domain.value_objects import SportCode


@dataclass
class CapabilityResolver:
    admin_service: ProviderManagementService
    circuit_breaker: CircuitBreaker
    quota_engine: QuotaIntelligenceEngine
    fixture_source_preferences: CompetitionFixtureSourceRepositoryPort

    def has_real_provider(self, sport: SportCode) -> bool:
        """False for table tennis today — no real provider is registered for it anywhere. Never
        raises for an unsupported sport; a capability question about a sport with no provider is
        a valid, answerable question ("no"), not an error."""
        return any(caps.sport is sport for caps in PROVIDER_CAPABILITIES.values())

    def capabilities_of(self, provider_key: str) -> ProviderCapabilities | None:
        return PROVIDER_CAPABILITIES.get(provider_key)

    def supports_sport(self, provider_key: str, sport: SportCode) -> bool:
        caps = self.capabilities_of(provider_key)
        return caps is not None and caps.sport is sport

    def supports_domain(self, provider_key: str, domain: ProviderDomain) -> bool:
        caps = self.capabilities_of(provider_key)
        return caps is not None and caps.supports_domain(domain)

    def supports_temporal_mode(self, provider_key: str, mode: TemporalMode) -> bool:
        caps = self.capabilities_of(provider_key)
        return caps is not None and caps.supports_temporal_mode(mode)

    def supports_historical(self, provider_key: str) -> bool:
        return self.supports_temporal_mode(provider_key, TemporalMode.HISTORICAL)

    def supports_live(self, provider_key: str) -> bool:
        return self.supports_temporal_mode(provider_key, TemporalMode.LIVE)

    def supports_pre_match(self, provider_key: str) -> bool:
        return self.supports_temporal_mode(provider_key, TemporalMode.PRE_MATCH)

    def supports_post_match(self, provider_key: str) -> bool:
        return self.supports_temporal_mode(provider_key, TemporalMode.POST_MATCH)

    def supports_source_role(self, provider_key: str, role: SourceRole) -> bool:
        caps = self.capabilities_of(provider_key)
        return caps is not None and caps.supports_source_role(role)

    async def supports_competition(self, provider_key: str, sport: SportCode, competition_id: str) -> bool:
        """A generic (non-`fixture_schedule_scoped`) provider's fetch methods are parameterized
        by `competition_ref`/`season_label` with no evidence anywhere in the adapters of a
        per-competition allowlist — so "supports the sport" already answers "supports this
        competition" for it (never fabricates a finer-grained matrix the code doesn't have). A
        `fixture_schedule_scoped` provider (`football_data_org`, `thesportsdb`) is different: it's
        *only* eligible for a competition that has explicitly opted into it via a real, existing
        `CompetitionFixtureSourcePreference` row — reused here, not re-implemented."""
        caps = self.capabilities_of(provider_key)
        if caps is None or caps.sport is not sport:
            return False
        if not caps.fixture_schedule_scoped:
            return True
        preference = await self.fixture_source_preferences.get_by_competition(competition_id)
        return preference is not None and preference.preferred_provider_key == provider_key

    async def is_configured(self, provider_key: str) -> bool:
        """Active + has at least one usable credential — the same gate
        `SportsProviderRouter._resolve_adapter` already applies before ever calling a real
        adapter. A provider absent from the admin registry (never onboarded) is "not configured",
        not an error."""
        provider = await self.admin_service.providers.get_by_key(provider_key)
        if provider is None or not provider.is_usable():
            return False
        credentials = await self.admin_service.usable_credentials(provider.id)
        return bool(credentials)

    def is_healthy(self, provider_key: str, now: datetime) -> bool:
        """Mirrors `CircuitBreaker.allow_request`: OPEN (and not yet past its recovery timeout)
        means unhealthy; CLOSED/HALF_OPEN mean healthy enough to try. Reuses the exact same
        `CircuitBreaker` instance Phase 2 wired into `SportsProviderRouter` — no parallel health
        concept. Takes `now` explicitly (not read from the wall clock internally) for the same
        deterministic-testability reason every other Phase 1/2 service does."""
        return self.circuit_breaker.allow_request(provider_key, now)

    async def has_quota(self, provider_key: str, now: datetime, *, low_priority: bool = False) -> bool:
        """Negation of the same `QuotaIntelligenceEngine.should_throttle` check
        `SportsProviderRouter._execute` already applies — a provider absent from the admin
        registry has no quota state to exhaust, so it's treated as quota-available (configuration/
        health checks are what exclude it, not this one)."""
        provider = await self.admin_service.providers.get_by_key(provider_key)
        if provider is None:
            return True
        return not await self.quota_engine.should_throttle(provider.id, now, low_priority=low_priority)
