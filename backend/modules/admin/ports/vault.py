"""Credential encryption port. Application/domain code never handles plaintext key material
directly outside an implementation of this port (docs/security.md §2).
"""

from __future__ import annotations

from typing import Protocol


class CredentialVaultPort(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, ciphertext: str) -> str: ...
