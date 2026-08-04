from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from modules.admin.application.connection_check_service import (
    _extract_capability_note,
    check_provider_connection,
)
from modules.admin.application.health_intelligence_engine import HealthIntelligenceEngine
from modules.admin.application.provider_management_service import ProviderManagementService
from modules.admin.domain.entities import ProviderDefinition
from modules.admin.domain.value_objects import ProviderCategory, ProviderId, ProviderStatus

T0 = datetime(2026, 8, 2, tzinfo=timezone.utc)


def test_extract_capability_note_reads_api_sports_free_plan():
    body = {"response": {"subscription": {"plan": "Free", "end": "2027-07-15T00:00:00+00:00", "active": True}}}

    note = _extract_capability_note(body)

    assert note is not None
    assert "Free plan" in note
    assert "2027-07-15" in note
    assert "historical data only" in note.lower()


def test_extract_capability_note_omits_free_tier_caveat_for_paid_plan():
    body = {"response": {"subscription": {"plan": "Pro", "end": "2027-07-15T00:00:00+00:00", "active": True}}}

    note = _extract_capability_note(body)

    assert note is not None
    assert "Pro plan" in note
    assert "historical data only" not in note.lower()


@pytest.mark.parametrize("body", [None, {}, {"response": {}}, {"response": {"subscription": {}}}, {"other": 1}])
def test_extract_capability_note_returns_none_for_unrecognized_shapes(body):
    assert _extract_capability_note(body) is None


@pytest.mark.asyncio
async def test_check_provider_connection_persists_detected_capability_note(
    provider_repo, credential_repo, vault, health_repo, health_state_repo, incident_repo, usage_repo, monkeypatch,
):
    provider = ProviderDefinition(
        id=ProviderId(uuid4()), key="api_football", name="API-Football", category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE, base_url="https://v3.football.api-sports.io/status", auth_type="api_key_header",
        auth_header_name="x-apisports-key",
    )
    await provider_repo.upsert(provider)

    service = ProviderManagementService(providers=provider_repo, credentials=credential_repo, vault=vault)
    engine = HealthIntelligenceEngine(
        health=health_repo, health_state=health_state_repo, incidents=incident_repo, usage=usage_repo,
    )

    def handler(request):
        return httpx.Response(200, json={"response": {"subscription": {"plan": "Free", "end": "2027-07-15T00:00:00+00:00"}}})

    import modules.admin.application.connection_check_service as service_module

    original_test_connection = service_module.test_connection

    async def patched_test_connection(**kwargs):
        kwargs["client"] = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return await original_test_connection(**kwargs)

    monkeypatch.setattr(service_module, "test_connection", patched_test_connection)
    await check_provider_connection(service, engine, provider.id, T0)

    updated = await provider_repo.get(provider.id)
    assert updated.capability_note is not None
    assert "Free plan" in updated.capability_note
    assert updated.capability_checked_at == T0


@pytest.mark.asyncio
async def test_check_provider_connection_leaves_note_untouched_when_shape_unrecognized(
    provider_repo, credential_repo, vault, health_repo, health_state_repo, incident_repo, usage_repo, monkeypatch,
):
    provider = ProviderDefinition(
        id=ProviderId(uuid4()), key="generic", name="Generic Provider", category=ProviderCategory.SPORTS_DATA,
        status=ProviderStatus.ACTIVE, base_url="https://api.example.com/ping", auth_type=None,
    )
    await provider_repo.upsert(provider)

    service = ProviderManagementService(providers=provider_repo, credentials=credential_repo, vault=vault)
    engine = HealthIntelligenceEngine(
        health=health_repo, health_state=health_state_repo, incidents=incident_repo, usage=usage_repo,
    )

    def handler(request):
        return httpx.Response(200, json={"ok": True})

    import modules.admin.application.connection_check_service as service_module

    original_test_connection = service_module.test_connection

    async def patched_test_connection(**kwargs):
        kwargs["client"] = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return await original_test_connection(**kwargs)

    monkeypatch.setattr(service_module, "test_connection", patched_test_connection)
    await check_provider_connection(service, engine, provider.id, T0)

    updated = await provider_repo.get(provider.id)
    assert updated.capability_note is None
    assert updated.capability_checked_at is None
