import os
from datetime import datetime, timedelta, timezone

import pytest

from modules.admin.application.provider_management_service import (
    EnvironmentVariableNotSetError,
    ProviderAlreadyRegisteredError,
    ProviderManagementService,
    ProviderNotFoundError,
    mask_credential,
)
from modules.admin.domain.value_objects import ProviderCategory, ProviderStatus

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def test_mask_credential_keeps_last_four():
    assert mask_credential("sk-live-abc123456789A4X9") == "*" * 20 + "A4X9"


def test_mask_credential_short_value_fully_masked():
    assert mask_credential("abc") == "***"


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


@pytest.mark.asyncio
async def test_register_provider_stores_registry_fields(service):
    provider = await service.register_provider(
        "api_football", "API-Football", ProviderCategory.SPORTS_DATA,
        base_url="https://v3.football.api-sports.io", auth_type="api_key_header",
        region="eu", version="v3", environment="production", timeout_seconds=15,
        retry_count=3, retry_delay_seconds=2, created_by="admin-user-id",
    )

    assert provider.base_url == "https://v3.football.api-sports.io"
    assert provider.auth_type == "api_key_header"
    assert provider.timeout_seconds == 15
    assert provider.retry_count == 3
    assert provider.created_by == "admin-user-id"
    assert provider.updated_by == "admin-user-id"


@pytest.mark.asyncio
async def test_update_provider_patches_only_provided_fields(service):
    provider = await service.register_provider("gemini", "Gemini", ProviderCategory.AI, priority=100)

    updated = await service.update_provider(provider.id, name="Gemini 2.0", updated_by="admin-2")

    assert updated.name == "Gemini 2.0"
    assert updated.priority == 100  # untouched
    assert updated.updated_by == "admin-2"


@pytest.mark.asyncio
async def test_update_unknown_provider_raises(service):
    from modules.admin.domain.value_objects import ProviderId
    import uuid

    with pytest.raises(ProviderNotFoundError):
        await service.update_provider(ProviderId(uuid.uuid4()), name="whatever")


@pytest.mark.asyncio
async def test_delete_provider_removes_it(service):
    provider = await service.register_provider("odds_api", "Odds API", ProviderCategory.ODDS)

    await service.delete_provider(provider.id)

    assert await service.providers.get(provider.id) is None


@pytest.mark.asyncio
async def test_delete_unknown_provider_raises(service):
    from modules.admin.domain.value_objects import ProviderId
    import uuid

    with pytest.raises(ProviderNotFoundError):
        await service.delete_provider(ProviderId(uuid.uuid4()))


@pytest.mark.asyncio
async def test_masked_credentials_never_exposes_plaintext(service):
    provider = await service.register_provider("api_football", "API-Football", ProviderCategory.SPORTS_DATA)
    await service.add_credential(provider.id, "primary", "sk-live-abc123456789A4X9", now=T0)

    pairs = await service.masked_credentials(provider.id)

    assert len(pairs) == 1
    credential, masked = pairs[0]
    assert masked == "*" * 20 + "A4X9"
    assert "sk-live" not in masked


@pytest.mark.asyncio
async def test_import_from_env_registers_and_credentials(service, monkeypatch):
    monkeypatch.setenv("TITANIQ_TEST_NEWSAPI_KEY", "sk-newsapi-realvalue1234")

    provider, credential = await service.import_from_env(
        "TITANIQ_TEST_NEWSAPI_KEY", "newsapi", "NewsAPI", ProviderCategory.NEWS,
        now=T0, created_by="admin-user-id",
    )

    assert provider.key == "newsapi"
    assert provider.created_by == "admin-user-id"
    assert await service.reveal_plaintext(credential.id) == "sk-newsapi-realvalue1234"


@pytest.mark.asyncio
async def test_import_from_env_reuses_existing_provider(service, monkeypatch):
    monkeypatch.setenv("TITANIQ_TEST_GNEWS_KEY", "sk-gnews-value")
    existing = await service.register_provider("gnews", "GNews", ProviderCategory.NEWS)

    provider, _credential = await service.import_from_env(
        "TITANIQ_TEST_GNEWS_KEY", "gnews", "GNews", ProviderCategory.NEWS, now=T0,
    )

    assert provider.id == existing.id


@pytest.mark.asyncio
async def test_import_from_env_missing_var_raises(service):
    os.environ.pop("TITANIQ_TEST_UNSET_KEY", None)

    with pytest.raises(EnvironmentVariableNotSetError):
        await service.import_from_env("TITANIQ_TEST_UNSET_KEY", "x", "X", ProviderCategory.GENERAL, now=T0)
