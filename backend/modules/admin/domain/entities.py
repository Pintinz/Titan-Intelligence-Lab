"""Provider Management System entities (docs/admin_center.md §2).

``ProviderCredential.encrypted_value`` is opaque ciphertext produced by a
``CredentialVaultPort`` implementation — the domain layer never sees, logs, or compares
plaintext key material (docs/security.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.admin.domain.value_objects import (
    CredentialId,
    FlagId,
    HealthStatus,
    IncidentId,
    IncidentSeverity,
    ProviderCategory,
    ProviderId,
    ProviderStatus,
    QuotaPeriod,
)


@dataclass
class ProviderDefinition:
    id: ProviderId
    key: str  # stable slug, e.g. "api_football" — never changes after registration
    name: str
    category: ProviderCategory
    status: ProviderStatus = ProviderStatus.INACTIVE
    priority: int = 100  # lower = tried first among providers implementing the same port
    daily_quota_limit: int | None = None
    monthly_quota_limit: int | None = None
    cache_ttl_seconds: int = 3600
    poll_interval_seconds: int = 300

    def is_usable(self) -> bool:
        return self.status is ProviderStatus.ACTIVE


@dataclass
class ProviderCredential:
    id: CredentialId
    provider_id: ProviderId
    label: str
    encrypted_value: str
    is_active: bool = True
    created_at: datetime | None = None
    rotated_at: datetime | None = None
    expires_at: datetime | None = None

    def is_expired(self, as_of: datetime) -> bool:
        return self.expires_at is not None and as_of >= self.expires_at


@dataclass
class ProviderUsageRecord:
    provider_id: ProviderId
    period: QuotaPeriod
    window_key: str  # "2026-07-25" for DAILY, "2026-07" for MONTHLY
    credential_id: CredentialId | None = None  # None = tracked at provider level (no credential yet)
    request_count: int = 0
    error_count: int = 0


@dataclass
class ProviderHealthCheck:
    """One raw health-check ping — the append-only history everything else is computed from."""

    provider_id: ProviderId
    checked_at: datetime
    success: bool
    latency_ms: float | None = None
    message: str | None = None


@dataclass
class ProviderHealthState:
    """Materialized rolling state, one row per provider — updated on every recorded check so
    ``consecutive_failures``/``status`` are O(1) reads instead of rescanning check history
    (docs/decisions.md ADR-011). This is the record HealthIntelligenceEngine mutates to detect
    degradation/recovery; ``ProviderHealthCheck`` history remains untouched, append-only."""

    provider_id: ProviderId
    status: HealthStatus = HealthStatus.HEALTHY
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_check_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    open_incident_id: IncidentId | None = None


@dataclass
class ProviderIncident:
    """A detected degradation/outage episode. Opened when status first leaves HEALTHY, closed
    when it returns — severity only ever escalates (WARNING -> CRITICAL) within one incident,
    never downgrades, so the record reflects the worst the episode got
    (docs/decisions.md ADR-011)."""

    id: IncidentId
    provider_id: ProviderId
    severity: IncidentSeverity
    opened_at: datetime
    trigger: str
    resolved_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None


@dataclass
class FeatureFlag:
    """Gates incomplete sports/markets/subsystems from general availability
    (docs/admin_center.md §1, docs/roadmap.md Milestone 4). ``rollout_percentage`` only matters
    when ``enabled`` is True — a disabled flag is off for everyone regardless of percentage."""

    id: FlagId
    key: str  # stable slug, e.g. "table_tennis_predictions"
    name: str
    description: str
    enabled: bool = False
    rollout_percentage: int = 100
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.rollout_percentage <= 100:
            raise ValueError("rollout_percentage must be between 0 and 100")
