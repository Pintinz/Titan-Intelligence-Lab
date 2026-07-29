from __future__ import annotations

from modules.identity.domain.entities import (
    AccountLockState,
    AuditLogEntry,
    FederatedIdentity,
    PersonalAccessToken,
    Profile,
    SecurityEvent,
    Session,
    User,
)
from modules.identity.domain.value_objects import (
    AuditAction,
    AuditEventId,
    Email,
    FederatedIdentityId,
    IdentityProvider,
    Role,
    SecurityEventId,
    SecurityEventType,
    SessionId,
    SessionRiskLevel,
    TokenId,
    UserId,
    UserStatus,
)
from modules.identity.infrastructure.persistence.models import (
    AccountLockStateModel,
    AuditLogEntryModel,
    FederatedIdentityModel,
    PersonalAccessTokenModel,
    ProfileModel,
    SecurityEventModel,
    SessionModel,
    UserModel,
)


def user_to_domain(model: UserModel) -> User:
    return User(
        id=UserId(model.id),
        email=Email(model.email),
        role=Role(model.role),
        status=UserStatus(model.status),
        password_hash=model.password_hash,
        email_verified=model.email_verified,
        created_at=model.created_at,
        updated_at=model.updated_at,
        last_login_at=model.last_login_at,
    )


def user_to_model(entity: User, model: UserModel | None = None) -> UserModel:
    model = model or UserModel(id=entity.id.value)
    model.email = str(entity.email)
    model.role = entity.role.value
    model.status = entity.status.value
    model.password_hash = entity.password_hash
    model.email_verified = entity.email_verified
    model.last_login_at = entity.last_login_at
    return model


def profile_to_domain(model: ProfileModel) -> Profile:
    return Profile(
        user_id=UserId(model.user_id),
        display_name=model.display_name,
        avatar_url=model.avatar_url,
        bio=model.bio,
        timezone=model.timezone,
        locale=model.locale,
        updated_at=model.updated_at,
    )


def profile_to_model(entity: Profile, model: ProfileModel | None = None) -> ProfileModel:
    model = model or ProfileModel(user_id=entity.user_id.value)
    model.display_name = entity.display_name
    model.avatar_url = entity.avatar_url
    model.bio = entity.bio
    model.timezone = entity.timezone
    model.locale = entity.locale
    model.updated_at = entity.updated_at
    return model


def federated_identity_to_domain(model: FederatedIdentityModel) -> FederatedIdentity:
    return FederatedIdentity(
        id=FederatedIdentityId(model.id),
        user_id=UserId(model.user_id),
        provider=IdentityProvider(model.provider),
        provider_user_id=model.provider_user_id,
        provider_email=model.provider_email,
        linked_at=model.linked_at,
    )


def federated_identity_to_model(
    entity: FederatedIdentity, model: FederatedIdentityModel | None = None
) -> FederatedIdentityModel:
    model = model or FederatedIdentityModel(id=entity.id.value)
    model.user_id = entity.user_id.value
    model.provider = entity.provider.value
    model.provider_user_id = entity.provider_user_id
    model.provider_email = entity.provider_email
    model.linked_at = entity.linked_at
    return model


def pat_to_domain(model: PersonalAccessTokenModel) -> PersonalAccessToken:
    return PersonalAccessToken(
        id=TokenId(model.id),
        user_id=UserId(model.user_id),
        name=model.name,
        token_hash=model.token_hash,
        scopes=list(model.scopes or []),
        created_at=model.created_at,
        expires_at=model.expires_at,
        last_used_at=model.last_used_at,
        revoked_at=model.revoked_at,
    )


def pat_to_model(entity: PersonalAccessToken, model: PersonalAccessTokenModel | None = None) -> PersonalAccessTokenModel:
    model = model or PersonalAccessTokenModel(id=entity.id.value)
    model.user_id = entity.user_id.value
    model.name = entity.name
    model.token_hash = entity.token_hash
    model.scopes = list(entity.scopes)
    model.expires_at = entity.expires_at
    model.last_used_at = entity.last_used_at
    model.revoked_at = entity.revoked_at
    return model


def session_to_domain(model: SessionModel) -> Session:
    return Session(
        id=SessionId(model.id),
        user_id=UserId(model.user_id),
        device_label=model.device_label,
        browser=model.browser,
        ip_address=model.ip_address,
        user_agent=model.user_agent,
        risk_level=SessionRiskLevel(model.risk_level),
        risk_indicators=list(model.risk_indicators or []),
        created_at=model.created_at,
        last_seen_at=model.last_seen_at,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
    )


def session_to_model(entity: Session, model: SessionModel | None = None) -> SessionModel:
    model = model or SessionModel(id=entity.id.value)
    model.user_id = entity.user_id.value
    model.device_label = entity.device_label
    model.browser = entity.browser
    model.ip_address = entity.ip_address
    model.user_agent = entity.user_agent
    model.risk_level = entity.risk_level.value
    model.risk_indicators = list(entity.risk_indicators)
    model.last_seen_at = entity.last_seen_at
    model.expires_at = entity.expires_at
    model.revoked_at = entity.revoked_at
    return model


def security_event_to_domain(model: SecurityEventModel) -> SecurityEvent:
    return SecurityEvent(
        id=SecurityEventId(model.id),
        event_type=SecurityEventType(model.event_type),
        occurred_at=model.occurred_at,
        user_id=UserId(model.user_id) if model.user_id else None,
        email_attempted=model.email_attempted,
        ip_address=model.ip_address,
        user_agent=model.user_agent,
        metadata=dict(model.event_metadata or {}),
    )


def security_event_to_model(entity: SecurityEvent) -> SecurityEventModel:
    return SecurityEventModel(
        id=entity.id.value,
        event_type=entity.event_type.value,
        occurred_at=entity.occurred_at,
        user_id=entity.user_id.value if entity.user_id else None,
        email_attempted=entity.email_attempted,
        ip_address=entity.ip_address,
        user_agent=entity.user_agent,
        event_metadata=entity.metadata,
    )


def lock_state_to_domain(model: AccountLockStateModel) -> AccountLockState:
    return AccountLockState(
        user_id=UserId(model.user_id),
        consecutive_failures=model.consecutive_failures,
        locked_until=model.locked_until,
        last_failure_at=model.last_failure_at,
    )


def lock_state_to_model(entity: AccountLockState, model: AccountLockStateModel | None = None) -> AccountLockStateModel:
    model = model or AccountLockStateModel(user_id=entity.user_id.value)
    model.consecutive_failures = entity.consecutive_failures
    model.locked_until = entity.locked_until
    model.last_failure_at = entity.last_failure_at
    return model


def audit_entry_to_domain(model: AuditLogEntryModel) -> AuditLogEntry:
    return AuditLogEntry(
        id=AuditEventId(model.id),
        action=AuditAction(model.action),
        occurred_at=model.occurred_at,
        actor_user_id=UserId(model.actor_user_id) if model.actor_user_id else None,
        target_type=model.target_type,
        target_id=model.target_id,
        ip_address=model.ip_address,
        metadata=dict(model.event_metadata or {}),
    )


def audit_entry_to_model(entity: AuditLogEntry) -> AuditLogEntryModel:
    return AuditLogEntryModel(
        id=entity.id.value,
        action=entity.action.value,
        occurred_at=entity.occurred_at,
        actor_user_id=entity.actor_user_id.value if entity.actor_user_id else None,
        target_type=entity.target_type,
        target_id=entity.target_id,
        ip_address=entity.ip_address,
        event_metadata=entity.metadata,
    )
