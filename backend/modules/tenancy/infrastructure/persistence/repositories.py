from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.domain.value_objects import UserId
from modules.tenancy.domain.entities import Invitation, Membership, Organization, Team
from modules.tenancy.domain.value_objects import InvitationId, MembershipId, OrganizationId, TeamId
from modules.tenancy.infrastructure.persistence import mappers
from modules.tenancy.infrastructure.persistence.models import (
    InvitationModel,
    MembershipModel,
    OrganizationModel,
    TeamModel,
)


@dataclass
class SqlAlchemyOrganizationRepository:
    session: AsyncSession

    async def get(self, organization_id: OrganizationId) -> Organization | None:
        model = await self.session.get(OrganizationModel, organization_id.value)
        return mappers.organization_to_domain(model) if model else None

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self.session.execute(select(OrganizationModel).where(OrganizationModel.slug == slug))
        model = result.scalar_one_or_none()
        return mappers.organization_to_domain(model) if model else None

    async def list_owned_by(self, owner_user_id: UserId) -> list[Organization]:
        stmt = select(OrganizationModel).where(OrganizationModel.owner_user_id == owner_user_id.value)
        result = await self.session.execute(stmt)
        return [mappers.organization_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, organization: Organization) -> Organization:
        existing = await self.session.get(OrganizationModel, organization.id.value)
        model = mappers.organization_to_model(organization, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.organization_to_domain(model)


@dataclass
class SqlAlchemyTeamRepository:
    session: AsyncSession

    async def get(self, team_id: TeamId) -> Team | None:
        model = await self.session.get(TeamModel, team_id.value)
        return mappers.team_to_domain(model) if model else None

    async def list_by_organization(self, organization_id: OrganizationId) -> list[Team]:
        stmt = select(TeamModel).where(TeamModel.organization_id == organization_id.value)
        result = await self.session.execute(stmt)
        return [mappers.team_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, team: Team) -> Team:
        existing = await self.session.get(TeamModel, team.id.value)
        model = mappers.team_to_model(team, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.team_to_domain(model)


@dataclass
class SqlAlchemyMembershipRepository:
    session: AsyncSession

    async def get(self, membership_id: MembershipId) -> Membership | None:
        model = await self.session.get(MembershipModel, membership_id.value)
        return mappers.membership_to_domain(model) if model else None

    async def get_for_user(self, organization_id: OrganizationId, user_id: UserId) -> Membership | None:
        stmt = select(MembershipModel).where(
            MembershipModel.organization_id == organization_id.value, MembershipModel.user_id == user_id.value
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return mappers.membership_to_domain(model) if model else None

    async def list_by_organization(self, organization_id: OrganizationId) -> list[Membership]:
        stmt = select(MembershipModel).where(MembershipModel.organization_id == organization_id.value)
        result = await self.session.execute(stmt)
        return [mappers.membership_to_domain(row) for row in result.scalars().all()]

    async def list_by_user(self, user_id: UserId) -> list[Membership]:
        stmt = select(MembershipModel).where(MembershipModel.user_id == user_id.value)
        result = await self.session.execute(stmt)
        return [mappers.membership_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, membership: Membership) -> Membership:
        existing = await self.session.get(MembershipModel, membership.id.value)
        model = mappers.membership_to_model(membership, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.membership_to_domain(model)

    async def delete(self, membership_id: MembershipId) -> None:
        model = await self.session.get(MembershipModel, membership_id.value)
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()


@dataclass
class SqlAlchemyInvitationRepository:
    session: AsyncSession

    async def get(self, invitation_id: InvitationId) -> Invitation | None:
        model = await self.session.get(InvitationModel, invitation_id.value)
        return mappers.invitation_to_domain(model) if model else None

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        stmt = select(InvitationModel).where(InvitationModel.token_hash == token_hash)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return mappers.invitation_to_domain(model) if model else None

    async def list_by_organization(self, organization_id: OrganizationId) -> list[Invitation]:
        stmt = select(InvitationModel).where(InvitationModel.organization_id == organization_id.value)
        result = await self.session.execute(stmt)
        return [mappers.invitation_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, invitation: Invitation) -> Invitation:
        existing = await self.session.get(InvitationModel, invitation.id.value)
        model = mappers.invitation_to_model(invitation, existing)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return mappers.invitation_to_domain(model)
