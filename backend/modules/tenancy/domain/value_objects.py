"""Value objects for the Multi-Tenancy bounded context (Milestone 6).

No framework imports (docs/architecture.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class OrganizationRole(str, Enum):
    """Org-scoped role — distinct from ``modules.identity.domain.value_objects.Role``, which
    is the platform-wide RBAC ladder. A user can be ``identity.Role.FREE`` platform-wide and
    still be an ``OWNER`` of their own organization."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True)
class OrganizationId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class TeamId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class MembershipId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class InvitationId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
