from datetime import datetime, timedelta, timezone

import pytest

from modules.admin.application.provider_management_service import (
    ProviderAlreadyRegisteredError,
    ProviderManagementService,
    ProviderNotFoundError,
)
from modules.admin.domain.value_objects import ProviderCategory, ProviderStatus

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@pytest.fixture
def service(provider_repo, credential_repo, vault):
    return ProviderManagementService(providers=provider_repo, credentials=credential_repo, vault=vault)


@pytest.mark.asyncio
async def test_register_provider_defaults_to_inactive(service):
    provider = await service.register_provider("api_football", "API-Football", ProviderCategory.SPORTS_DATA)

    assert provider.status is ProviderStatus.INACTIVE
    assert provider.key == "api_football"


@pytest.mark.asyncio
async def test_register_duplicate_key_raises(service):
    await service.register_provider("api_football", "API-Football", ProviderCategory.SPORTS_DATA)

    with pytest.raises(ProviderAlreadyRegisteredError):
        await service.register_provider("api_football", "API-Football Again", ProviderCategory.SPORTS_DATA)


@pytest.mark.asyncio
async def test_activate_and_deactivate(service):
    provider = await service.register_provider("gemini", "Gemini", ProviderCategory.AI)

    activated = await service.activate(provider.id)
    assert activated.status is ProviderStatus.ACTIVE

    deactivated = await service.deactivate(provider.id)
    assert deactivated.status is ProviderStatus.INACTIVE


@pytest.mark.asyncio
async def test_activate_unknown_provider_raises(service):
    from modules.admin.domain.value_objects import ProviderId
    import uuid

    with pytest.raises(ProviderNotFoundError):
        await service.activate(ProviderId(uuid.uuid4()))


@pytest.mark.asyncio
async def test_add_credential_and_reveal_round_trip(service):
    provider = await service.register_provider("api_football", "API-Football", ProviderCategory.SPORTS_DATA)

    credential = await service.add_credential(provider.id, "primary", "sk-live-abc123", now=T0)
    revealed = await service.reveal_plaintext(credential.id)

    assert revealed == "sk-live-abc123"
    assert credential.encrypted_value != "sk-live-abc123"


@pytest.mark.asyncio
async def test_rotate_credential_deactivates_old_and_keeps_history(service):
    provider = await service.register_provider("api_football", "API-Football", ProviderCategory.SPORTS_DATA)
    old = await service.add_credential(provider.id, "primary", "sk-old", now=T0)

    new = await service.rotate_credential(old.id, "primary-rotated", "sk-new", now=T0 + timedelta(days=1))

    usable = await service.usable_credentials(provider.id)
    assert len(usable) == 1
    assert usable[0].id == new.id
    assert await service.reveal_plaintext(new.id) == "sk-new"

    old_after = await service.credentials.get(old.id)
    assert old_after.is_active is False
    assert old_after.rotated_at == T0 + timedelta(days=1)


@pytest.mark.asyncio
async def test_usable_credentials_excludes_inactive(service):
    provider = await service.register_provider("api_football", "API-Football", ProviderCategory.SPORTS_DATA)
    await service.add_credential(provider.id, "primary", "sk-old", now=T0)
    only_credential = (await service.usable_credentials(provider.id))[0]
    await service.rotate_credential(only_credential.id, "rotated", "sk-new", now=T0)

    usable = await service.usable_credentials(provider.id)

    assert len(usable) == 1
    assert usable[0].label == "rotated"
