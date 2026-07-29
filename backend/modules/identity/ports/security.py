"""Cryptographic/token ports for the Identity module — mock-first pattern (ADR-008): domain and
application code depend only on these Protocols, real adapters (bcrypt, secrets, PyJWT/JWKS)
live in infrastructure and are swapped in only when composition wires a live environment.
"""

from __future__ import annotations

from typing import Protocol


class PasswordHasherPort(Protocol):
    def hash(self, plaintext: str) -> str: ...
    def verify(self, plaintext: str, hashed: str) -> bool: ...


class TokenHasherPort(Protocol):
    """Hashes Personal Access Tokens for storage — same one-way, non-reversible contract as
    ``PasswordHasherPort`` but kept separate since PATs use a fast hash (SHA-256) rather than a
    slow one (bcrypt/argon2): a PAT is high-entropy random data, not a low-entropy user password,
    so it doesn't need work-factor stretching to resist brute force."""

    def hash(self, raw_token: str) -> str: ...
    def generate(self) -> str: ...


class JWTValidatorPort(Protocol):
    """Validates a Supabase Auth-issued JWT against its published JWKS and returns the decoded
    claims. Supabase remains infrastructure-only (docs constitution) — FastAPI never trusts a
    token without validating signature, issuer, audience, and expiry through this port."""

    async def validate(self, token: str) -> dict: ...
