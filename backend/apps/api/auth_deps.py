"""Authentication/authorization FastAPI dependencies (Milestone 6, docs/authentication.md).

``get_current_user`` accepts either a Supabase Auth JWT (the normal browser/app login path) or
a Personal Access Token (the API-automation path) in the ``Authorization: Bearer <token>``
header — JWT validation is tried first since it's the common case, falling back to PAT lookup
on failure rather than requiring the caller to signal which kind of token it's sending.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.composition import build_identity_service, get_jwt_validator, get_session
from modules.identity.application.identity_service import IdentityService
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import Email, IdentityProvider, Role, UserId
from modules.identity.infrastructure.security import JWTValidationError
from modules.identity.ports.security import JWTValidatorPort

# Supabase's own provider identifiers (app_metadata.provider on the JWT) that map onto our
# federated-identity vocabulary. "email" means password/magic-link — not a federated provider,
# so it's deliberately absent here and never triggers a FederatedIdentity link.
_SUPABASE_PROVIDER_MAP = {
    "google": IdentityProvider.GOOGLE,
    "github": IdentityProvider.GITHUB,
    "apple": IdentityProvider.APPLE,
    "azure": IdentityProvider.MICROSOFT,  # Supabase's provider id for Microsoft/Azure AD is "azure"
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _authenticate_via_jwt(
    token: str, validator: JWTValidatorPort, identity_service: IdentityService
) -> User | None:
    try:
        claims = await validator.validate(token)
    except JWTValidationError:
        return None
    subject = claims.get("sub")
    email = claims.get("email")
    if subject is None or email is None:
        return None
    try:
        user_id = UserId(uuid.UUID(str(subject)))
    except ValueError:
        return None

    user = await identity_service.ensure_provisioned(user_id, Email(email), _now())

    provider_key = (claims.get("app_metadata") or {}).get("provider")
    provider = _SUPABASE_PROVIDER_MAP.get(provider_key)
    if provider is not None:
        # Supabase's JWT doesn't carry the upstream provider's own subject id, so the
        # Supabase user id doubles as the provider_user_id here — enough to record "this
        # account has signed in via Google/GitHub/etc." for the linked-accounts UI and audit
        # trail, without needing a second call to Supabase's Admin API for the raw identity.
        await identity_service.ensure_federated_identity_linked(user_id, provider, str(subject), email, _now())

    return user


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    validator: JWTValidatorPort = Depends(get_jwt_validator),
) -> User:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()

    identity_service = build_identity_service(session)

    user = await _authenticate_via_jwt(token, validator, identity_service)
    if user is None:
        user = await identity_service.authenticate_with_token(token, _now())
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials")
    if not user.can_authenticate():
        raise HTTPException(status_code=403, detail="Account is not active")
    return user


def require_role(minimum: Role):
    """Dependency factory — ``Depends(require_role(Role.ADMINISTRATOR))`` gates a route to
    users whose platform-wide role is at least ``minimum`` on the RBAC ladder
    (``Role.at_least``, docs/security.md)."""

    async def _check(user: User = Depends(get_current_user)) -> User:
        if not user.is_at_least(minimum):
            raise HTTPException(status_code=403, detail=f"Requires role >= {minimum.value}")
        return user

    return _check
