from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from modules.identity.domain.value_objects import UserId
from modules.tenancy.domain.entities import Invitation, Membership, Organization, Team
from modules.tenancy.domain.value_objects import (
    InvitationId,
    InvitationStatus,
    MembershipId,
    OrganizationId,
    OrganizationRole,
    TeamId,
)
from modules.tenancy.infrastructure.persistence.repositories import (
    SqlAlchemyInvitationRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyTeamRepository,
)


def now():
    return datetime.now(timezone.utc)


async def test_organization_repository_round_trip(sqlite_session):
    repo = SqlAlchemyOrganizationRepository(session=sqlite_session)
    owner = UserId(uuid4())
    org = Organization(id=OrganizationId(uuid4()), name="Acme", slug="acme", owner_user_id=owner)

    await repo.upsert(org)
    await sqlite_session.commit()

    assert (await repo.get_by_slug("acme")).id == org.id
    assert (await repo.list_owned_by(owner))[0].id == org.id


async def test_team_repository_round_trip(sqlite_session):
    org_repo = SqlAlchemyOrganizationRepository(session=sqlite_session)
    org = await org_repo.upsert(Organization(id=OrganizationId(uuid4()), name="Acme", slug="acme", owner_user_id=UserId(uuid4())))
    await sqlite_session.commit()

    team_repo = SqlAlchemyTeamRepository(session=sqlite_session)
    team = await team_repo.upsert(Team(id=TeamId(uuid4()), organization_id=org.id, name="Engineering"))
    await sqlite_session.commit()

    teams = await team_repo.list_by_organization(org.id)
    assert len(teams) == 1 and teams[0].name == "Engineering"


async def test_membership_repository_round_trip(sqlite_session):
    org_repo = SqlAlchemyOrganizationRepository(session=sqlite_session)
    org = await org_repo.upsert(Organization(id=OrganizationId(uuid4()), name="Acme", slug="acme", owner_user_id=UserId(uuid4())))
    await sqlite_session.commit()

    membership_repo = SqlAlchemyMembershipRepository(session=sqlite_session)
    user = UserId(uuid4())
    membership = await membership_repo.upsert(
        Membership(id=MembershipId(uuid4()), organization_id=org.id, user_id=user, role=OrganizationRole.MEMBER)
    )
    await sqlite_session.commit()

    fetched = await membership_repo.get_for_user(org.id, user)
    assert fetched.id == membership.id

    await membership_repo.delete(membership.id)
    await sqlite_session.commit()
    assert await membership_repo.get_for_user(org.id, user) is None


async def test_invitation_repository_round_trip(sqlite_session):
    org_repo = SqlAlchemyOrganizationRepository(session=sqlite_session)
    org = await org_repo.upsert(Organization(id=OrganizationId(uuid4()), name="Acme", slug="acme", owner_user_id=UserId(uuid4())))
    await sqlite_session.commit()

    invitation_repo = SqlAlchemyInvitationRepository(session=sqlite_session)
    invitation = await invitation_repo.upsert(
        Invitation(
            id=InvitationId(uuid4()),
            organization_id=org.id,
            email="friend@example.com",
            role=OrganizationRole.MEMBER,
            invited_by=UserId(uuid4()),
            token_hash="hash-abc",
            status=InvitationStatus.PENDING,
        )
    )
    await sqlite_session.commit()

    fetched = await invitation_repo.get_by_token_hash("hash-abc")
    assert fetched.id == invitation.id
    assert (await invitation_repo.list_by_organization(org.id))[0].id == invitation.id
