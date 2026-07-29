"""Value objects for the Provider Management System (docs/admin_center.md §2).

No framework imports — same domain-purity rule as every other module
(docs/architecture.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class ProviderCategory(str, Enum):
    SPORTS_DATA = "sports_data"
    AI = "ai"


class ProviderStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class CircuitState(str, Enum):
    CLOSED = "closed"  # requests flow normally
    OPEN = "open"  # requests short-circuit without calling the provider
    HALF_OPEN = "half_open"  # a single trial request is allowed through


class QuotaPeriod(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class IncidentSeverity(str, Enum):
    WARNING = "warning"  # DEGRADED
    CRITICAL = "critical"  # DOWN


@dataclass(frozen=True)
class ProviderId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class CredentialId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class IncidentId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class FlagId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
