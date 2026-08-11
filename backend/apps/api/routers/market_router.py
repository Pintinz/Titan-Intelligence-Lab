"""Market & Feature-to-Market Registry API — Milestone 9
(docs/api_specification.md `/api/v1/markets`). Exposes `MarketRegistryService`'s full lifecycle
(Draft -> Review -> Approved -> Production -> Deprecated -> Archived -> Removed) and
`FeatureMarketMappingService`'s registry of which features back which market — the two
registries "Feature Registry"/"Markets" name in Part 5, scoped to the Prediction Intelligence
Platform's own market/mapping resources (the generic Feature *Definition* registry already has
its own routes in apps/api/main.py from Milestone 4).

Every lifecycle mutation (register/submit/approve/reject/promote/deprecate/archive/remove, and
feature-to-market mapping) requires `Role.ADMINISTRATOR` — this is the platform's live market
catalog, not a sandbox any authenticated user should be able to write to. Reads (`list_markets`,
`get_market`, `list_market_features`) stay `get_current_user`-only since the Prediction
Laboratory and other authenticated surfaces legitimately need to browse the catalog.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user, require_role
from apps.api.composition import build_feature_market_mapping_service, build_market_registry_service, get_session
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import Role
from modules.predictions.application.feature_market_mapping_service import (
    FeatureNotApprovedError,
    MappingAlreadyExistsError,
)
from modules.predictions.application.feature_market_mapping_service import MarketNotFoundError as MappingMarketNotFoundError
from modules.predictions.application.market_registry_service import (
    InvalidMarketLifecycleTransitionError,
    MarketAlreadyRegisteredError,
    MarketNotFoundError,
    MarketNotReadyForProductionError,
)
from modules.predictions.domain.entities import FeatureMarketMapping, MarketDefinition
from modules.predictions.domain.value_objects import MarketKind, MarketStatus, TargetType

router = APIRouter(prefix="/api/v1/markets", tags=["markets"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_market_kind(value: str) -> MarketKind:
    try:
        return MarketKind(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized market_kind '{value}'") from None


def _parse_target_type(value: str) -> TargetType:
    try:
        return TargetType(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized target_type '{value}'") from None


def _parse_status(value: str | None) -> MarketStatus | None:
    if value is None:
        return None
    try:
        return MarketStatus(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized status '{value}'") from None


def _serialize_market(market: MarketDefinition) -> dict:
    return {
        "id": str(market.id),
        "market_key": market.market_key,
        "sport_code": market.sport_code,
        "name": market.name,
        "category": market.category,
        "market_kind": market.market_kind.value,
        "target_type": market.target_type.value,
        "description": market.description,
        "min_historical_window_days": market.min_historical_window_days,
        "required_data_quality": market.required_data_quality,
        "explainability_required": market.explainability_required,
        "confidence_threshold": market.confidence_threshold,
        "status": market.status.value,
        "owner": market.owner,
        "version": market.version,
        "created_at": market.created_at.isoformat() if market.created_at else None,
        "updated_at": market.updated_at.isoformat() if market.updated_at else None,
        "reviewed_by": market.reviewed_by,
        "reviewed_at": market.reviewed_at.isoformat() if market.reviewed_at else None,
        "rejection_reason": market.rejection_reason,
        "deprecated_at": market.deprecated_at.isoformat() if market.deprecated_at else None,
    }


def _serialize_mapping(mapping: FeatureMarketMapping) -> dict:
    return {
        "id": str(mapping.id),
        "market_id": str(mapping.market_id),
        "feature_key": mapping.feature_key,
        "is_required": mapping.is_required,
        "importance": mapping.importance,
        "confidence_contribution": mapping.confidence_contribution,
        "weight": mapping.weight,
    }


class RegisterMarketBody(BaseModel):
    market_key: str
    sport_code: str
    name: str
    category: str
    market_kind: str
    target_type: str
    description: str = ""
    min_historical_window_days: int = 0
    required_data_quality: float = 0.0
    explainability_required: bool = True
    confidence_threshold: float = 0.5
    owner: str = ""


class ReviewMarketBody(BaseModel):
    reviewer: str
    reason: str | None = None


class MapFeatureBody(BaseModel):
    feature_key: str
    is_required: bool = True
    importance: float = 0.0
    confidence_contribution: float = 0.0
    weight: float = 1.0


@router.post("")
async def register_market(
    body: RegisterMarketBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_market_registry_service(session)
    try:
        market = await service.register(
            market_key=body.market_key,
            sport_code=body.sport_code,
            name=body.name,
            category=body.category,
            market_kind=_parse_market_kind(body.market_kind),
            target_type=_parse_target_type(body.target_type),
            description=body.description,
            min_historical_window_days=body.min_historical_window_days,
            required_data_quality=body.required_data_quality,
            explainability_required=body.explainability_required,
            confidence_threshold=body.confidence_threshold,
            owner=body.owner,
            now=_now(),
        )
    except MarketAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_market(market))


@router.get("")
async def list_markets(
    sport_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    service = build_market_registry_service(session)
    parsed_status = _parse_status(status)
    if parsed_status is not None:
        results = await service.markets.list_by_status(parsed_status)
        if sport_code is not None:
            results = [m for m in results if m.sport_code == sport_code]
    elif sport_code is not None:
        results = await service.markets.list_by_sport(sport_code)
    else:
        results = await service.markets.list_all()
    return envelope(data=[_serialize_market(m) for m in results], meta={"count": len(results)})


@router.get("/{market_key}")
async def get_market(
    market_key: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_market_registry_service(session)
    market = await service.markets.get_by_key(market_key)
    if market is None:
        raise HTTPException(status_code=404, detail="market not found")
    return envelope(data=_serialize_market(market))


def _handle_market_lifecycle_errors(exc: Exception):
    if isinstance(exc, MarketNotFoundError):
        raise HTTPException(status_code=404, detail="market not found") from None
    if isinstance(exc, (InvalidMarketLifecycleTransitionError, MarketNotReadyForProductionError)):
        raise HTTPException(status_code=409, detail=str(exc)) from None
    raise exc


@router.post("/{market_key}/submit")
async def submit_market_for_review(
    market_key: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_market_registry_service(session)
    try:
        market = await service.submit_for_review(market_key)
    except (MarketNotFoundError, InvalidMarketLifecycleTransitionError) as exc:
        _handle_market_lifecycle_errors(exc)
    return envelope(data=_serialize_market(market))


@router.post("/{market_key}/approve")
async def approve_market(
    market_key: str,
    body: ReviewMarketBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_market_registry_service(session)
    try:
        market = await service.approve(market_key, reviewer=body.reviewer, now=_now())
    except (MarketNotFoundError, InvalidMarketLifecycleTransitionError) as exc:
        _handle_market_lifecycle_errors(exc)
    return envelope(data=_serialize_market(market))


@router.post("/{market_key}/reject")
async def reject_market(
    market_key: str,
    body: ReviewMarketBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_market_registry_service(session)
    try:
        market = await service.reject(market_key, reviewer=body.reviewer, reason=body.reason or "", now=_now())
    except (MarketNotFoundError, InvalidMarketLifecycleTransitionError) as exc:
        _handle_market_lifecycle_errors(exc)
    return envelope(data=_serialize_market(market))


@router.post("/{market_key}/promote")
async def promote_market_to_production(
    market_key: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_market_registry_service(session)
    try:
        market = await service.promote_to_production(market_key, now=_now())
    except (MarketNotFoundError, InvalidMarketLifecycleTransitionError, MarketNotReadyForProductionError) as exc:
        _handle_market_lifecycle_errors(exc)
    return envelope(data=_serialize_market(market))


@router.post("/{market_key}/deprecate")
async def deprecate_market(
    market_key: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_market_registry_service(session)
    try:
        market = await service.deprecate(market_key, now=_now())
    except (MarketNotFoundError, InvalidMarketLifecycleTransitionError) as exc:
        _handle_market_lifecycle_errors(exc)
    return envelope(data=_serialize_market(market))


@router.post("/{market_key}/archive")
async def archive_market(
    market_key: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_market_registry_service(session)
    try:
        market = await service.archive(market_key, now=_now())
    except (MarketNotFoundError, InvalidMarketLifecycleTransitionError) as exc:
        _handle_market_lifecycle_errors(exc)
    return envelope(data=_serialize_market(market))


@router.post("/{market_key}/remove")
async def remove_market(
    market_key: str,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_market_registry_service(session)
    try:
        market = await service.remove(market_key, now=_now())
    except (MarketNotFoundError, InvalidMarketLifecycleTransitionError) as exc:
        _handle_market_lifecycle_errors(exc)
    return envelope(data=_serialize_market(market))


# -- Feature-to-Market Registry -----------------------------------------------------------------


@router.get("/{market_key}/features")
async def list_market_features(
    market_key: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_feature_market_mapping_service(session)
    try:
        mappings = await service.list_for_market(market_key)
    except MappingMarketNotFoundError:
        raise HTTPException(status_code=404, detail="market not found") from None
    return envelope(data=[_serialize_mapping(m) for m in mappings], meta={"count": len(mappings)})


@router.post("/{market_key}/features")
async def map_feature_to_market(
    market_key: str,
    body: MapFeatureBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ADMINISTRATOR)),
):
    service = build_feature_market_mapping_service(session)
    try:
        mapping = await service.map_feature(
            market_key=market_key,
            feature_key=body.feature_key,
            is_required=body.is_required,
            importance=body.importance,
            confidence_contribution=body.confidence_contribution,
            weight=body.weight,
        )
    except MappingMarketNotFoundError:
        raise HTTPException(status_code=404, detail="market not found") from None
    except FeatureNotApprovedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except MappingAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_mapping(mapping))
