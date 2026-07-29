"""Entities for the Identity & Security bounded context (Milestone 6).

``User.password_hash`` is opaque ciphertext produced by a ``PasswordHasherPort`` implementation
(bcrypt/argon2 in the real adapter) — the domain layer never compares plaintext passwords
directly, same pattern as ``ProviderCredential.encrypted_value`` in modules.admin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

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


@dataclass
class User:
    id: UserId
    email: Email
    role: Role = Role.FREE
    status: UserStatus = UserStatus.PENDING_VERIFICATION
    password_hash: str | None = None  # None for OAuth-only accounts
    email_verified: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None

    def can_authenticate(self) -> bool:
        return self.status in (UserStatus.ACTIVE, UserStatus.PENDING_VERIFICATION)

    def is_at_least(self, role: Role) -> bool:
        return self.role.at_least(role)


@dataclass
class Profile:
    """Separated from ``User`` because profile fields (display name, avatar, bio) are
    self-service-editable and RLS-owner-scoped, while ``User`` (role, status, password_hash)
    is written only by the identity application layer — one table, one write path each."""

    user_id: UserId
    display_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    timezone: str = "UTC"
    locale: str = "en"
    updated_at: datetime | None = None


@dataclass
class FederatedIdentity:
    id: FederatedIdentityId
    user_id: UserId
    provider: IdentityProvider
    provider_user_id: str
    provider_email: str | None = None
    linked_at: datetime | None = None


@dataclass
class PersonalAccessToken:
    """``token_hash`` stores a one-way hash (never the raw token) — the raw value is shown to
    the user exactly once at creation time and cannot be recovered afterward, matching how
    GitHub/GitLab PATs behave (docs/security.md)."""

    id: TokenId
    user_id: UserId
    name: str
    token_hash: str
    scopes: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def is_expired(self, as_of: datetime) -> bool:
        return self.expires_at is not None and as_of >= self.expires_at

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or "*" in self.scopes


@dataclass
class Session:
    """Session Intelligence record — one row per active login session, materialized (not
    derived from an event log) so "list my concurrent sessions" and "revoke this device" are
    O(1) reads/writes instead of scanning an audit trail (same rationale as
    ``ProviderHealthState`` in modules.admin)."""

    id: SessionId
    user_id: UserId
    device_label: str | None = None
    browser: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    risk_level: SessionRiskLevel = SessionRiskLevel.LOW
    risk_indicators: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


@dataclass
class SecurityEvent:
    """Append-only Security Intelligence record — failed logins, brute-force detections,
    suspicious logins, lock/unlock events. ``user_id`` is nullable because a failed login
    against an email with no matching account is still a signal worth recording."""

    id: SecurityEventId
    event_type: SecurityEventType
    occurred_at: datetime
    user_id: UserId | None = None
    email_attempted: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AccountLockState:
    """Materialized brute-force protection state, one row per user — mirrors
    ``ProviderHealthState``'s rationale: O(1) lockout checks on every login attempt instead of
    rescanning ``SecurityEvent`` history."""

    user_id: UserId
    consecutive_failures: int = 0
    locked_until: datetime | None = None
    last_failure_at: datetime | None = None

    def is_locked(self, as_of: datetime) -> bool:
        return self.locked_until is not None and as_of < self.locked_until


@dataclass
class AuditLogEntry:
    """Immutable security audit trail — append-only, never updated or deleted by application
    code (enforced at the infrastructure layer: no UPDATE/DELETE repository method exists).
    Distinct from ``ingestion.TimelineEvent`` (M5), which audits data-sync activity; this one
    audits identity/security/tenancy/billing actions (docs/decisions.md)."""

    id: AuditEventId
    action: AuditAction
    occurred_at: datetime
    actor_user_id: UserId | None = None
    target_type: str | None = None
    target_id: str | None = None
    ip_address: str | None = None
    metadata: dict = field(default_factory=dict)
