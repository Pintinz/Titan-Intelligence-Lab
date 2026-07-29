"""Webhook Infrastructure endpoints — endpoint registration, delivery history (Milestone 6,
docs/api_specification.md). No real payment/integration provider dispatches through this yet;
these endpoints manage registration + the delivery/retry ledger.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_webhook_service, get_session
from modules.identity.domain.entities import User
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
    payload: RegisterEndpointRequest, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_webhook_service(session)
    endpoint, raw_secret = await service.register_endpoint(
        payload.organization_id, payload.url, payload.subscribed_events, _now()
    )
    return envelope({**_serialize_endpoint(endpoint), "signing_secret": raw_secret})


@router.get("/organizations/{organization_id}/endpoints")
async def list_endpoints(
    organization_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_webhook_service(session)
    endpoints = await service.endpoints.list_by_organization(organization_id)
    return envelope([_serialize_endpoint(e) for e in endpoints])


@router.post("/endpoints/{endpoint_id}/rotate-secret")
async def rotate_secret(
    endpoint_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_webhook_service(session)
    try:
        endpoint, raw_secret = await service.rotate_secret(WebhookEndpointId(_parse_uuid(endpoint_id)), _now())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return envelope({**_serialize_endpoint(endpoint), "signing_secret": raw_secret})


@router.delete("/endpoints/{endpoint_id}")
async def deactivate_endpoint(
    endpoint_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_webhook_service(session)
    await service.deactivate_endpoint(WebhookEndpointId(_parse_uuid(endpoint_id)))
    return envelope({"deactivated": True})


@router.get("/endpoints/{endpoint_id}/deliveries")
async def list_deliveries(
    endpoint_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_webhook_service(session)
    deliveries = await service.deliveries.list_by_endpoint(WebhookEndpointId(_parse_uuid(endpoint_id)))
    return envelope([_serialize_delivery(d) for d in deliveries])
