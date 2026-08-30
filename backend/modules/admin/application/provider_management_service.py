"""Provider Management Service — the single place providers are registered, activated, and
credentialed from (docs/admin_center.md §2). The future Admin UI (Milestone 15) calls exactly
these methods; it does not talk to repositories or the vault directly.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from modules.admin.domain.entities import ProviderCredential, ProviderDefinition
from modules.admin.domain.value_objects import (
    CredentialId,
    ProviderCategory,
    ProviderId,
    ProviderStatus,
)
from modules.admin.infrastructure.vault import DecryptionError
from modules.admin.ports.repositories import CredentialRepositoryPort, ProviderRepositoryPort
from modules.admin.ports.vault import CredentialVaultPort


class ProviderAlreadyRegisteredError(ValueError):
    pass


class ProviderNotFoundError(KeyError):
    pass


class EnvironmentVariableNotSetError(ValueError):
    pass


def normalize_credential_label(label: str) -> str:
    """A human typing into a free-text label field will write "Client ID" or "client id", not
    the machine-format "client_id" a lookup-by-label needs — normalize whitespace/hyphens to
    underscores and lowercase so any of those match. Shared by connection testing and any
    payment-provider adapter that needs a specific named credential (e.g. Flutterwave's
    client_id/client_secret/encryption_key/webhook_secret_hash)."""
    return re.sub(r"[\s\-]+", "_", label.strip().lower())


def mask_credential(plaintext: str) -> str:
    """Renders a plaintext secret as ``****...<last 4 chars>`` (docs/security.md §2 example) —
    called only ever server-side, immediately after a controlled ``vault.decrypt``, and the
    plaintext is discarded the instant this returns. Never logged, never the return value of an
    API endpoint on its own."""
    if len(plaintext) <= 4:
        return "*" * len(plaintext)
    return "*" * (len(plaintext) - 4) + plaintext[-4:]


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
        base_url: str | None = None,
        auth_type: str | None = None,
        auth_header_name: str | None = None,
        region: str | None = None,
        version: str | None = None,
        environment: str = "production",
        timeout_seconds: int = 10,
        retry_count: int = 2,
        retry_delay_seconds: int = 1,
        created_by: str | None = None,
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
            base_url=base_url,
            auth_type=auth_type,
            auth_header_name=auth_header_name,
            region=region,
            version=version,
            environment=environment,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            created_by=created_by,
            updated_by=created_by,
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
        # Newest first, enforced here rather than trusted to whatever order the repository
        # happens to return — real incident, 2026-08-29: the SQL repository had no ORDER BY at
        # all, so `usable[0]` (every caller's "the credential to actually use" pick) silently
        # kept resolving to the OLDEST active row. Sorting explicitly at this layer means the
        # right behavior doesn't depend on every repository implementation (SQL, in-memory test
        # double, a future one) independently getting its own ordering right.
        active = [c for c in await self.credentials.list_by_provider(provider_id) if c.is_active]
        return sorted(active, key=lambda c: c.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    async def masked_credentials(self, provider_id: ProviderId) -> list[tuple[ProviderCredential, str]]:
        """Every credential for a provider paired with a masked display value — the only form a
        credential's value is ever allowed to leave this service in (docs/security.md §2).

        Real incident, 2026-08-29: a single undecryptable row (ciphertext encrypted under a
        since-rotated TITANIQ_ENCRYPTION_KEY) previously crashed this whole list — an admin
        couldn't even SEE a provider's credentials to diagnose or clean up the exact row causing
        the problem. Degrades per-row instead: one bad credential is reported as such, never
        hides the rest."""
        credentials = await self.credentials.list_by_provider(provider_id)
        results = []
        for c in credentials:
            try:
                results.append((c, mask_credential(self.vault.decrypt(c.encrypted_value))))
            except DecryptionError:
                results.append((c, "⚠ undecryptable — re-save this credential"))
        return results

    async def update_provider(
        self,
        provider_id: ProviderId,
        *,
        updated_by: str | None = None,
        name: str | None = None,
        priority: int | None = None,
        daily_quota_limit: int | None = None,
        monthly_quota_limit: int | None = None,
        base_url: str | None = None,
        auth_type: str | None = None,
        auth_header_name: str | None = None,
        region: str | None = None,
        version: str | None = None,
        environment: str | None = None,
        timeout_seconds: int | None = None,
        retry_count: int | None = None,
        retry_delay_seconds: int | None = None,
        cache_ttl_seconds: int | None = None,
        poll_interval_seconds: int | None = None,
    ) -> ProviderDefinition:
        """Patch-style update — every argument left at its default is a no-op on that field, so
        callers (the PATCH endpoint) only need to pass what actually changed."""
        provider = await self._require_provider(provider_id)
        if name is not None:
            provider.name = name
        if priority is not None:
            provider.priority = priority
        if daily_quota_limit is not None:
            provider.daily_quota_limit = daily_quota_limit
        if monthly_quota_limit is not None:
            provider.monthly_quota_limit = monthly_quota_limit
        if base_url is not None:
            provider.base_url = base_url
        if auth_type is not None:
            provider.auth_type = auth_type
        if auth_header_name is not None:
            provider.auth_header_name = auth_header_name
        if region is not None:
            provider.region = region
        if version is not None:
            provider.version = version
        if environment is not None:
            provider.environment = environment
        if timeout_seconds is not None:
            provider.timeout_seconds = timeout_seconds
        if retry_count is not None:
            provider.retry_count = retry_count
        if retry_delay_seconds is not None:
            provider.retry_delay_seconds = retry_delay_seconds
        if cache_ttl_seconds is not None:
            provider.cache_ttl_seconds = cache_ttl_seconds
        if poll_interval_seconds is not None:
            provider.poll_interval_seconds = poll_interval_seconds
        if updated_by is not None:
            provider.updated_by = updated_by
        return await self.providers.upsert(provider)

    async def delete_provider(self, provider_id: ProviderId) -> None:
        await self._require_provider(provider_id)  # 404s early rather than silently no-op'ing
        await self.providers.delete(provider_id)

    async def import_from_env(
        self,
        env_var_name: str,
        key: str,
        name: str,
        category: ProviderCategory,
        *,
        now: datetime,
        credential_label: str = "imported-from-env",
        created_by: str | None = None,
    ) -> tuple[ProviderDefinition, ProviderCredential]:
        """One-time migration path for an admin who already has a real key sitting in `.env`
        (docs/admin_center.md — Milestone 11B). Reads the named environment variable exactly
        once, encrypts it into the vault, and registers (or re-credentials) the provider — from
        that point on the DB is the only source of truth; nothing keeps reading the env var on
        subsequent requests. Deliberately NOT a standing runtime fallback: this system's existing
        design (SportsProviderRouter._resolve_adapter) treats "no usable DB credential" as "use
        the mock adapter," not "read a raw env var" — a permanent env-read path would add a
        second, less secure credential path that bypasses the vault entirely.
        """
        plaintext = os.environ.get(env_var_name)
        if not plaintext:
            raise EnvironmentVariableNotSetError(f"environment variable '{env_var_name}' is not set")

        provider = await self.providers.get_by_key(key)
        if provider is None:
            provider = await self.register_provider(key, name, category, created_by=created_by)

        credential = await self.add_credential(provider.id, credential_label, plaintext, now=now)
        return provider, credential
