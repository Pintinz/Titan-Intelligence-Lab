"""IdentityService — registration, authentication, brute-force protection, and audit emission
for the Identity & Security bounded context (Milestone 6).

Mirrors the orchestration style of ``HealthIntelligenceEngine`` (modules.admin): ``now`` is
always passed in by the caller rather than read internally, so every method is deterministic
and unit-testable without monkeypatching the clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from modules.identity.domain.entities import (
    AccountLockState,
    AuditLogEntry,
    FederatedIdentity,
    PersonalAccessToken,
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
from modules.identity.ports.repositories import (
    AccountLockRepositoryPort,
    AuditLogRepositoryPort,
    FederatedIdentityRepositoryPort,
    PersonalAccessTokenRepositoryPort,
    SecurityEventRepositoryPort,
    SessionRepositoryPort,
    UserRepositoryPort,
)
from modules.identity.ports.security import PasswordHasherPort, TokenHasherPort


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — every datetime
    in this codebase is UTC by convention, so a naive value read back from storage is assumed
    to be UTC and stamped to match ``reference``'s awareness before comparison. Real Postgres/
    asyncpg preserves tzinfo correctly; this only bites in the SQLite testing path, but the
    service needs to not crash regardless of which database produced the row."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


class AccountLockedError(Exception):
    def __init__(self, locked_until: datetime) -> None:
        self.locked_until = locked_until
        super().__init__(f"Account locked until {locked_until.isoformat()}")


class InvalidCredentialsError(Exception):
    pass


@dataclass(frozen=True)
class LoginResult:
    user: User
    session: Session


@dataclass
class IdentityService:
    users: UserRepositoryPort
    federated_identities: FederatedIdentityRepositoryPort
    tokens: PersonalAccessTokenRepositoryPort
    sessions: SessionRepositoryPort
    security_events: SecurityEventRepositoryPort
    account_locks: AccountLockRepositoryPort
    audit_log: AuditLogRepositoryPort
    password_hasher: PasswordHasherPort
    token_hasher: TokenHasherPort
    max_consecutive_failures: int = 5
    lockout_duration: timedelta = timedelta(minutes=15)
    brute_force_window: timedelta = timedelta(minutes=15)
    # Must be <= max_consecutive_failures: once an account is locked, authenticate() short-
    # circuits on the lock check before _record_failure ever runs again, so no further
    # LOGIN_FAILURE events get recorded for it — a brute_force_threshold above the lockout
    # threshold would make this detection path unreachable. Firing lower/equal makes it a
    # distinct, earlier signal ("someone's guessing this account") rather than a redundant one.
    brute_force_threshold: int = 3

    # -- registration --------------------------------------------------------------------------

    async def register(self, email: Email, password: str, now: datetime) -> User:
        existing = await self.users.get_by_email(email)
        if existing is not None:
            raise ValueError(f"Account already exists for {email}")

        user = User(
            id=UserId(uuid4()),
            email=email,
            role=Role.FREE,
            status=UserStatus.PENDING_VERIFICATION,
            password_hash=self.password_hasher.hash(password),
            created_at=now,
            updated_at=now,
        )
        await self.users.upsert(user)
        await self._audit(AuditAction.USER_REGISTERED, now, actor=user.id, target_type="user", target_id=str(user.id))
        return user

    async def ensure_provisioned(self, supabase_user_id: UserId, email: Email, now: datetime) -> User:
        """The REAL production authentication path (docs/authentication.md, docs/decisions.md):
        Supabase Auth (GoTrue) is the actual credential store and JWT issuer — it owns
        password verification, email verification, magic links, and OAuth. FastAPI never
        re-implements that; it validates the resulting JWT (``JWTValidatorPort``) and calls
        this method with the token's ``sub`` claim to get-or-create the local ``identity.users``
        shadow row that everything else (RBAC role, entitlements, audit, memberships) hangs off.

        ``register``/``authenticate`` (password + bcrypt) above remain the OFFLINE/MOCK path —
        same mock-first rationale as ``fakeredis``/``FakeSportsProvider`` elsewhere: they let the
        fast SQLite test suite and any non-Supabase deployment target exercise identity flows
        without a live Supabase Auth instance. In production, ``identity.users.id`` is provisioned
        to equal Supabase's ``auth.users.id`` so ``auth.uid()`` lines up directly with it in RLS
        policies — this method is what establishes that equality on first sight of a user.
        """
        existing = await self.users.get(supabase_user_id)
        if existing is not None:
            return existing

        by_email = await self.users.get_by_email(email)
        if by_email is not None:
            return by_email

        user = User(
            id=supabase_user_id,
            email=email,
            role=Role.FREE,
            status=UserStatus.ACTIVE,
            email_verified=True,  # Supabase Auth already verified before issuing the JWT
            created_at=now,
            updated_at=now,
        )
        await self.users.upsert(user)
        await self._audit(AuditAction.USER_REGISTERED, now, actor=user.id, target_type="user", target_id=str(user.id))
        return user

    async def link_federated_identity(
        self,
        user_id: UserId,
        provider: IdentityProvider,
        provider_user_id: str,
        provider_email: str | None,
        now: datetime,
    ) -> FederatedIdentity:
        identity = FederatedIdentity(
            id=FederatedIdentityId(uuid4()),
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            linked_at=now,
        )
        await self.federated_identities.upsert(identity)
        await self._audit(
            AuditAction.IDENTITY_LINKED, now, actor=user_id, target_type="federated_identity", target_id=str(identity.id)
        )
        return identity

    async def ensure_federated_identity_linked(
        self,
        user_id: UserId,
        provider: IdentityProvider,
        provider_user_id: str,
        provider_email: str | None,
        now: datetime,
    ) -> FederatedIdentity:
        """Idempotent wrapper around ``link_federated_identity`` — called on every OAuth login
        (``apps.api.auth_deps``), so it must not create a duplicate row or re-emit an
        IDENTITY_LINKED audit entry for a provider identity that's already recorded."""
        existing = await self.federated_identities.get_by_provider(provider, provider_user_id)
        if existing is not None:
            return existing
        return await self.link_federated_identity(user_id, provider, provider_user_id, provider_email, now)

    # -- authentication + brute-force protection -----------------------------------------------

    async def authenticate(
        self,
        email: Email,
        password: str,
        now: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_label: str | None = None,
    ) -> LoginResult:
        user = await self.users.get_by_email(email)

        if user is not None:
            lock_state = await self.account_locks.get(user.id)
            if lock_state is not None and lock_state.locked_until is not None:
                lock_state.locked_until = _ensure_aware(lock_state.locked_until, now)
            if lock_state is not None and lock_state.is_locked(now):
                raise AccountLockedError(lock_state.locked_until)

        if user is None or user.password_hash is None or not self.password_hasher.verify(password, user.password_hash):
            await self._record_failure(email, user, now, ip_address, user_agent)
            raise InvalidCredentialsError("Invalid email or password")

        if not user.can_authenticate():
            raise InvalidCredentialsError("Account is not active")

        await self._clear_failures(user.id)
        user.last_login_at = now
        user.updated_at = now
        await self.users.upsert(user)

        await self.security_events.record(
            SecurityEvent(
                id=SecurityEventId(uuid4()),
                event_type=SecurityEventType.LOGIN_SUCCESS,
                occurred_at=now,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self._audit(AuditAction.USER_LOGIN_SUCCEEDED, now, actor=user.id, target_type="user", target_id=str(user.id))

        session = Session(
            id=SessionId(uuid4()),
            user_id=user.id,
            device_label=device_label,
            ip_address=ip_address,
            user_agent=user_agent,
            risk_level=await self._assess_risk(user.id, ip_address, now),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=30),
        )
        await self.sessions.upsert(session)
        return LoginResult(user=user, session=session)

    async def _record_failure(
        self, email: Email, user: User | None, now: datetime, ip_address: str | None, user_agent: str | None
    ) -> None:
        await self.security_events.record(
            SecurityEvent(
                id=SecurityEventId(uuid4()),
                event_type=SecurityEventType.LOGIN_FAILURE,
                occurred_at=now,
                user_id=user.id if user else None,
                email_attempted=str(email),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        if user is None:
            return

        await self._audit(AuditAction.USER_LOGIN_FAILED, now, actor=None, target_type="user", target_id=str(user.id))

        state = await self.account_locks.get(user.id) or AccountLockState(user_id=user.id)
        state.consecutive_failures += 1
        state.last_failure_at = now
        if state.consecutive_failures >= self.max_consecutive_failures:
            state.locked_until = now + self.lockout_duration
            await self.security_events.record(
                SecurityEvent(
                    id=SecurityEventId(uuid4()),
                    event_type=SecurityEventType.ACCOUNT_LOCKED,
                    occurred_at=now,
                    user_id=user.id,
                    ip_address=ip_address,
                )
            )
            await self._audit(AuditAction.ACCOUNT_LOCKED, now, actor=None, target_type="user", target_id=str(user.id))
        await self.account_locks.upsert(state)

        recent = await self.security_events.list_recent_by_email(str(email), now - self.brute_force_window)
        failures = [e for e in recent if e.event_type is SecurityEventType.LOGIN_FAILURE]
        if len(failures) >= self.brute_force_threshold:
            await self.security_events.record(
                SecurityEvent(
                    id=SecurityEventId(uuid4()),
                    event_type=SecurityEventType.BRUTE_FORCE_DETECTED,
                    occurred_at=now,
                    email_attempted=str(email),
                    ip_address=ip_address,
                    metadata={"failure_count": len(failures)},
                )
            )

    async def _clear_failures(self, user_id: UserId) -> None:
        state = await self.account_locks.get(user_id)
        if state is not None and (state.consecutive_failures or state.locked_until):
            state.consecutive_failures = 0
            state.locked_until = None
            await self.account_locks.upsert(state)

    async def _assess_risk(self, user_id: UserId, ip_address: str | None, now: datetime) -> SessionRiskLevel:
        """New IP/device relative to the user's active sessions is a MEDIUM-risk indicator — a
        heuristic starting point, not a full device-fingerprinting system (out of scope for
        Milestone 6; see docs/roadmap.md for where richer risk scoring lands)."""
        if ip_address is None:
            return SessionRiskLevel.LOW
        active = await self.sessions.list_active_by_user(user_id)
        known_ips = {s.ip_address for s in active if s.ip_address}
        return SessionRiskLevel.MEDIUM if known_ips and ip_address not in known_ips else SessionRiskLevel.LOW

    # -- sessions -------------------------------------------------------------------------------

    async def revoke_session(self, session_id: SessionId, now: datetime, actor: UserId | None = None) -> None:
        session = await self.sessions.get(session_id)
        if session is None or not session.is_active:
            return
        session.revoked_at = now
        await self.sessions.upsert(session)
        await self._audit(
            AuditAction.SESSION_REVOKED, now, actor=actor or session.user_id, target_type="session", target_id=str(session_id)
        )

    async def list_active_sessions(self, user_id: UserId) -> list[Session]:
        return await self.sessions.list_active_by_user(user_id)

    # -- personal access tokens -------------------------------------------------------------------

    async def create_personal_access_token(
        self, user_id: UserId, name: str, scopes: list[str], now: datetime, expires_at: datetime | None = None
    ) -> tuple[PersonalAccessToken, str]:
        raw_token = self.token_hasher.generate()
        token = PersonalAccessToken(
            id=TokenId(uuid4()),
            user_id=user_id,
            name=name,
            token_hash=self.token_hasher.hash(raw_token),
            scopes=scopes,
            created_at=now,
            expires_at=expires_at,
        )
        await self.tokens.upsert(token)
        await self._audit(AuditAction.PAT_CREATED, now, actor=user_id, target_type="pat", target_id=str(token.id))
        return token, raw_token

    async def revoke_personal_access_token(self, token_id: TokenId, now: datetime, actor: UserId) -> None:
        token = await self.tokens.get(token_id)
        if token is None or not token.is_active:
            return
        token.revoked_at = now
        await self.tokens.upsert(token)
        await self._audit(AuditAction.PAT_REVOKED, now, actor=actor, target_type="pat", target_id=str(token_id))

    async def authenticate_with_token(self, raw_token: str, now: datetime) -> User | None:
        token = await self.tokens.get_by_hash(self.token_hasher.hash(raw_token))
        if token is None:
            return None
        if token.expires_at is not None:
            token.expires_at = _ensure_aware(token.expires_at, now)
        if not token.is_active or token.is_expired(now):
            return None
        token.last_used_at = now
        await self.tokens.upsert(token)
        return await self.users.get(token.user_id)

    async def list_personal_access_tokens(self, user_id: UserId) -> list[PersonalAccessToken]:
        return await self.tokens.list_by_user(user_id)

    # -- role management ------------------------------------------------------------------------

    async def change_role(self, user_id: UserId, new_role: Role, now: datetime, actor: UserId) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise ValueError(f"No such user: {user_id}")
        old_role = user.role
        user.role = new_role
        user.updated_at = now
        await self.users.upsert(user)
        await self._audit(
            AuditAction.ROLE_CHANGED,
            now,
            actor=actor,
            target_type="user",
            target_id=str(user_id),
            metadata={"old_role": old_role.value, "new_role": new_role.value},
        )
        return user

    # -- audit ------------------------------------------------------------------------------------

    async def _audit(
        self,
        action: AuditAction,
        now: datetime,
        actor: UserId | None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            id=AuditEventId(uuid4()),
            action=action,
            occurred_at=now,
            actor_user_id=actor,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
        )
        return await self.audit_log.append(entry)
