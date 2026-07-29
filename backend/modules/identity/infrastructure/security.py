"""Real adapters for the Identity module's cryptographic ports (docs/security.md).

``BcryptPasswordHasher`` and ``Sha256TokenHasher`` are pure local computation — no external
service call — so unlike provider/Redis adapters they don't need a separate mock for fast
tests; the real adapter *is* the fast, offline-safe implementation (docs/decisions.md ADR-008
still applies to ``SupabaseJWKSValidator``, which does call out over the network).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from functools import lru_cache

import bcrypt
import httpx
import jwt
from jwt import PyJWKClient
from pydantic_settings import BaseSettings, SettingsConfigDict

from modules.identity.ports.security import JWTValidatorPort, PasswordHasherPort, TokenHasherPort


class BcryptPasswordHasher(PasswordHasherPort):
    def __init__(self, rounds: int = 12) -> None:
        self._rounds = rounds

    def hash(self, plaintext: str) -> str:
        return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(self._rounds)).decode()

    def verify(self, plaintext: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plaintext.encode(), hashed.encode())
        except ValueError:
            return False


class Sha256TokenHasher(TokenHasherPort):
    """PATs are high-entropy (32 random bytes, urlsafe-base64 encoded) so a fast one-way hash
    is sufficient — there's no need for bcrypt-style work-factor stretching against a value an
    attacker can't dictionary-attack in the first place."""

    def generate(self) -> str:
        return secrets.token_urlsafe(32)

    def hash(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()


class SupabaseAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TITANIQ_SUPABASE_")

    project_url: str
    jwks_cache_seconds: int = 3600


@lru_cache
def get_supabase_auth_settings() -> SupabaseAuthSettings:
    return SupabaseAuthSettings()  # type: ignore[call-arg]  # raises if TITANIQ_SUPABASE_PROJECT_URL is unset


class JWTValidationError(Exception):
    pass


class SupabaseJWKSValidator(JWTValidatorPort):
    """Validates a Supabase Auth-issued JWT against the project's published JWKS (asymmetric,
    rotating keys) — the modern recommended approach over a static HS256 shared secret
    (docs/security.md §4, docs/decisions.md). The JWKS client caches keys internally and only
    re-fetches on a signing-key-id miss, so steady-state validation makes zero network calls.
    """

    def __init__(self, project_url: str | None = None, audience: str = "authenticated") -> None:
        settings = get_supabase_auth_settings() if project_url is None else None
        self._project_url = (project_url or settings.project_url).rstrip("/")
        self._audience = audience
        self._jwks_client = PyJWKClient(f"{self._project_url}/auth/v1/.well-known/jwks.json")

    async def validate(self, token: str) -> dict:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience=self._audience,
                issuer=f"{self._project_url}/auth/v1",
            )
        except jwt.PyJWTError as exc:
            raise JWTValidationError(str(exc)) from exc
        return claims


class MockJWTValidator(JWTValidatorPort):
    """Deterministic fake for fast offline tests — accepts a pre-registered token -> claims
    mapping instead of doing real signature verification, following the same mock-first
    pattern as ``FakeSportsProvider``/``fakeredis`` elsewhere in the codebase."""

    def __init__(self) -> None:
        self._tokens: dict[str, dict] = {}

    def register(self, token: str, claims: dict) -> None:
        self._tokens[token] = claims

    async def validate(self, token: str) -> dict:
        claims = self._tokens.get(token)
        if claims is None:
            raise JWTValidationError("unknown token")
        if claims.get("exp") and claims["exp"] < time.time():
            raise JWTValidationError("token expired")
        return claims
