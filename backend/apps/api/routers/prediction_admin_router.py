"""Admin Control Center extension — Prediction Intelligence Platform (Milestone 9 Part 6).
Exposes `PredictionAdminService`'s dashboards (Market Health, Confidence, Accuracy, Prediction
Drift, Alerts, Export) plus the `regenerate` Admin Action ("Recompute"/"Reprocess"/"Retry") and
`ModelRegistryService.rollback` ("Rollback"). Gated at `Role.ADMINISTRATOR` — unlike the public
prediction/market resource routers, these are operator-only views and actions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import require_role
from apps.api.composition import (
    build_market_registry_service,
    build_model_registry_service,
    build_prediction_admin_service,
    build_prediction_cache_service,
    get_session,
)
from modules.features.domain.value_objects import EntityType
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import Role
from modules.predictions.application.model_registry_service import ModelNotFoundError
from modules.predictions.application.prediction_cache_service import MarketNotFoundError
from modules.predictions.application.prediction_context_builder import MarketNotInProductionError, NoChampionModelError
from modules.predictions.domain.value_objects import MarketId

router = APIRouter(prefix="/api/v1/admin/predictions", tags=["admin", "predictions"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_entity_type(value: str) -> EntityType:
    try:
        return EntityType(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized entity_type '{value}'") from None


def _parse_market_id(value: str) -> MarketId:
    try:
        return MarketId(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid market_id: {value}") from None


async def _require_market_id(session: AsyncSession, market_key: str) -> MarketId:
    market = await build_market_registry_service(session).markets.get_by_key(market_key)
    if market is None:
        raise HTTPException(status_code=404, detail="market not found")
    return market.id


@router.get("/markets/health")
async def market_health(
    session: AsyncSession = Depends(get_session), _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    service = build_prediction_admin_service(session)
    return envelope(data=await service.market_health())


@router.get("/markets/{market_key}/confidence")
async def market_confidence_dashboard(
    market_key: str,
    limit: int = Query(default=200, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    market_id = await _require_market_id(session, market_key)
    service = build_prediction_admin_service(session)
    return envelope(data=await service.confidence_dashboard(market_id, limit=limit))


@router.get("/markets/{market_key}/accuracy")
async def market_accuracy_dashboard(
    market_key: str,
    limit: int = Query(default=200, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    market_id = await _require_market_id(session, market_key)
    service = build_prediction_admin_service(session)
    return envelope(data=await service.accuracy_dashboard(market_id, limit=limit))


@router.get("/markets/{market_key}/drift")
async def market_prediction_drift(
    market_key: str,
    window: int = Query(default=50, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    market_id = await _require_market_id(session, market_key)
    service = build_prediction_admin_service(session)
    return envelope(data=await service.prediction_drift(market_id, window=window))


@router.get("/markets/{market_key}/export")
async def export_market_predictions(
    market_key: str,
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    market_id = await _require_market_id(session, market_key)
    service = build_prediction_admin_service(session)
    exported = await service.export_market_predictions(market_id, limit=limit)
    return envelope(data=exported, meta={"count": len(exported)})


@router.get("/alerts")
async def prediction_alerts(
    session: AsyncSession = Depends(get_session), _user: User = Depends(require_role(Role.ADMINISTRATOR))
):
    service = build_prediction_admin_service(session)
    alerts = await service.alerts()
    return envelope(data=alerts, meta={"count": len(alerts)})


class RegenerateBody(BaseModel):
    market_key: str
    entity_type: str
    entity_id: str
    subject_ref: str


@router.post("/regenerate")
async def regenerate_prediction(
    body: RegenerateBody,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_prediction_cache_service(session)
    try:
        prediction = await service.regenerate(
            body.market_key, _parse_entity_type(body.entity_type), body.entity_id, body.subject_ref, _now(),
            actor=str(user.id),
        )
    except MarketNotFoundError:
        raise HTTPException(status_code=404, detail="market not found") from None
    except MarketNotInProductionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except NoChampionModelError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data={"id": str(prediction.id), "status": prediction.status.value, "probability": prediction.probability})


class RollbackBody(BaseModel):
    market_id: str


@router.post("/models/rollback")
async def rollback_champion_model(
    body: RollbackBody,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_model_registry_service(session)
    try:
        model = await service.rollback(_parse_market_id(body.market_id), now=_now())
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return envelope(data={"id": str(model.id), "model_key": model.model_key, "status": model.status.value})
