"""Fernet-based CredentialVaultPort implementation — AES-128-CBC + HMAC authenticated
symmetric encryption via the `cryptography` package (docs/security.md §2, "encrypted at rest").

TITANIQ_ENCRYPTION_KEY must be a urlsafe-base64-encoded 32-byte key (``Fernet.generate_key()``).
Read from the environment and validated at startup — fail fast, never default to a
hardcoded/generated-on-the-fly key, which would silently make stored secrets unrecoverable
across restarts.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from pydantic_settings import BaseSettings, SettingsConfigDict

from modules.admin.ports.vault import CredentialVaultPort


class VaultSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TITANIQ_")

    encryption_key: str


@lru_cache
def get_vault_settings() -> VaultSettings:
    return VaultSettings()  # type: ignore[call-arg]  # raises if TITANIQ_ENCRYPTION_KEY is unset


class DecryptionError(RuntimeError):
    pass


class FernetCredentialVault(CredentialVaultPort):
    def __init__(self, key: str | None = None) -> None:
        resolved_key = key or get_vault_settings().encryption_key
        self._fernet = Fernet(resolved_key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("credential ciphertext is invalid or was encrypted with a different key") from exc
