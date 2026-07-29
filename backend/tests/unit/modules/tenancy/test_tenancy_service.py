from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.identity.domain.value_objects import AuditAction, UserId
from modules.tenancy.application.tenancy_service import (
    InvitationInvalidError,
    NotAuthorizedError,
    TenancyService,
    slugify,
)
from modules.tenancy.domain.entities import Membership
from modules.tenancy.domain.value_objects import InvitationStatus, MembershipId, OrganizationRole


def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def service(organization_repo, team_repo, membership_repo, invitation_repo, audit_log_repo, token_hasher):
    return TenancyService(
        organizations=organization_repo,
        teams=team_repo,
        memberships=membership_repo,
        invitations=invitation_repo,
        audit_log=audit_log_repo,
        token_hasher=token_hasher,
    )


def test_slugify():
    assert slugify("Acme Sports Analytics!!") == "acme-sports-analytics"
    assert slugify("   ") == "org"


async def test_create_organization_makes_owner_a_member(service, membership_repo, audit_log_repo):
    owner = UserId(uuid4())

    org = await service.create_organization("Acme Corp", owner, now())

    membership = await membership_repo.get_for_user(org.id, owner)
    assert membership.role is OrganizationRole.OWNER
    assert any(e.action is AuditAction.ORGANIZATION_CREATED for e in audit_log_repo.entries)


async def test_create_team_requires_admin_role(service):
    owner = UserId(uuid4())
    member = UserId(uuid4())
    org = await service.create_organization("Acme", owner, now())
    await service.memberships.upsert(
        Membership(id=MembershipId(uuid4()), organization_id=org.id, user_id=member, role=OrganizationRole.MEMBER)
    )

    with pytest.raises(NotAuthorizedError):
        await service.create_team(org.id, "Engineering", member, now())

    team = await service.create_team(org.id, "Engineering", owner, now())
    assert team.name == "Engineering"


async def test_invite_and_accept_flow(service):
    owner = UserId(uuid4())
    invitee = UserId(uuid4())
    org = await service.create_organization("Acme", owner, now())

    invitation, raw_token = await service.invite_member(org.id, "friend@example.com", OrganizationRole.MEMBER, owner, now())
    assert invitation.email == "friend@example.com"

    membership = await service.accept_invitation(raw_token, invitee, now())
    assert membership.organization_id == org.id
    assert membership.role is OrganizationRole.MEMBER


async def test_accept_invitation_rejects_unknown_token(service):
    with pytest.raises(InvitationInvalidError):
        await service.accept_invitation("not-a-real-token", UserId(uuid4()), now())


async def test_accept_invitation_rejects_expired(service, invitation_repo):
    owner = UserId(uuid4())
    org = await service.create_organization("Acme", owner, now())
    invitation, raw_token = await service.invite_member(org.id, "friend@example.com", OrganizationRole.MEMBER, owner, now())

    long_after_expiry = invitation.expires_at + timedelta(days=1)

    with pytest.raises(InvitationInvalidError):
        await service.accept_invitation(raw_token, UserId(uuid4()), long_after_expiry)


async def test_change_member_role_and_remove(service):
    owner = UserId(uuid4())
    member = UserId(uuid4())
    org = await service.create_organization("Acme", owner, now())
    invitation, raw_token = await service.invite_member(org.id, "friend@example.com", OrganizationRole.MEMBER, owner, now())
    await service.accept_invitation(raw_token, member, now())

    updated = await service.change_member_role(org.id, member, OrganizationRole.ADMIN, owner, now())
    assert updated.role is OrganizationRole.ADMIN

    await service.remove_member(org.id, member, owner, now())
    assert await service.memberships.get_for_user(org.id, member) is None


async def test_non_admin_cannot_change_roles(service):
    owner = UserId(uuid4())
    member = UserId(uuid4())
    org = await service.create_organization("Acme", owner, now())
    invitation, raw_token = await service.invite_member(org.id, "friend@example.com", OrganizationRole.MEMBER, owner, now())
    await service.accept_invitation(raw_token, member, now())

    with pytest.raises(NotAuthorizedError):
        await service.change_member_role(org.id, member, OrganizationRole.ADMIN, member, now())


async def test_revoke_invitation(service, invitation_repo):
    owner = UserId(uuid4())
    org = await service.create_organization("Acme", owner, now())
    invitation, _ = await service.invite_member(org.id, "friend@example.com", OrganizationRole.MEMBER, owner, now())

    await service.revoke_invitation(invitation.id, owner, now())

    stored = await invitation_repo.get(invitation.id)
    assert stored.status is InvitationStatus.REVOKED
