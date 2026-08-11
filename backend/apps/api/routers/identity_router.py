"""Identity & Security endpoints — registration, login, sessions, PATs (Milestone 6,
docs/api_specification.md `/api/v1/auth`, `/api/v1/users`).

Registration/login (bcrypt) are the offline/mock authentication path (see
``IdentityService.ensure_provisioned`` docstring) — kept as real endpoints because the fast
SQLite test suite and any non-Supabase deployment need a working auth flow that doesn't depend
on a live Supabase Auth instance. Production clients normally authenticate directly against
Supabase Auth and only ever call this API with the resulting JWT.

Both `/auth/register` and `/auth/login` are gated behind `TITANIQ_ENABLE_OFFLINE_AUTH` (see
`_offline_auth_enabled` below) — default OFF, so a production deployment that forgets to
explicitly disable this path doesn't end up with it silently reachable (Security Milestone
finding H-4: this path has no email-verification enforcement, so leaving it open in production
would let anyone mass-create fully-functional accounts around whatever verification guarantees
the product otherwise relies on Supabase for).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user, require_role
from apps.api.composition import build_identity_service, get_session
from apps.api.rate_limit import rate_limit_by_ip
from modules.identity.application.identity_service import (
    AccountLockedError,
    InvalidCredentialsError,
    NotSessionOwnerError,
    NotTokenOwnerError,
    RoleEscalationError,
)
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import Email, Role, SessionId, TokenId, UserId

router = APIRouter(prefix="/api/v1", tags=["identity"])


def _offline_auth_enabled() -> bool:
    """Read fresh per call (not cached at import) so tests can flip it via `monkeypatch.setenv`
    without needing to reload this module. Defaults OFF — a production deployment that never sets
    this flag gets the offline/bcrypt path closed rather than silently reachable (Security
    Milestone finding H-4); the test suite's root `tests/conftest.py` sets it on for the whole
    run, and local non-Supabase dev sets it in `.env`, matching this module's own stated intent
    that the path exists for "the fast SQLite test suite and any non-Supabase deployment"."""
    return os.environ.get("TITANIQ_ENABLE_OFFLINE_AUTH", "false").strip().lower() in ("1", "true", "yes")


def _require_offline_auth_enabled() -> None:
    if not _offline_auth_enabled():
        raise HTTPException(status_code=404, detail="Not Found")


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


_DEFAULT_PAT_EXPIRY_DAYS = 90
_MAX_PAT_EXPIRY_DAYS = 365


class CreateTokenRequest(BaseModel):
    name: str
    scopes: list[str] = []
    expires_in_days: int | None = None


@router.post(
    "/auth/register",
    dependencies=[
        Depends(_require_offline_auth_enabled),
        Depends(rate_limit_by_ip("auth_register", limit=5, window_seconds=3600)),
    ],
)
async def register(payload: RegisterRequest, session: AsyncSession = Depends(get_session)):
    service = build_identity_service(session)
    try:
        user = await service.register(Email(payload.email), payload.password, _now())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(_serialize_user(user))


@router.post(
    "/auth/login",
    dependencies=[
        Depends(_require_offline_auth_enabled),
        Depends(rate_limit_by_ip("auth_login", limit=10, window_seconds=60)),
    ],
)
async def login(payload: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)):
    """Returns an ``access_token`` (a short-lived Personal Access Token, not a Supabase JWT) —
    this is the offline/mock authentication path (see ``IdentityService.ensure_provisioned``
    docstring). It lets a client authenticate subsequent requests via the same
    ``Authorization: Bearer`` header and PAT-fallback code path in ``get_current_user`` without
    a live Supabase project. Production clients get their bearer token directly from Supabase
    Auth instead and never call this endpoint."""
    service = build_identity_service(session)
    now = _now()
    # `request.client.host`, not a client-supplied header — same reasoning as rate_limit.py's
    # own IP source: no reverse-proxy X-Forwarded-For trust chain is configured anywhere in this
    # deployment, so trusting a header here would let it be spoofed trivially. Without this
    # (Security Milestone finding M-7), every `SecurityEvent`/`Session` and the login risk
    # assessment (`_assess_risk`) that reads it were blind to source IP even though the service
    # layer already fully supports it — a router-only gap, not a missing capability.
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        result = await service.authenticate(Email(payload.email), payload.password, now, ip_address, user_agent)
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
        target = await service.change_role(UserId(_parse_uuid(user_id)), payload.role, _now(), actor.id, actor.role)
    except RoleEscalationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
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
    try:
        await service.revoke_session(SessionId(_parse_uuid(session_id)), _now(), actor=user.id)
    except NotSessionOwnerError:
        # 404, not 403 — a caller must not learn that a session ID they don't own even exists.
        raise HTTPException(status_code=404, detail="session not found") from None
    return envelope({"revoked": True})


@router.post("/users/me/tokens")
async def create_token(
    payload: CreateTokenRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_identity_service(session)
    now = _now()
    # User-created PATs always expire — an indefinitely-lived credential is exactly the risk
    # Security Milestone finding H-8 flagged (no PAT ever expired unless the caller happened to
    # pass expires_at, which no client did). Default 90 days; callers may request a shorter or
    # longer lifetime up to a hard cap so a token still can't be minted to outlive review.
    requested_days = payload.expires_in_days if payload.expires_in_days is not None else _DEFAULT_PAT_EXPIRY_DAYS
    expiry_days = max(1, min(requested_days, _MAX_PAT_EXPIRY_DAYS))
    token, raw_token = await service.create_personal_access_token(
        user.id, payload.name, payload.scopes, now, expires_at=now + timedelta(days=expiry_days)
    )
    return envelope(
        {
            "id": str(token.id),
            "name": token.name,
            "scopes": token.scopes,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
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
                "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            }
            for t in tokens
        ]
    )


@router.delete("/users/me/tokens/{token_id}")
async def revoke_token(
    token_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_identity_service(session)
    try:
        await service.revoke_personal_access_token(TokenId(_parse_uuid(token_id)), _now(), actor=user.id)
    except NotTokenOwnerError:
        raise HTTPException(status_code=404, detail="token not found") from None
    return envelope({"revoked": True})


def _parse_uuid(value: str):
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {value}") from None
