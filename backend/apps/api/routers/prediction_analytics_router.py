"""Prediction Confidence / Explainability / History / Monitoring / Statistics / Comparison API —
Milestone 9 (docs/api_specification.md `/api/v1/predictions`). Split from `prediction_router.py`
(the prediction resource itself, task #142) since these are read-only analytical views over
already-generated predictions, not the generate/approve/reject resource lifecycle.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_market_registry_service, build_prediction_cache_service, get_session
from modules.identity.domain.entities import User
from modules.predictions.domain.entities import Prediction
from modules.predictions.domain.value_objects import MarketId, PredictionId, PredictionStatus

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _parse_prediction_id(value: str) -> PredictionId:
    try:
        return PredictionId(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid prediction_id: {value}") from None


def _parse_market_id(value: str | None) -> MarketId | None:
    if value is None:
        return None
    try:
        return MarketId(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid market_id: {value}") from None


async def _require_prediction(service, prediction_id: str) -> Prediction:
    prediction = await service.predictions.get(_parse_prediction_id(prediction_id))
    if prediction is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    return prediction


def _serialize_confidence(prediction: Prediction) -> dict:
    c = prediction.confidence
    return {
        "prediction_id": str(prediction.id),
        "feature_quality": c.feature_quality,
        "feature_freshness": c.feature_freshness,
        "historical_accuracy": c.historical_accuracy,
        "knowledge_graph_completeness": c.knowledge_graph_completeness,
        "news_reliability": c.news_reliability,
        "community_reliability": c.community_reliability,
        "data_completeness": c.data_completeness,
        "model_reliability": c.model_reliability,
        "prediction_stability": c.prediction_stability,
        "composite": c.composite,
    }


def _serialize_explanation(prediction: Prediction) -> dict:
    e = prediction.explanation
    return {
        "prediction_id": str(prediction.id),
        "top_positive_features": [list(pair) for pair in e.top_positive_features],
        "top_negative_features": [list(pair) for pair in e.top_negative_features],
        "feature_importance": e.feature_importance,
        "knowledge_graph_evidence": list(e.knowledge_graph_evidence),
        "news_contribution": list(e.news_contribution),
        "community_contribution": list(e.community_contribution),
        "ai_explanation": e.ai_explanation,
    }


def _serialize_summary(prediction: Prediction) -> dict:
    return {
        "id": str(prediction.id),
        "market_id": str(prediction.market_id),
        "model_id": str(prediction.model_id),
        "subject_ref": prediction.subject_ref,
        "value": prediction.value,
        "probability": prediction.probability,
        "confidence_composite": prediction.confidence.composite,
        "status": prediction.status.value,
        "generated_at": prediction.generated_at.isoformat() if prediction.generated_at else None,
    }


# -- AI Picks ------------------------------------------------------------------------------------


@router.get("/picks")
async def ai_picks(
    limit: int = Query(default=20, ge=1, le=100),
    sport_code: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """A curated, confidence-ranked feed across every sport — reuses
    ``PredictionRepositoryPort.list_recent`` (already powers ``/monitoring/summary`` above)
    rather than adding a new repository query. Only ``PUBLISHED`` predictions qualify: that's
    the state `prediction_router.approve_prediction` gates a below-threshold ``DRAFT`` into
    (docs Part 6 "Admin Actions") — AI Picks must never surface an unreviewed or below-threshold
    prediction as if it were a vetted pick. Sorted by ``confidence.composite`` across a wider
    recent window than ``limit`` so a genuinely high-confidence pick from a quieter market isn't
    pushed out by a flood of lower-confidence predictions on a busier one.
    """
    service = build_prediction_cache_service(session)
    market_service = build_market_registry_service(session)

    recent = await service.predictions.list_recent(limit=max(limit * 10, 500))
    published = [p for p in recent if p.status is PredictionStatus.PUBLISHED]

    market_cache: dict[str, object] = {}
    picks: list[tuple[Prediction, object]] = []
    for prediction in published:
        market_key = str(prediction.market_id)
        if market_key not in market_cache:
            market_cache[market_key] = await market_service.markets.get(prediction.market_id)
        market = market_cache[market_key]
        if market is None:
            continue
        if sport_code is not None and market.sport_code != sport_code:
            continue
        picks.append((prediction, market))

    picks.sort(key=lambda pm: pm[0].confidence.composite, reverse=True)
    top = picks[:limit]

    return envelope(
        data=[
            {
                **_serialize_summary(prediction),
                "market_key": market.market_key,
                "market_name": market.name,
                "sport_code": market.sport_code,
                "evidence_count": (
                    len(prediction.explanation.top_positive_features)
                    + len(prediction.explanation.top_negative_features)
                    + len(prediction.explanation.knowledge_graph_evidence)
                    + len(prediction.explanation.news_contribution)
                    + len(prediction.explanation.community_contribution)
                ),
            }
            for prediction, market in top
        ],
        meta={"count": len(top)},
    )


# -- Confidence ------------------------------------------------------------------------------------


@router.get("/{prediction_id}/confidence")
async def get_prediction_confidence(
    prediction_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_prediction_cache_service(session)
    prediction = await _require_prediction(service, prediction_id)
    return envelope(data=_serialize_confidence(prediction))


# -- Explainability ---------------------------------------------------------------------------------


@router.get("/{prediction_id}/explanation")
async def get_prediction_explanation(
    prediction_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_prediction_cache_service(session)
    prediction = await _require_prediction(service, prediction_id)
    return envelope(data=_serialize_explanation(prediction))


# -- History ------------------------------------------------------------------------------------------


@router.get("/history/{subject_ref}")
async def prediction_history(
    subject_ref: str,
    market_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    service = build_prediction_cache_service(session)
    results = await service.predictions.list_by_subject(subject_ref, market_id=_parse_market_id(market_id))
    return envelope(data=[_serialize_summary(p) for p in results], meta={"count": len(results)})


# -- Monitoring ---------------------------------------------------------------------------------------


@router.get("/monitoring/summary")
async def prediction_monitoring_summary(
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    service = build_prediction_cache_service(session)
    recent = await service.predictions.list_recent(limit=limit)
    by_status: dict[str, int] = {}
    for prediction in recent:
        by_status[prediction.status.value] = by_status.get(prediction.status.value, 0) + 1

    recent_audits = await service.audits.list_recent(limit=limit)
    by_action: dict[str, int] = {}
    for audit in recent_audits:
        by_action[audit.action.value] = by_action.get(audit.action.value, 0) + 1

    return envelope(
        data={
            "sample_size": len(recent),
            "predictions_by_status": by_status,
            "recent_audit_count": len(recent_audits),
            "audits_by_action": by_action,
        }
    )


# -- Statistics ---------------------------------------------------------------------------------------


@router.get("/statistics/{market_key}")
async def prediction_statistics_for_market(
    market_key: str,
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    market_registry = build_market_registry_service(session)
    market = await market_registry.markets.get_by_key(market_key)
    if market is None:
        raise HTTPException(status_code=404, detail="market not found")

    service = build_prediction_cache_service(session)
    predictions = await service.predictions.list_by_market(market.id, limit=limit)

    if not predictions:
        return envelope(
            data={
                "market_key": market_key,
                "sample_size": 0,
                "average_probability": None,
                "average_confidence": None,
                "publish_rate": None,
            }
        )

    published = [p for p in predictions if p.status is PredictionStatus.PUBLISHED]
    return envelope(
        data={
            "market_key": market_key,
            "sample_size": len(predictions),
            "average_probability": sum(p.probability for p in predictions) / len(predictions),
            "average_confidence": sum(p.confidence.composite for p in predictions) / len(predictions),
            "publish_rate": len(published) / len(predictions),
        }
    )


# -- Comparison ---------------------------------------------------------------------------------------


class ComparePredictionsBody(BaseModel):
    prediction_ids: list[str]


@router.post("/compare")
async def compare_predictions(
    body: ComparePredictionsBody,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    if len(body.prediction_ids) < 2:
        raise HTTPException(status_code=422, detail="compare requires at least two prediction_ids")

    service = build_prediction_cache_service(session)
    predictions = [await _require_prediction(service, pid) for pid in body.prediction_ids]
    return envelope(data=[_serialize_summary(p) for p in predictions])
