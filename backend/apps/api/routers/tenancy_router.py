"""Multi-Tenancy endpoints — organizations, teams, memberships, invitations (Milestone 6,
docs/api_specification.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_tenancy_service, get_session
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import UserId
from modules.tenancy.application.tenancy_service import InvitationInvalidError, NotAuthorizedError
from modules.tenancy.domain.entities import Invitation, Membership, Organization, Team
from modules.tenancy.domain.value_objects import InvitationId, OrganizationId, OrganizationRole, TeamId

router = APIRouter(prefix="/api/v1/organizations", tags=["tenancy"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {value}") from None


def _serialize_organization(org: Organization) -> dict:
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "owner_user_id": str(org.owner_user_id),
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


def _serialize_team(team: Team) -> dict:
    return {"id": str(team.id), "organization_id": str(team.organization_id), "name": team.name}


def _serialize_membership(membership: Membership) -> dict:
    return {
        "id": str(membership.id),
        "organization_id": str(membership.organization_id),
        "user_id": str(membership.user_id),
        "role": membership.role.value,
        "team_id": str(membership.team_id) if membership.team_id else None,
        "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
    }


def _serialize_invitation(invitation: Invitation) -> dict:
    return {
        "id": str(invitation.id),
        "organization_id": str(invitation.organization_id),
        "email": invitation.email,
        "role": invitation.role.value,
        "status": invitation.status.value,
        "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
    }


class CreateOrganizationRequest(BaseModel):
    name: str


class CreateTeamRequest(BaseModel):
    name: str


class InviteMemberRequest(BaseModel):
    email: str
    role: OrganizationRole = OrganizationRole.MEMBER


class AcceptInvitationRequest(BaseModel):
    token: str


class ChangeMemberRoleRequest(BaseModel):
    role: OrganizationRole


@router.post("")
async def create_organization(
    payload: CreateOrganizationRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_tenancy_service(session)
    organization = await service.create_organization(payload.name, user.id, _now())
    return envelope(_serialize_organization(organization))


@router.post("/{organization_id}/teams")
async def create_team(
    organization_id: str,
    payload: CreateTeamRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_tenancy_service(session)
    try:
        team = await service.create_team(OrganizationId(_parse_uuid(organization_id)), payload.name, user.id, _now())
    except NotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return envelope(_serialize_team(team))


@router.get("/{organization_id}/members")
async def list_members(
    organization_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_tenancy_service(session)
    members = await service.list_members(OrganizationId(_parse_uuid(organization_id)))
    return envelope([_serialize_membership(m) for m in members])


@router.post("/{organization_id}/members/{target_user_id}/role")
async def change_member_role(
    organization_id: str,
    target_user_id: str,
    payload: ChangeMemberRoleRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_tenancy_service(session)
    try:
        membership = await service.change_member_role(
            OrganizationId(_parse_uuid(organization_id)), UserId(_parse_uuid(target_user_id)), payload.role, user.id, _now()
        )
    except NotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return envelope(_serialize_membership(membership))


@router.delete("/{organization_id}/members/{target_user_id}")
async def remove_member(
    organization_id: str,
    target_user_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_tenancy_service(session)
    try:
        await service.remove_member(OrganizationId(_parse_uuid(organization_id)), UserId(_parse_uuid(target_user_id)), user.id, _now())
    except NotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return envelope({"removed": True})


@router.post("/{organization_id}/invitations")
async def invite_member(
    organization_id: str,
    payload: InviteMemberRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_tenancy_service(session)
    try:
        invitation, raw_token = await service.invite_member(
            OrganizationId(_parse_uuid(organization_id)), payload.email, payload.role, user.id, _now()
        )
    except NotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return envelope({**_serialize_invitation(invitation), "raw_token": raw_token})


@router.post("/invitations/accept")
async def accept_invitation(
    payload: AcceptInvitationRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_tenancy_service(session)
    try:
        membership = await service.accept_invitation(payload.token, user.id, _now())
    except InvitationInvalidError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from None
    return envelope(_serialize_membership(membership))


@router.delete("/{organization_id}/invitations/{invitation_id}")
async def revoke_invitation(
    organization_id: str,
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_tenancy_service(session)
    try:
        await service.revoke_invitation(InvitationId(_parse_uuid(invitation_id)), user.id, _now())
    except NotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return envelope({"revoked": True})
