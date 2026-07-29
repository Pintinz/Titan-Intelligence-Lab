"""Prediction API — Milestone 9 (docs/api_specification.md `/api/v1/predictions`). Core
resource surface: generate-or-reuse a cached prediction, fetch one by id, list a market's
predictions, and the two human-approval Admin Actions that gate a below-threshold DRAFT
prediction into PUBLISHED or VOIDED (Part 6 "Admin Actions": Approve/Reject).

History/Comparison/Statistics/Monitoring endpoints live in a separate router
(Milestone 9 task #144) — this one is the prediction resource itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_prediction_cache_service, get_session
from modules.features.domain.value_objects import EntityType
from modules.identity.domain.entities import User
from modules.predictions.application.prediction_cache_service import (
    InvalidPredictionStatusTransitionError,
    MarketNotFoundError,
)
from modules.predictions.application.prediction_context_builder import (
    MarketNotInProductionError,
    NoChampionModelError,
)
from modules.predictions.domain.entities import Prediction
from modules.predictions.domain.value_objects import MarketId, PredictionId, PredictionStatus

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


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


def _parse_prediction_id(value: str) -> PredictionId:
    try:
        return PredictionId(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid prediction_id: {value}") from None


def _parse_status(value: str | None) -> PredictionStatus | None:
    if value is None:
        return None
    try:
        return PredictionStatus(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unrecognized status '{value}'") from None


def _serialize_prediction(prediction: Prediction) -> dict:
    confidence = prediction.confidence
    explanation = prediction.explanation
    return {
        "id": str(prediction.id),
        "market_id": str(prediction.market_id),
        "model_id": str(prediction.model_id),
        "subject_ref": prediction.subject_ref,
        "value": prediction.value,
        "probability": prediction.probability,
        "confidence": {
            "feature_quality": confidence.feature_quality,
            "feature_freshness": confidence.feature_freshness,
            "historical_accuracy": confidence.historical_accuracy,
            "knowledge_graph_completeness": confidence.knowledge_graph_completeness,
            "news_reliability": confidence.news_reliability,
            "community_reliability": confidence.community_reliability,
            "data_completeness": confidence.data_completeness,
            "model_reliability": confidence.model_reliability,
            "prediction_stability": confidence.prediction_stability,
            "composite": confidence.composite,
        },
        "explanation": {
            "top_positive_features": [list(pair) for pair in explanation.top_positive_features],
            "top_negative_features": [list(pair) for pair in explanation.top_negative_features],
            "feature_importance": explanation.feature_importance,
            "knowledge_graph_evidence": list(explanation.knowledge_graph_evidence),
            "news_contribution": list(explanation.news_contribution),
            "community_contribution": list(explanation.community_contribution),
            "ai_explanation": explanation.ai_explanation,
        },
        "feature_snapshot": prediction.feature_snapshot,
        "model_version": prediction.model_version,
        "status": prediction.status.value,
        "generated_at": prediction.generated_at.isoformat() if prediction.generated_at else None,
        "data_freshness": prediction.data_freshness.isoformat() if prediction.data_freshness else None,
    }


class GeneratePredictionBody(BaseModel):
    market_key: str
    entity_type: str
    entity_id: str
    subject_ref: str


class ReviewPredictionBody(BaseModel):
    reason: str | None = None


@router.post("/generate")
async def generate_prediction(
    body: GeneratePredictionBody,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_prediction_cache_service(session)
    try:
        prediction = await service.get_or_generate(
            body.market_key, _parse_entity_type(body.entity_type), body.entity_id, body.subject_ref, _now(),
            actor=str(user.id),
        )
    except MarketNotFoundError:
        raise HTTPException(status_code=404, detail="market not found") from None
    except MarketNotInProductionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except NoChampionModelError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_prediction(prediction))


@router.get("/{prediction_id}")
async def get_prediction(
    prediction_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_prediction_cache_service(session)
    prediction = await service.predictions.get(_parse_prediction_id(prediction_id))
    if prediction is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    return envelope(data=_serialize_prediction(prediction))


@router.get("")
async def list_predictions_for_market(
    market_id: str = Query(...),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    service = build_prediction_cache_service(session)
    results = await service.predictions.list_by_market(
        _parse_market_id(market_id), status=_parse_status(status), limit=limit
    )
    return envelope(data=[_serialize_prediction(p) for p in results], meta={"limit": limit, "count": len(results)})


@router.post("/{prediction_id}/approve")
async def approve_prediction(
    prediction_id: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    service = build_prediction_cache_service(session)
    prediction = await service.predictions.get(_parse_prediction_id(prediction_id))
    if prediction is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    try:
        approved = await service.approve(prediction, actor=str(user.id), now=_now())
    except InvalidPredictionStatusTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_prediction(approved))


@router.post("/{prediction_id}/reject")
async def reject_prediction(
    prediction_id: str,
    body: ReviewPredictionBody,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_prediction_cache_service(session)
    prediction = await service.predictions.get(_parse_prediction_id(prediction_id))
    if prediction is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    try:
        rejected = await service.reject(prediction, actor=str(user.id), now=_now(), reason=body.reason or "")
    except InvalidPredictionStatusTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return envelope(data=_serialize_prediction(rejected))
