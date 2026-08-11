"""TenancyService — organizations, teams, memberships, and invitations (Milestone 6).

Every mutating action emits an entry into the shared immutable security audit trail
(``modules.identity`` owns that port/vocabulary — see docs/decisions.md on why audit is
centralized rather than duplicated per bounded context).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from modules.identity.domain.entities import AuditLogEntry
from modules.identity.domain.value_objects import AuditAction, AuditEventId, UserId
from modules.identity.ports.repositories import AuditLogRepositoryPort
from modules.identity.ports.security import TokenHasherPort
from modules.tenancy.domain.entities import Invitation, Membership, Organization, Team
from modules.tenancy.domain.value_objects import (
    InvitationId,
    InvitationStatus,
    MembershipId,
    OrganizationId,
    OrganizationRole,
    TeamId,
)
from modules.tenancy.ports.repositories import (
    InvitationRepositoryPort,
    MembershipRepositoryPort,
    OrganizationRepositoryPort,
    TeamRepositoryPort,
)


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — same fix as
    ``modules.identity.application.identity_service._ensure_aware``."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "org"


class NotAuthorizedError(Exception):
    pass


class InvitationInvalidError(Exception):
    pass


@dataclass
class TenancyService:
    organizations: OrganizationRepositoryPort
    teams: TeamRepositoryPort
    memberships: MembershipRepositoryPort
    invitations: InvitationRepositoryPort
    audit_log: AuditLogRepositoryPort
    token_hasher: TokenHasherPort
    invitation_ttl: timedelta = timedelta(days=7)

    # -- organizations --------------------------------------------------------------------------

    async def create_organization(self, name: str, owner_user_id: UserId, now: datetime) -> Organization:
        organization = Organization(
            id=OrganizationId(uuid4()),
            name=name,
            slug=slugify(name),
            owner_user_id=owner_user_id,
            created_at=now,
            updated_at=now,
        )
        await self.organizations.upsert(organization)
        await self.memberships.upsert(
            Membership(
                id=MembershipId(uuid4()),
                organization_id=organization.id,
                user_id=owner_user_id,
                role=OrganizationRole.OWNER,
                joined_at=now,
            )
        )
        await self._audit(
            AuditAction.ORGANIZATION_CREATED, now, owner_user_id, "organization", str(organization.id)
        )
        return organization

    # -- teams ------------------------------------------------------------------------------------

    async def create_team(self, organization_id: OrganizationId, name: str, actor: UserId, now: datetime) -> Team:
        await self._require_role(organization_id, actor, {OrganizationRole.OWNER, OrganizationRole.ADMIN})
        team = Team(id=TeamId(uuid4()), organization_id=organization_id, name=name, created_at=now)
        await self.teams.upsert(team)
        return team

    # -- memberships --------------------------------------------------------------------------------

    async def _require_role(
        self, organization_id: OrganizationId, user_id: UserId, allowed: set[OrganizationRole]
    ) -> Membership:
        membership = await self.memberships.get_for_user(organization_id, user_id)
        if membership is None or membership.role not in allowed:
            raise NotAuthorizedError(f"{user_id} lacks required role in organization {organization_id}")
        return membership

    async def change_member_role(
        self,
        organization_id: OrganizationId,
        target_user_id: UserId,
        new_role: OrganizationRole,
        actor: UserId,
        now: datetime,
    ) -> Membership:
        await self._require_role(organization_id, actor, {OrganizationRole.OWNER, OrganizationRole.ADMIN})
        membership = await self.memberships.get_for_user(organization_id, target_user_id)
        if membership is None:
            raise ValueError("No such membership")
        old_role = membership.role
        membership.role = new_role
        await self.memberships.upsert(membership)
        await self._audit(
            AuditAction.MEMBERSHIP_CHANGED,
            now,
            actor,
            "membership",
            str(membership.id),
            metadata={"old_role": old_role.value, "new_role": new_role.value},
        )
        return membership

    async def remove_member(
        self, organization_id: OrganizationId, target_user_id: UserId, actor: UserId, now: datetime
    ) -> None:
        await self._require_role(organization_id, actor, {OrganizationRole.OWNER, OrganizationRole.ADMIN})
        membership = await self.memberships.get_for_user(organization_id, target_user_id)
        if membership is None:
            return
        await self.memberships.delete(membership.id)
        await self._audit(
            AuditAction.MEMBERSHIP_CHANGED,
            now,
            actor,
            "membership",
            str(membership.id),
            metadata={"removed": True},
        )

    async def list_members(self, organization_id: OrganizationId, actor: UserId) -> list[Membership]:
        await self._require_role(
            organization_id, actor, {OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.MEMBER}
        )
        return await self.memberships.list_by_organization(organization_id)

    # -- invitations --------------------------------------------------------------------------------

    async def invite_member(
        self,
        organization_id: OrganizationId,
        email: str,
        role: OrganizationRole,
        actor: UserId,
        now: datetime,
    ) -> tuple[Invitation, str]:
        await self._require_role(organization_id, actor, {OrganizationRole.OWNER, OrganizationRole.ADMIN})
        raw_token = self.token_hasher.generate()
        invitation = Invitation(
            id=InvitationId(uuid4()),
            organization_id=organization_id,
            email=email.strip().lower(),
            role=role,
            invited_by=actor,
            token_hash=self.token_hasher.hash(raw_token),
            status=InvitationStatus.PENDING,
            created_at=now,
            expires_at=now + self.invitation_ttl,
        )
        await self.invitations.upsert(invitation)
        return invitation, raw_token

    async def accept_invitation(self, raw_token: str, accepting_user_id: UserId, now: datetime) -> Membership:
        invitation = await self.invitations.get_by_token_hash(self.token_hasher.hash(raw_token))
        if invitation is not None and invitation.expires_at is not None:
            invitation.expires_at = _ensure_aware(invitation.expires_at, now)
        if invitation is None or not invitation.is_pending(now):
            raise InvitationInvalidError("Invitation is invalid or has expired")

        invitation.status = InvitationStatus.ACCEPTED
        invitation.responded_at = now
        await self.invitations.upsert(invitation)

        membership = Membership(
            id=MembershipId(uuid4()),
            organization_id=invitation.organization_id,
            user_id=accepting_user_id,
            role=invitation.role,
            joined_at=now,
        )
        await self.memberships.upsert(membership)
        await self._audit(
            AuditAction.MEMBERSHIP_CHANGED,
            now,
            accepting_user_id,
            "membership",
            str(membership.id),
            metadata={"via_invitation": str(invitation.id)},
        )
        return membership

    async def revoke_invitation(self, invitation_id: InvitationId, actor: UserId, now: datetime) -> None:
        invitation = await self.invitations.get(invitation_id)
        if invitation is None:
            return
        await self._require_role(invitation.organization_id, actor, {OrganizationRole.OWNER, OrganizationRole.ADMIN})
        invitation.status = InvitationStatus.REVOKED
        invitation.responded_at = now
        await self.invitations.upsert(invitation)

    # -- audit --------------------------------------------------------------------------------------

    async def _audit(
        self,
        action: AuditAction,
        now: datetime,
        actor: UserId,
        target_type: str,
        target_id: str,
        metadata: dict | None = None,
    ) -> None:
        await self.audit_log.append(
            AuditLogEntry(
                id=AuditEventId(uuid4()),
                action=action,
                occurred_at=now,
                actor_user_id=actor,
                target_type=target_type,
                target_id=target_id,
                metadata=metadata or {},
            )
        )
