from __future__ import annotations

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
from modules.tenancy.infrastructure.persistence.models import (
    InvitationModel,
    MembershipModel,
    OrganizationModel,
    TeamModel,
)


def organization_to_domain(model: OrganizationModel) -> Organization:
    return Organization(
        id=OrganizationId(model.id),
        name=model.name,
        slug=model.slug,
        owner_user_id=UserId(model.owner_user_id),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def organization_to_model(entity: Organization, model: OrganizationModel | None = None) -> OrganizationModel:
    model = model or OrganizationModel(id=entity.id.value)
    model.name = entity.name
    model.slug = entity.slug
    model.owner_user_id = entity.owner_user_id.value
    model.updated_at = entity.updated_at
    return model


def team_to_domain(model: TeamModel) -> Team:
    return Team(
        id=TeamId(model.id),
        organization_id=OrganizationId(model.organization_id),
        name=model.name,
        created_at=model.created_at,
    )


def team_to_model(entity: Team, model: TeamModel | None = None) -> TeamModel:
    model = model or TeamModel(id=entity.id.value)
    model.organization_id = entity.organization_id.value
    model.name = entity.name
    return model


def membership_to_domain(model: MembershipModel) -> Membership:
    return Membership(
        id=MembershipId(model.id),
        organization_id=OrganizationId(model.organization_id),
        user_id=UserId(model.user_id),
        role=OrganizationRole(model.role),
        team_id=TeamId(model.team_id) if model.team_id else None,
        joined_at=model.joined_at,
    )


def membership_to_model(entity: Membership, model: MembershipModel | None = None) -> MembershipModel:
    model = model or MembershipModel(id=entity.id.value)
    model.organization_id = entity.organization_id.value
    model.user_id = entity.user_id.value
    model.role = entity.role.value
    model.team_id = entity.team_id.value if entity.team_id else None
    return model


def invitation_to_domain(model: InvitationModel) -> Invitation:
    return Invitation(
        id=InvitationId(model.id),
        organization_id=OrganizationId(model.organization_id),
        email=model.email,
        role=OrganizationRole(model.role),
        invited_by=UserId(model.invited_by),
        token_hash=model.token_hash,
        status=InvitationStatus(model.status),
        created_at=model.created_at,
        expires_at=model.expires_at,
        responded_at=model.responded_at,
    )


def invitation_to_model(entity: Invitation, model: InvitationModel | None = None) -> InvitationModel:
    model = model or InvitationModel(id=entity.id.value)
    model.organization_id = entity.organization_id.value
    model.email = entity.email
    model.role = entity.role.value
    model.invited_by = entity.invited_by.value
    model.token_hash = entity.token_hash
    model.status = entity.status.value
    model.expires_at = entity.expires_at
    model.responded_at = entity.responded_at
    return model
