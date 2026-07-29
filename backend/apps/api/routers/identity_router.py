"""Identity & Security endpoints — registration, login, sessions, PATs (Milestone 6,
docs/api_specification.md `/api/v1/auth`, `/api/v1/users`).

Registration/login (bcrypt) are the offline/mock authentication path (see
``IdentityService.ensure_provisioned`` docstring) — kept as real endpoints because the fast
SQLite test suite and any non-Supabase deployment need a working auth flow that doesn't depend
on a live Supabase Auth instance. Production clients normally authenticate directly against
Supabase Auth and only ever call this API with the resulting JWT.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user, require_role
from apps.api.composition import build_identity_service, get_session
from modules.identity.application.identity_service import (
    AccountLockedError,
    InvalidCredentialsError,
)
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import Email, Role, SessionId, TokenId, UserId

router = APIRouter(prefix="/api/v1", tags=["identity"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": str(user.email),
        "role": user.role.value,
        "status": user.status.value,
        "email_verified": user.email_verified,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangeRoleRequest(BaseModel):
    role: Role


class CreateTokenRequest(BaseModel):
    name: str
    scopes: list[str] = []


@router.post("/auth/register")
async def register(payload: RegisterRequest, session: AsyncSession = Depends(get_session)):
    service = build_identity_service(session)
    try:
        user = await service.register(Email(payload.email), payload.password, _now())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(_serialize_user(user))


@router.post("/auth/login")
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)):
    """Returns an ``access_token`` (a short-lived Personal Access Token, not a Supabase JWT) —
    this is the offline/mock authentication path (see ``IdentityService.ensure_provisioned``
    docstring). It lets a client authenticate subsequent requests via the same
    ``Authorization: Bearer`` header and PAT-fallback code path in ``get_current_user`` without
    a live Supabase project. Production clients get their bearer token directly from Supabase
    Auth instead and never call this endpoint."""
    service = build_identity_service(session)
    now = _now()
    try:
        result = await service.authenticate(Email(payload.email), payload.password, now)
    except AccountLockedError as exc:
        raise HTTPException(status_code=423, detail=f"Account locked until {exc.locked_until.isoformat()}") from None
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None

    _token, raw_token = await service.create_personal_access_token(
        result.user.id, "offline-login-session", ["*"], now, expires_at=now + timedelta(hours=12)
    )
    return envelope(
        {
            "user": _serialize_user(result.user),
            "session_id": str(result.session.id),
            "risk_level": result.session.risk_level.value,
            "access_token": raw_token,
        }
    )


@router.get("/users/me")
async def get_me(user: User = Depends(get_current_user)):
    return envelope(_serialize_user(user))


@router.post("/users/{user_id}/role")
async def change_role(
    user_id: str,
    payload: ChangeRoleRequest,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_identity_service(session)
    try:
        target = await service.change_role(UserId(_parse_uuid(user_id)), payload.role, _now(), actor.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return envelope(_serialize_user(target))


@router.get("/users/me/sessions")
async def list_sessions(session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)):
    service = build_identity_service(session)
    sessions = await service.list_active_sessions(user.id)
    return envelope(
        [
            {
                "id": str(s.id),
                "device_label": s.device_label,
                "ip_address": s.ip_address,
                "risk_level": s.risk_level.value,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
            }
            for s in sessions
        ]
    )


@router.delete("/users/me/sessions/{session_id}")
async def revoke_session(
    session_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_identity_service(session)
    await service.revoke_session(SessionId(_parse_uuid(session_id)), _now(), actor=user.id)
    return envelope({"revoked": True})


@router.post("/users/me/tokens")
async def create_token(
    payload: CreateTokenRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_identity_service(session)
    token, raw_token = await service.create_personal_access_token(user.id, payload.name, payload.scopes, _now())
    return envelope(
        {
            "id": str(token.id),
            "name": token.name,
            "scopes": token.scopes,
            "raw_token": raw_token,  # shown exactly once — never recoverable after this response
        }
    )


@router.get("/users/me/tokens")
async def list_tokens(session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)):
    service = build_identity_service(session)
    tokens = await service.list_personal_access_tokens(user.id)
    return envelope(
        [
            {
                "id": str(t.id),
                "name": t.name,
                "scopes": t.scopes,
                "is_active": t.is_active,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
            }
            for t in tokens
        ]
    )


@router.delete("/users/me/tokens/{token_id}")
async def revoke_token(
    token_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_identity_service(session)
    await service.revoke_personal_access_token(TokenId(_parse_uuid(token_id)), _now(), actor=user.id)
    return envelope({"revoked": True})


def _parse_uuid(value: str):
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {value}") from None
