import uuid
from datetime import datetime, timezone

import pytest

from modules.admin.domain.entities import (
    ProviderCredential,
    ProviderDefinition,
    ProviderHealthCheck,
    ProviderUsageRecord,
)
from modules.admin.domain.value_objects import (
    CredentialId,
    ProviderCategory,
    ProviderId,
    ProviderStatus,
    QuotaPeriod,
)
from modules.admin.infrastructure.persistence.repositories import (
    SqlAlchemyCredentialRepository,
    SqlAlchemyHealthRepository,
    SqlAlchemyProviderRepository,
    SqlAlchemyUsageRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_provider_repository_round_trip(sqlite_session):
    repo = SqlAlchemyProviderRepository(session=sqlite_session)
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()),
        key="api_football",
        name="API-Football",
        category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE,
        daily_quota_limit=100,
    )

    await repo.upsert(provider)
    await sqlite_session.commit()

    fetched = await repo.get(provider.id)
    by_key = await repo.get_by_key("api_football")
    all_providers = await repo.list_all()

    assert fetched is not None and fetched.daily_quota_limit == 100
    assert by_key is not None and by_key.id == provider.id
    assert len(all_providers) == 1


@pytest.mark.asyncio
async def test_credential_repository_round_trip(sqlite_session):
    provider_repo = SqlAlchemyProviderRepository(session=sqlite_session)
    credential_repo = SqlAlchemyCredentialRepository(session=sqlite_session)

    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="gemini", name="Gemini", category=ProviderCategory.AI
    )
    await provider_repo.upsert(provider)

    credential = ProviderCredential(
        id=CredentialId(uuid.uuid4()),
        provider_id=provider.id,
        label="primary",
        encrypted_value="ciphertext-blob",
        created_at=T0,
    )
    await credential_repo.upsert(credential)
    await sqlite_session.commit()

    fetched = await credential_repo.get(credential.id)
    by_provider = await credential_repo.list_by_provider(provider.id)

    assert fetched is not None and fetched.encrypted_value == "ciphertext-blob"
    assert len(by_provider) == 1

    await credential_repo.delete(credential.id)
    await sqlite_session.commit()
    assert await credential_repo.get(credential.id) is None


@pytest.mark.asyncio
async def test_usage_repository_upsert_accumulates(sqlite_session):
    provider_repo = SqlAlchemyProviderRepository(session=sqlite_session)
    usage_repo = SqlAlchemyUsageRepository(session=sqlite_session)

    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="api_football", name="API-Football", category=ProviderCategory.SPORTS_DATA
    )
    await provider_repo.upsert(provider)

    record = ProviderUsageRecord(provider_id=provider.id, period=QuotaPeriod.DAILY, window_key="2026-07-25")
    record.request_count = 1
    await usage_repo.upsert(record)
    await sqlite_session.commit()

    fetched = await usage_repo.get(provider.id, QuotaPeriod.DAILY, "2026-07-25")
    fetched.request_count += 1
    await usage_repo.upsert(fetched)
    await sqlite_session.commit()

    final = await usage_repo.get(provider.id, QuotaPeriod.DAILY, "2026-07-25")
    assert final.request_count == 2


@pytest.mark.asyncio
async def test_health_repository_records_and_lists_recent(sqlite_session):
    provider_repo = SqlAlchemyProviderRepository(session=sqlite_session)
    health_repo = SqlAlchemyHealthRepository(session=sqlite_session)

    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="api_football", name="API-Football", category=ProviderCategory.SPORTS_DATA
    )
    await provider_repo.upsert(provider)

    await health_repo.record(ProviderHealthCheck(provider_id=provider.id, checked_at=T0, success=True, latency_ms=120.0))
    await sqlite_session.commit()

    recent = await health_repo.list_recent(provider.id)

    assert len(recent) == 1
    assert recent[0].success is True
