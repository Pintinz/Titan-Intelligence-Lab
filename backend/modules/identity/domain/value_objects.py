"""Value objects for the Identity & Security bounded context (docs/security.md, Milestone 6).

No framework imports — same domain-purity rule as every other module (docs/architecture.md §2).
Supabase Auth issues/validates credentials at the infrastructure edge; every value here is
plain Python so the domain has zero dependency on Supabase, JWT libraries, or FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class Role(str, Enum):
    """Enterprise RBAC ladder (docs/security.md). Ordinal position (via ``level``) is what
    authorization checks compare — never the enum member identity — so a new role can be
    inserted without every call site needing an explicit branch."""

    GUEST = "guest"
    FREE = "free"
    REWARDED = "rewarded"
    PREMIUM = "premium"
    MODERATOR = "moderator"
    ANALYST = "analyst"
    ADMINISTRATOR = "administrator"
    SUPER_ADMINISTRATOR = "super_administrator"

    @property
    def level(self) -> int:
        return _ROLE_LEVELS[self]

    def at_least(self, other: "Role") -> bool:
        return self.level >= other.level


_ROLE_LEVELS: dict[Role, int] = {
    Role.GUEST: 0,
    Role.FREE: 1,
    Role.REWARDED: 2,
    Role.PREMIUM: 3,
    Role.MODERATOR: 4,
    Role.ANALYST: 5,
    Role.ADMINISTRATOR: 6,
    Role.SUPER_ADMINISTRATOR: 7,
}


class UserStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LOCKED = "locked"
    DELETED = "deleted"


class IdentityProvider(str, Enum):
    """Federated identity interfaces (Milestone 6 spec). APPLE/MICROSOFT are modeled now so the
    linkage table and ports never need a schema change to add them — the OAuth adapter itself
    is stubbed until Supabase Auth has those providers configured (docs/supabase.md)."""

    EMAIL = "email"
    GOOGLE = "google"
    GITHUB = "github"
    APPLE = "apple"
    MICROSOFT = "microsoft"


class AuditAction(str, Enum):
    """Closed vocabulary for the immutable security audit trail — an open-ended free-text
    action would let a bug silently write unqueryable garbage into a log that's supposed to be
    the source of truth for incident response."""

    USER_REGISTERED = "user_registered"
    USER_LOGIN_SUCCEEDED = "user_login_succeeded"
    USER_LOGIN_FAILED = "user_login_failed"
    USER_LOGGED_OUT = "user_logged_out"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    EMAIL_VERIFIED = "email_verified"
    ROLE_CHANGED = "role_changed"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    ACCOUNT_SUSPENDED = "account_suspended"
    SESSION_REVOKED = "session_revoked"
    IDENTITY_LINKED = "identity_linked"
    IDENTITY_UNLINKED = "identity_unlinked"
    PAT_CREATED = "pat_created"
    PAT_REVOKED = "pat_revoked"
    ORGANIZATION_CREATED = "organization_created"
    MEMBERSHIP_CHANGED = "membership_changed"
    SUBSCRIPTION_CHANGED = "subscription_changed"
    PROVIDER_REGISTERED = "provider_registered"
    PROVIDER_UPDATED = "provider_updated"
    PROVIDER_DELETED = "provider_deleted"
    PROVIDER_ACTIVATED = "provider_activated"
    PROVIDER_DEACTIVATED = "provider_deactivated"
    PROVIDER_CREDENTIAL_ADDED = "provider_credential_added"
    PROVIDER_CREDENTIAL_ROTATED = "provider_credential_rotated"
    PROVIDER_IMPORTED_FROM_ENV = "provider_imported_from_env"


class SecurityEventType(str, Enum):
    LOGIN_FAILURE = "login_failure"
    LOGIN_SUCCESS = "login_success"
    BRUTE_FORCE_DETECTED = "brute_force_detected"
    SUSPICIOUS_LOGIN = "suspicious_login"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"


class SessionRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class UserId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class FederatedIdentityId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SessionId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class TokenId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class AuditEventId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SecurityEventId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Email:
    """Normalized (lower-cased) email — equality/hash must be case-insensitive since RFC 5321
    local-parts are case-sensitive in theory but every real provider treats them as not, and
    two `User` rows differing only by email case would defeat the whole point of uniqueness."""

    value: str

    def __post_init__(self) -> None:
        if "@" not in self.value:
            raise ValueError(f"Invalid email: {self.value!r}")
        object.__setattr__(self, "value", self.value.strip().lower())

    def __str__(self) -> str:
        return self.value
