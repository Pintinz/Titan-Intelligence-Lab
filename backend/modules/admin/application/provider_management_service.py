"""Provider Management Service — the single place providers are registered, activated, and
credentialed from (docs/admin_center.md §2). The future Admin UI (Milestone 15) calls exactly
these methods; it does not talk to repositories or the vault directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from modules.admin.domain.entities import ProviderCredential, ProviderDefinition
from modules.admin.domain.value_objects import (
    CredentialId,
    ProviderCategory,
    ProviderId,
    ProviderStatus,
)
from modules.admin.ports.repositories import CredentialRepositoryPort, ProviderRepositoryPort
from modules.admin.ports.vault import CredentialVaultPort


class ProviderAlreadyRegisteredError(ValueError):
    pass


class ProviderNotFoundError(KeyError):
    pass


@dataclass
class ProviderManagementService:
    providers: ProviderRepositoryPort
    credentials: CredentialRepositoryPort
    vault: CredentialVaultPort

    async def register_provider(
        self,
        key: str,
        name: str,
        category: ProviderCategory,
        *,
        priority: int = 100,
        daily_quota_limit: int | None = None,
        monthly_quota_limit: int | None = None,
    ) -> ProviderDefinition:
        if await self.providers.get_by_key(key) is not None:
            raise ProviderAlreadyRegisteredError(f"provider '{key}' is already registered")
        provider = ProviderDefinition(
            id=ProviderId(uuid.uuid4()),
            key=key,
            name=name,
            category=category,
            status=ProviderStatus.INACTIVE,
            priority=priority,
            daily_quota_limit=daily_quota_limit,
            monthly_quota_limit=monthly_quota_limit,
        )
        return await self.providers.upsert(provider)

    async def _require_provider(self, provider_id: ProviderId) -> ProviderDefinition:
        provider = await self.providers.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(str(provider_id))
        return provider

    async def activate(self, provider_id: ProviderId) -> ProviderDefinition:
        provider = await self._require_provider(provider_id)
        provider.status = ProviderStatus.ACTIVE
        return await self.providers.upsert(provider)

    async def deactivate(self, provider_id: ProviderId) -> ProviderDefinition:
        provider = await self._require_provider(provider_id)
        provider.status = ProviderStatus.INACTIVE
        return await self.providers.upsert(provider)

    async def set_maintenance(self, provider_id: ProviderId) -> ProviderDefinition:
        provider = await self._require_provider(provider_id)
        provider.status = ProviderStatus.MAINTENANCE
        return await self.providers.upsert(provider)

    async def set_priority(self, provider_id: ProviderId, priority: int) -> ProviderDefinition:
        provider = await self._require_provider(provider_id)
        provider.priority = priority
        return await self.providers.upsert(provider)

    async def add_credential(
        self,
        provider_id: ProviderId,
        label: str,
        plaintext_value: str,
        *,
        now: datetime,
        expires_at: datetime | None = None,
    ) -> ProviderCredential:
        await self._require_provider(provider_id)  # 404s early if the provider doesn't exist
        credential = ProviderCredential(
            id=CredentialId(uuid.uuid4()),
            provider_id=provider_id,
            label=label,
            encrypted_value=self.vault.encrypt(plaintext_value),
            is_active=True,
            created_at=now,
            expires_at=expires_at,
        )
        return await self.credentials.upsert(credential)

    async def rotate_credential(
        self,
        old_credential_id: CredentialId,
        label: str,
        new_plaintext_value: str,
        *,
        now: datetime,
        expires_at: datetime | None = None,
    ) -> ProviderCredential:
        """Deactivates the old key and stores a new one — the old key's usage history is kept
        (not deleted) for audit purposes; only ``is_active`` flips."""
        old = await self.credentials.get(old_credential_id)
        if old is None:
            raise KeyError(str(old_credential_id))
        old.is_active = False
        old.rotated_at = now
        await self.credentials.upsert(old)

        new_credential = ProviderCredential(
            id=CredentialId(uuid.uuid4()),
            provider_id=old.provider_id,
            label=label,
            encrypted_value=self.vault.encrypt(new_plaintext_value),
            is_active=True,
            created_at=now,
            expires_at=expires_at,
        )
        return await self.credentials.upsert(new_credential)

    async def reveal_plaintext(self, credential_id: CredentialId) -> str:
        """Decrypts a credential's value. Only ever called server-side to authenticate an
        outbound provider request — never returned in an API response (docs/security.md §2)."""
        credential = await self.credentials.get(credential_id)
        if credential is None:
            raise KeyError(str(credential_id))
        return self.vault.decrypt(credential.encrypted_value)

    async def usable_credentials(self, provider_id: ProviderId) -> list[ProviderCredential]:
        return [c for c in await self.credentials.list_by_provider(provider_id) if c.is_active]
