"""Entities for the Multi-Tenancy bounded context (Milestone 6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.identity.domain.value_objects import UserId
from modules.tenancy.domain.value_objects import (
    InvitationId,
    InvitationStatus,
    MembershipId,
    OrganizationId,
    OrganizationRole,
    TeamId,
)


@dataclass
class Organization:
    id: OrganizationId
    name: str
    slug: str
    owner_user_id: UserId
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Team:
    id: TeamId
    organization_id: OrganizationId
    name: str
    created_at: datetime | None = None


@dataclass
class Membership:
    """``team_id`` is None for an org-wide membership not scoped to a specific team — a
    membership always belongs to exactly one organization, optionally also to one team within
    it (docs/database_schema.md §RLS)."""

    id: MembershipId
    organization_id: OrganizationId
    user_id: UserId
    role: OrganizationRole
    team_id: TeamId | None = None
    joined_at: datetime | None = None


@dataclass
class Invitation:
    id: InvitationId
    organization_id: OrganizationId
    email: str
    role: OrganizationRole
    invited_by: UserId
    token_hash: str
    status: InvitationStatus = InvitationStatus.PENDING
    created_at: datetime | None = None
    expires_at: datetime | None = None
    responded_at: datetime | None = None

    def is_pending(self, as_of: datetime) -> bool:
        return self.status is InvitationStatus.PENDING and (self.expires_at is None or as_of < self.expires_at)
