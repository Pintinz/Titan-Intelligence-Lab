"""Alerts API — real-triggered in-app notifications for watched matches/teams/predictions.

Read/mark-read only: alerts are never created directly by a client, only emitted server-side by
AlertService.notify_watchers when a real trigger fires (fixture status transition, prediction
republish) — see entity_reconciliation_service.reconcile_fixture and
prediction_cache_service._persist_new_version.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_alert_service, get_session
from modules.alerts.application.alert_service import AlertEventNotFoundError, NotAlertEventOwnerError
from modules.alerts.domain.entities import AlertEvent
from modules.alerts.domain.value_objects import AlertEventId
from modules.identity.domain.entities import User

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_event_id(value: str) -> AlertEventId:
    try:
        return AlertEventId(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid alert event id: {value}") from None


def _serialize(event: AlertEvent) -> dict:
    return {
        "id": str(event.id),
        "alert_type": event.alert_type.value,
        "entity_type": event.entity_type.value,
        "entity_ref": event.entity_ref,
        "title": event.title,
        "body": event.body,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "read_at": event.read_at.isoformat() if event.read_at else None,
    }


@router.get("")
async def list_alerts(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_alert_service(session)
    events = await service.list_for_user(user.id, unread_only, limit)
    return envelope([_serialize(e) for e in events])


@router.get("/unread-count")
async def unread_count(session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)):
    service = build_alert_service(session)
    count = await service.unread_count(user.id)
    return envelope({"count": count})


@router.post("/{event_id}/read")
async def mark_read(
    event_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    parsed_id = _parse_event_id(event_id)
    service = build_alert_service(session)
    try:
        await service.mark_read(user.id, parsed_id, _now())
    except AlertEventNotFoundError:
        raise HTTPException(status_code=404, detail="alert not found") from None
    except NotAlertEventOwnerError:
        raise HTTPException(status_code=404, detail="alert not found") from None
    return envelope({"read": True})
