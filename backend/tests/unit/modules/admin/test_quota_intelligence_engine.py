import uuid
from datetime import datetime, timedelta, timezone

import pytest

from modules.admin.application.quota_intelligence_engine import QuotaIntelligenceEngine
from modules.admin.domain.entities import ProviderCredential, ProviderDefinition
from modules.admin.domain.value_objects import (
    CredentialId,
    ProviderCategory,
    ProviderId,
    ProviderStatus,
    QuotaPeriod,
)

T0 = datetime(2026, 7, 25, 6, 0, tzinfo=timezone.utc)  # 6am — 6 hours into the day


def _provider(daily_limit=100, monthly_limit=1000) -> ProviderDefinition:
    return ProviderDefinition(
        id=ProviderId(uuid.uuid4()),
        key="api_football",
        name="API-Football",
        category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE,
        daily_quota_limit=daily_limit,
        monthly_quota_limit=monthly_limit,
    )


@pytest.mark.asyncio
async def test_record_request_increments_both_daily_and_monthly_windows(provider_repo, usage_repo):
    provider = _provider()
    await provider_repo.upsert(provider)
    engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)

    await engine.record_request(provider.id, T0, success=True)

    daily = await engine.snapshot(provider.id, QuotaPeriod.DAILY, T0)
    monthly = await engine.snapshot(provider.id, QuotaPeriod.MONTHLY, T0)
    assert daily.used == 1
    assert monthly.used == 1


@pytest.mark.asyncio
async def test_snapshot_remaining_reflects_limit(provider_repo, usage_repo):
    provider = _provider(daily_limit=10)
    await provider_repo.upsert(provider)
    engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)

    for _ in range(4):
        await engine.record_request(provider.id, T0, success=True)

    snapshot = await engine.snapshot(provider.id, QuotaPeriod.DAILY, T0)
    assert snapshot.used == 4
    assert snapshot.remaining == 6
    assert snapshot.remaining_ratio == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_unbounded_provider_has_no_remaining_ratio(provider_repo, usage_repo):
    provider = _provider(daily_limit=None, monthly_limit=None)
    await provider_repo.upsert(provider)
    engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)

    snapshot = await engine.snapshot(provider.id, QuotaPeriod.DAILY, T0)

    assert snapshot.remaining_ratio is None


@pytest.mark.asyncio
async def test_should_throttle_low_priority_before_high_priority(provider_repo, usage_repo):
    provider = _provider(daily_limit=100)
    await provider_repo.upsert(provider)
    engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)

    # Consume 92% of quota — above the 10% throttle threshold for low-priority, below full exhaustion.
    for _ in range(92):
        await engine.record_request(provider.id, T0, success=True)

    assert await engine.should_throttle(provider.id, T0, low_priority=True)
    assert not await engine.should_throttle(provider.id, T0, low_priority=False)


@pytest.mark.asyncio
async def test_should_not_throttle_when_quota_healthy(provider_repo, usage_repo):
    provider = _provider(daily_limit=100)
    await provider_repo.upsert(provider)
    engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)

    await engine.record_request(provider.id, T0, success=True)

    assert not await engine.should_throttle(provider.id, T0, low_priority=True)


@pytest.mark.asyncio
async def test_needs_alert_below_threshold(provider_repo, usage_repo):
    provider = _provider(daily_limit=100)
    await provider_repo.upsert(provider)
    engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)

    for _ in range(90):
        await engine.record_request(provider.id, T0, success=True)

    assert await engine.needs_alert(provider.id, T0)


@pytest.mark.asyncio
async def test_predict_daily_exhaustion_hour_projects_linearly(provider_repo, usage_repo):
    provider = _provider(daily_limit=120)
    await provider_repo.upsert(provider)
    engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)

    # 60 requests used by hour 6 -> rate 10/hr -> 60 remaining -> 6 more hours -> exhausted at hour 12.
    for _ in range(60):
        await engine.record_request(provider.id, T0, success=True)

    hour = await engine.predict_daily_exhaustion_hour(provider.id, T0)

    assert hour == pytest.approx(12.0, abs=0.01)


@pytest.mark.asyncio
async def test_predict_daily_exhaustion_hour_none_with_no_usage(provider_repo, usage_repo):
    provider = _provider(daily_limit=120)
    await provider_repo.upsert(provider)
    engine = QuotaIntelligenceEngine(providers=provider_repo, usage=usage_repo)

    assert await engine.predict_daily_exhaustion_hour(provider.id, T0) is None


def test_select_credential_picks_least_used():
    provider_id = ProviderId(uuid.uuid4())
    cred_a = ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider_id, label="a", encrypted_value="x")
    cred_b = ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider_id, label="b", encrypted_value="y")
    usage = {cred_a.id: 50, cred_b.id: 5}

    chosen = QuotaIntelligenceEngine.select_credential([cred_a, cred_b], usage, T0)

    assert chosen is cred_b


def test_select_credential_skips_inactive_and_expired():
    provider_id = ProviderId(uuid.uuid4())
    inactive = ProviderCredential(
        id=CredentialId(uuid.uuid4()), provider_id=provider_id, label="inactive",
        encrypted_value="x", is_active=False,
    )
    expired = ProviderCredential(
        id=CredentialId(uuid.uuid4()), provider_id=provider_id, label="expired",
        encrypted_value="y", expires_at=T0 - timedelta(days=1),
    )
    good = ProviderCredential(id=CredentialId(uuid.uuid4()), provider_id=provider_id, label="good", encrypted_value="z")

    chosen = QuotaIntelligenceEngine.select_credential([inactive, expired, good], {}, T0)

    assert chosen is good


def test_select_credential_returns_none_when_all_unusable():
    provider_id = ProviderId(uuid.uuid4())
    inactive = ProviderCredential(
        id=CredentialId(uuid.uuid4()), provider_id=provider_id, label="inactive",
        encrypted_value="x", is_active=False,
    )

    chosen = QuotaIntelligenceEngine.select_credential([inactive], {}, T0)

    assert chosen is None
