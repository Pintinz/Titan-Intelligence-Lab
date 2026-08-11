"""Webhook Infrastructure endpoints — endpoint registration, delivery history (Milestone 6,
docs/api_specification.md). No real payment/integration provider dispatches through this yet;
these endpoints manage registration + the delivery/retry ledger.

Every endpoint requires the caller to belong to the organization the webhook endpoint is scoped
to (Security Milestone finding H-7) — mirrors `tenancy_router.py`'s own org-role checks, since
`WebhookService` deliberately has no dependency on the tenancy module (hexagonal boundary:
`WebhookEndpoint.organization_id` is a plain `str`, not a tenancy value object), so the
membership check is composed here at the router layer instead of duplicated into the service.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_tenancy_service, build_webhook_service, get_session
from modules.identity.domain.entities import User
from modules.tenancy.application.tenancy_service import TenancyService
from modules.tenancy.domain.value_objects import OrganizationId, OrganizationRole
from modules.webhooks.domain.entities import WebhookDelivery, WebhookEndpoint
from modules.webhooks.domain.value_objects import WebhookEndpointId

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {value}") from None


_ANY_MEMBER = {OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.MEMBER}
_MANAGE_WEBHOOKS = {OrganizationRole.OWNER, OrganizationRole.ADMIN}


async def _require_org_role(
    tenancy_service: TenancyService, organization_id: str, user: User, allowed: set[OrganizationRole]
) -> None:
    membership = await tenancy_service.memberships.get_for_user(OrganizationId(_parse_uuid(organization_id)), user.id)
    if membership is None or membership.role not in allowed:
        raise HTTPException(status_code=403, detail="Not a member of this organization")


def _serialize_endpoint(endpoint: WebhookEndpoint) -> dict:
    return {
        "id": str(endpoint.id),
        "organization_id": endpoint.organization_id,
        "url": endpoint.url,
        "subscribed_events": endpoint.subscribed_events,
        "is_active": endpoint.is_active,
    }


def _serialize_delivery(delivery: WebhookDelivery) -> dict:
    return {
        "id": str(delivery.id),
        "endpoint_id": str(delivery.endpoint_id),
        "event_type": delivery.event_type,
        "status": delivery.status.value,
        "attempt_count": delivery.attempt_count,
        "response_status_code": delivery.response_status_code,
    }


class RegisterEndpointRequest(BaseModel):
    organization_id: str
    url: str
    subscribed_events: list[str] = ["*"]


@router.post("/endpoints")
async def register_endpoint(
    payload: RegisterEndpointRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    await _require_org_role(build_tenancy_service(session), payload.organization_id, user, _MANAGE_WEBHOOKS)
    service = build_webhook_service(session)
    endpoint, raw_secret = await service.register_endpoint(
        payload.organization_id, payload.url, payload.subscribed_events, _now()
    )
    return envelope({**_serialize_endpoint(endpoint), "signing_secret": raw_secret})


@router.get("/organizations/{organization_id}/endpoints")
async def list_endpoints(
    organization_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    await _require_org_role(build_tenancy_service(session), organization_id, user, _ANY_MEMBER)
    service = build_webhook_service(session)
    endpoints = await service.endpoints.list_by_organization(organization_id)
    return envelope([_serialize_endpoint(e) for e in endpoints])


@router.post("/endpoints/{endpoint_id}/rotate-secret")
async def rotate_secret(
    endpoint_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_webhook_service(session)
    endpoint = await service.endpoints.get(WebhookEndpointId(_parse_uuid(endpoint_id)))
    if endpoint is None:
        raise HTTPException(status_code=404, detail="No such webhook endpoint")
    await _require_org_role(build_tenancy_service(session), endpoint.organization_id, user, _MANAGE_WEBHOOKS)
    endpoint, raw_secret = await service.rotate_secret(WebhookEndpointId(_parse_uuid(endpoint_id)), _now())
    return envelope({**_serialize_endpoint(endpoint), "signing_secret": raw_secret})


@router.delete("/endpoints/{endpoint_id}")
async def deactivate_endpoint(
    endpoint_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_webhook_service(session)
    endpoint = await service.endpoints.get(WebhookEndpointId(_parse_uuid(endpoint_id)))
    if endpoint is not None:
        await _require_org_role(build_tenancy_service(session), endpoint.organization_id, user, _MANAGE_WEBHOOKS)
        await service.deactivate_endpoint(WebhookEndpointId(_parse_uuid(endpoint_id)))
    return envelope({"deactivated": True})


@router.get("/endpoints/{endpoint_id}/deliveries")
async def list_deliveries(
    endpoint_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_webhook_service(session)
    endpoint = await service.endpoints.get(WebhookEndpointId(_parse_uuid(endpoint_id)))
    if endpoint is None:
        raise HTTPException(status_code=404, detail="No such webhook endpoint")
    await _require_org_role(build_tenancy_service(session), endpoint.organization_id, user, _ANY_MEMBER)
    deliveries = await service.deliveries.list_by_endpoint(WebhookEndpointId(_parse_uuid(endpoint_id)))
    return envelope([_serialize_delivery(d) for d in deliveries])
