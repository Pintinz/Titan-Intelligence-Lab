"""Shared "test this provider's connection and record the result" orchestration (Milestone
11B) — the one place both the Operations Center's manual "Test Connection"/"Refresh" buttons
(apps/api/main.py) and the Celery beat health-check job (infrastructure/celery/tasks.py) go
through, so the two callers can never drift into different classification or recording logic.
"""

from __future__ import annotations

from datetime import datetime

from modules.admin.application.provider_management_service import (
    ProviderManagementService,
    ProviderNotFoundError,
    normalize_credential_label,
)
from modules.admin.application.health_intelligence_engine import HealthIntelligenceEngine
from modules.admin.domain.value_objects import ProviderId
from modules.admin.infrastructure.connection_tester import (
    ConnectionTestResult,
    ConnectionTestStatus,
    test_connection,
    test_oauth2_client_credentials,
)


def _extract_capability_note(raw_body: dict | None) -> str | None:
    """Best-effort, provider-shape-specific capability read from a connection test's raw JSON
    body — deliberately kept out of connection_tester.py so that module stays provider-agnostic
    (its own docstring's stated contract). Currently recognizes API-SPORTS' `/status` shape
    (`response.subscription.plan`/`.end`), the only provider family this platform integrates
    today (docs/architecture.md §5). Returns None for any other/unrecognized shape rather than
    guessing — a missing note means "nothing detected," never "no capability."
    """
    if not raw_body:
        return None
    subscription = (raw_body.get("response") or {}).get("subscription") if isinstance(raw_body.get("response"), dict) else None
    if not subscription:
        return None
    plan = subscription.get("plan")
    if not plan:
        return None
    end = subscription.get("end")
    note = f"{plan} plan"
    if end:
        note += f" (active until {end.split('T')[0]})" if isinstance(end, str) else f" (active until {end})"
    if str(plan).strip().lower() == "free":
        note += " — historical data only on API-SPORTS free tier, typically 2+ seasons behind current"
    return note


async def check_provider_connection(
    service: ProviderManagementService,
    engine: HealthIntelligenceEngine,
    provider_id: ProviderId,
    now: datetime,
) -> ConnectionTestResult:
    provider = await service.providers.get(provider_id)
    if provider is None:
        raise ProviderNotFoundError(str(provider_id))

    usable = await service.usable_credentials(provider_id)

    if provider.auth_type == "oauth2_client_credentials":
        # Two paired credential values, not one — picked by label rather than "the first active
        # credential" (that convention only makes sense for the single-value auth types below).
        client_id_cred = next((c for c in usable if normalize_credential_label(c.label) == "client_id"), None)
        client_secret_cred = next((c for c in usable if normalize_credential_label(c.label) == "client_secret"), None)
        client_id = await service.reveal_plaintext(client_id_cred.id) if client_id_cred else None
        client_secret = await service.reveal_plaintext(client_secret_cred.id) if client_secret_cred else None
        result = await test_oauth2_client_credentials(
            token_url=provider.base_url,
            client_id=client_id,
            client_secret=client_secret,
            timeout_seconds=provider.timeout_seconds,
        )
    else:
        plaintext = await service.reveal_plaintext(usable[0].id) if usable else None
        result = await test_connection(
            base_url=provider.base_url,
            auth_type=provider.auth_type,
            credential=plaintext,
            header_name=provider.auth_header_name,
            timeout_seconds=provider.timeout_seconds,
        )
    if result.status is not ConnectionTestStatus.NOT_CONFIGURED:
        await engine.record_check(provider_id, now, result.success, latency_ms=result.latency_ms, message=result.message)

    note = _extract_capability_note(result.raw_body)
    if note is not None:
        provider.capability_note = note
        provider.capability_checked_at = now
        await service.providers.upsert(provider)

    return result
