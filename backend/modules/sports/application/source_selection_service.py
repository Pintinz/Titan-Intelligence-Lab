"""SourceSelectionService (POST-M24 Phase 3) — the smallest reusable "which provider should
serve this request" decision service TitanIQ didn't have before. Deliberately additive: it does
not replace `SportsProviderRouter._resolve_adapter`'s existing per-sport real/mock selection
(that remains exactly as Phase 2 left it, tested and unchanged) — it is a new, explicit,
provider-agnostic query layer that future orchestration (multi-provider requests, historical
import routing, admin tooling) can consult, per the master prompt's own framing: "make provider
selection explicit, deterministic, provider-agnostic, and reusable by future orchestration,"
not "rewrite provider clients."

Selection order, matching the master prompt's own sequencing exactly:

    CAPABILITY -> CONFIGURATION -> HEALTH -> QUOTA -> (COMPETITION) -> SOURCE PRIORITY -> SELECTED

No step here calls a provider adapter or makes an external request — every check is a pure
lookup or a read against already-persisted state (`CapabilityResolver`, which itself only wraps
`ProviderManagementService`/`CircuitBreaker`/`QuotaIntelligenceEngine`, all unchanged from
Phase 1/2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.sports.application.capability_resolver import CapabilityResolver
from modules.sports.domain.provider_capabilities import PROVIDER_CAPABILITIES, ProviderDomain, TemporalMode
from modules.sports.domain.value_objects import SportCode

# Explicit, static per-sport priority — not derived, not random, matching the master prompt's
# "Provider A / Provider B / Provider C" ordered examples and its "DO NOT randomly select
# providers" instruction. Mirrors the roles already declared in
# `modules.sports.domain.provider_capabilities.PROVIDER_CAPABILITIES` (PRIMARY before SECONDARY/
# FALLBACK) — a provider absent from a sport's tuple, or from the registry entirely, is simply
# never a candidate for that sport (correct for table tennis: an empty tuple, not an error).
_DEFAULT_SOURCE_PRIORITY: dict[SportCode, tuple[str, ...]] = {
    SportCode.FOOTBALL: ("api_football", "football_data_org", "thesportsdb"),
    SportCode.BASKETBALL: ("api_basketball",),
    SportCode.BASEBALL: ("api_baseball",),
    SportCode.TABLE_TENNIS: (),
}


@dataclass(frozen=True)
class DataRequest:
    """What the caller wants — sport/domain/temporal-mode are mandatory; `competition_id` and
    `low_priority` narrow the request further where relevant (competition-scoped and quota-
    priority checks are skipped, not failed, when omitted)."""

    sport: SportCode
    domain: ProviderDomain
    temporal_mode: TemporalMode
    competition_id: str | None = None
    low_priority: bool = False


@dataclass(frozen=True)
class SourceSelectionResult:
    provider_key: str | None
    eligible_providers: tuple[str, ...]  # capability-eligible, in priority order, before health/quota/config filtering
    excluded: tuple[tuple[str, str], ...]  # (provider_key, reason) for every eligible-but-rejected provider, in order


@dataclass
class SourceSelectionService:
    resolver: CapabilityResolver
    priority: dict[SportCode, tuple[str, ...]] = field(default_factory=lambda: dict(_DEFAULT_SOURCE_PRIORITY))

    def eligible_providers(self, request: DataRequest) -> tuple[str, ...]:
        """Pure capability filter — sport + domain + temporal mode, no I/O, no health/quota/
        configuration check yet. Ordered by this sport's static priority, with any capability-
        eligible provider not in the priority tuple appended after (so a newly-registered
        provider is never silently invisible to selection just because the priority tuple wasn't
        updated yet)."""
        candidates = [
            provider_key
            for provider_key, caps in PROVIDER_CAPABILITIES.items()
            if caps.sport is request.sport
            and caps.supports_domain(request.domain)
            and caps.supports_temporal_mode(request.temporal_mode)
        ]
        ordered_priority = self.priority.get(request.sport, ())
        ordered = [pk for pk in ordered_priority if pk in candidates]
        ordered += [pk for pk in candidates if pk not in ordered]
        return tuple(ordered)

    async def select_provider(self, request: DataRequest, now: datetime) -> SourceSelectionResult:
        """Applies CONFIGURATION -> HEALTH -> QUOTA -> (COMPETITION) in that order to the
        capability-eligible, priority-ordered candidates, returning the first provider that
        clears every gate — or `None` with a per-candidate exclusion reason if nothing did.
        Never falls back to an incapable provider (§13's explicit rule): a provider is only ever
        a candidate here because `eligible_providers` already proved it supports this exact
        sport/domain/temporal-mode combination."""
        candidates = self.eligible_providers(request)
        excluded: list[tuple[str, str]] = []

        for provider_key in candidates:
            if not await self.resolver.is_configured(provider_key):
                excluded.append((provider_key, "not_configured"))
                continue
            if not self.resolver.is_healthy(provider_key, now):
                excluded.append((provider_key, "circuit_open"))
                continue
            if not await self.resolver.has_quota(provider_key, now, low_priority=request.low_priority):
                excluded.append((provider_key, "quota_exhausted"))
                continue
            if request.competition_id is not None:
                if not await self.resolver.supports_competition(provider_key, request.sport, request.competition_id):
                    excluded.append((provider_key, "competition_not_supported"))
                    continue
            return SourceSelectionResult(provider_key=provider_key, eligible_providers=candidates, excluded=tuple(excluded))

        return SourceSelectionResult(provider_key=None, eligible_providers=candidates, excluded=tuple(excluded))
