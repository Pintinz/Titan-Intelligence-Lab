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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user, require_role, require_scope
from apps.api.composition import (
    build_contextual_reasoning_service,
    build_football_explanation_service,
    build_prediction_cache_service,
    build_prediction_credit_service,
    get_admob_ssv_key_provider,
    get_session,
)
from apps.api.rate_limit import rate_limit_by_user
from modules.features.domain.value_objects import EntityType
from modules.identity.domain.entities import User
from modules.identity.domain.value_objects import Role
from modules.predictions.application.admob_ssv_verifier import AdMobSsvVerificationError, verify_admob_ssv_callback
from modules.predictions.application.prediction_cache_service import (
    InvalidPredictionStatusTransitionError,
    MarketNotFoundError,
)
from modules.predictions.application.feature_market_mapping_service import MissingRequiredFeatureError
from modules.predictions.application.prediction_context_builder import (
    MarketNotInProductionError,
    NoChampionModelError,
)
from modules.predictions.domain.contextual_reasoning import ContextualReview
from modules.predictions.domain.football_explanation import FootballExplanation
from modules.predictions.domain.entities import INITIAL_FREE_PREDICTIONS, REWARDED_AD_CREDIT_GRANT, Prediction, PredictionCreditExhaustedError
from modules.predictions.domain.value_objects import MarketId, PredictionId, PredictionStatus
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository, SqlAlchemyModelRepository

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


def _serialize_contextual_review(review: ContextualReview) -> dict:
    """Gemini Prediction Reasoning Engine — additive nested object, never replacing anything the
    base `_serialize_prediction()` shape already returns. `confidence_score` here is explicitly
    Gemini's confidence in this *contextual assessment*, never an outcome probability — the
    frontend must never render it alongside/instead of `probability` above (see
    `ContextualReviewPanel`'s own docstring)."""
    baseline = review.statistical_baseline
    return {
        "review_status": review.review_status.value,
        "overall_assessment": review.overall_assessment,
        "confidence_level": review.confidence_level.value,
        "confidence_score": review.confidence_score,
        "statistical_baseline": {
            "applicable": baseline.applicable, "available": baseline.available,
            "algorithm": baseline.algorithm, "probabilities": baseline.probabilities, "reason": baseline.reason,
        },
        "contextual_assessment": {
            category: {
                "impact": value.impact.value, "strength": value.strength.value,
                "score": value.score, "reason": value.reason,
            }
            for category, value in review.contextual_assessment.items()
        },
        "supporting_factors": [
            {
                "factor": f.factor, "impact": f.impact.value, "strength": f.strength.value,
                "evidence": f.evidence, "source_ids": list(f.source_ids),
            }
            for f in review.supporting_factors
        ],
        "risk_factors": [
            {
                "factor": f.factor, "impact": f.impact.value, "strength": f.strength.value,
                "evidence": f.evidence, "source_ids": list(f.source_ids),
            }
            for f in review.risk_factors
        ],
        "missing_context": list(review.missing_context),
        "reconsideration": (
            {
                "direction": review.reconsideration.direction.value,
                "material_change": review.reconsideration.material_change,
                "reason": review.reconsideration.reason,
            }
            if review.reconsideration else None
        ),
        "evidence_quality": (
            {
                "overall": review.evidence_quality.overall.value,
                "source_count": review.evidence_quality.source_count,
                "timestamp_valid": review.evidence_quality.timestamp_valid,
                "pre_event_only": review.evidence_quality.pre_event_only,
                "conflicting_information": review.evidence_quality.conflicting_information,
            }
            if review.evidence_quality else None
        ),
        "source_ids": list(review.source_ids),
        "prediction_cutoff": review.prediction_cutoff.isoformat() if review.prediction_cutoff else None,
        "prompt_version": review.prompt_version,
        "generated_at": review.generated_at.isoformat() if review.generated_at else None,
        # "gemini" | "mock" | "cached" | "unavailable" — which narrator actually produced the
        # prose above, disclosed so the frontend never presents a deterministic fallback as if it
        # were a live Gemini read.
        "narration_source": review.narration_source,
    }


def _serialize_football_explanation(explanation: FootballExplanation, prediction: Prediction) -> dict:
    """Sports-Analyst Explainability — additive nested object, never replacing anything the base
    `_serialize_prediction()` shape already returns. `key_reasons`/`counter_signals` carry real
    attribution values TitanIQ computed; `analysis` text within each is Gemini's narration of
    them, never a replacement number.

    `model_id`/`model_version`/`prediction_id` (spec §17: "every attribution must include" these)
    are sourced from `prediction` — the same fixed prediction this explanation was generated for
    — rather than from `explanation.model_id` alone, so `model_version`/`prediction_id` (fields
    the domain `FootballExplanation` doesn't itself carry) are still real, not fabricated."""
    return {
        "model_id": str(prediction.model_id),
        "model_version": prediction.model_version,
        "prediction_id": str(prediction.id),
        "status": explanation.status.value,
        "attribution_method": explanation.attribution_method.value,
        "key_reasons": [
            {
                "rank": r.rank, "feature": r.feature, "football_concept": r.football_concept, "team": r.team,
                "direction": r.direction, "contribution": r.contribution, "evidence": r.evidence,
                "analysis": r.analysis,
            }
            for r in explanation.key_reasons
        ],
        "counter_signals": [
            {
                "feature": c.feature, "football_concept": c.football_concept, "contribution": c.contribution,
                "analysis": c.analysis,
            }
            for c in explanation.counter_signals
        ],
        "context": [
            {"type": c.type, "description": c.description, "model_contribution": c.model_contribution, "role": c.role.value}
            for c in explanation.context
        ],
        "verdict": explanation.verdict,
        "match_profile": explanation.match_profile,
        "confidence_explanation": explanation.confidence_explanation,
        "bottom_line": explanation.bottom_line,
        # Sports-Analyst Explainability Upgrade — additive fields, all default to an empty/None
        # "not applicable/unavailable" shape so no existing consumer of this envelope needs to
        # change (§28: extend backend contracts only where genuinely necessary, never break them).
        "market_analysis": explanation.market_analysis,
        "scoreline_reasoning": (
            {
                "selected_score": explanation.scoreline_reasoning.selected_score,
                "selected_probability": explanation.scoreline_reasoning.selected_probability,
                "expected_home_goals": explanation.scoreline_reasoning.expected_home_goals,
                "expected_away_goals": explanation.scoreline_reasoning.expected_away_goals,
                "alternatives": [
                    {"score": a.score, "probability": a.probability} for a in explanation.scoreline_reasoning.alternatives
                ],
                "home_goal_case": explanation.scoreline_reasoning.home_goal_case,
                "away_goal_case": explanation.scoreline_reasoning.away_goal_case,
                "alternative_comparison": explanation.scoreline_reasoning.alternative_comparison,
            }
            if explanation.scoreline_reasoning is not None else None
        ),
        "injury_evidence": [_serialize_narrated_evidence(e) for e in explanation.injury_evidence],
        "news_evidence": [_serialize_narrated_evidence(e) for e in explanation.news_evidence],
        "lineup_evidence": [_serialize_narrated_evidence(e) for e in explanation.lineup_evidence],
        "context_quality": explanation.context_quality,
        "unavailable_reason": explanation.unavailable_reason,
        "prompt_version": explanation.prompt_version,
        "generated_at": explanation.generated_at.isoformat() if explanation.generated_at else None,
        "narration_source": explanation.narration_source,
    }


def _serialize_narrated_evidence(evidence) -> dict:
    return {
        "source_id": evidence.source_id, "category": evidence.category, "summary": evidence.summary,
        "entity_ref": evidence.entity_ref, "source_name": evidence.source_name,
        "published_at": evidence.published_at.isoformat() if evidence.published_at else None,
        "analysis": evidence.analysis,
    }


def _serialize_prediction(
    prediction: Prediction, contextual_review: ContextualReview | None = None,
    football_explanation: FootballExplanation | None = None,
    model_algorithm: str | None = None, model_framework: str | None = None,
) -> dict:
    confidence = prediction.confidence
    explanation = prediction.explanation
    # Real prod incident audit (2026-08-23): a formula fallback is not the Champion algorithm
    # named by `model_algorithm`/`model_framework` above (those are looked up from `model_id`,
    # which always names the Champion regardless of which predictor actually ran) — reporting the
    # Champion's real algorithm name next to a fallback-computed value would misattribute it as
    # ML-computed. Overridden here only for the one case that's actually misleading; `None`
    # provenance (predictions generated before this field existed) leaves the original lookup
    # untouched rather than guessing.
    if prediction.predictor_provenance == "formula_fallback":
        model_algorithm, model_framework = "statistical_formula", "weighted_formula"
    return {
        "id": str(prediction.id),
        "market_id": str(prediction.market_id),
        "model_id": str(prediction.model_id),
        # Intelligence Center Phase A (§9/§35) — real model architecture for display, e.g.
        # "XGBoost Classifier"/"Poisson Goal Distribution", never inferred from the market name.
        # `None` when the model lookup fails for any reason — the base prediction must never be
        # blocked by this, and the frontend already renders "unknown" honestly rather than guess.
        "model_algorithm": model_algorithm,
        "model_framework": model_framework,
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
        "probability_distribution": prediction.probability_distribution,
        "confidence_interval": list(prediction.confidence_interval) if prediction.confidence_interval else None,
        "expected_error": prediction.expected_error,
        "contextual_review": _serialize_contextual_review(contextual_review) if contextual_review else None,
        "football_explanation": (
            _serialize_football_explanation(football_explanation, prediction) if football_explanation else None
        ),
        # Phase 3 audit fix (spec §27 "API Diagnostics") — a successful response only ever reaches
        # this point once `NoChampionModelError` didn't fire, meaning a real Champion is
        # *registered* for this market — but that is not the same claim as "the Champion's own
        # artifact actually served this prediction" (real prod incident, audited 2026-08-23: a
        # silent formula fallback on artifact-load failure previously had `champion_status`
        # hardcoded to "ACTIVE" regardless). `predictor_provenance` now names which one it was.
        "prediction_status": "READY",
        "champion_status": {"trained_model": "ACTIVE", "formula_fallback": "FALLBACK"}.get(
            prediction.predictor_provenance, "UNKNOWN"
        ),
        "predictor_provenance": prediction.predictor_provenance,
        # Section 31 audit fix (2026-08-23) — mirrors `champion_status`/`predictor_provenance`
        # above: "INSUFFICIENT_PRODUCTION_DATA" (spec's own wording) rather than silently claiming
        # a raw pass-through probability was calibrated. `None` status (predictions generated
        # before this field existed) reports "UNKNOWN", same posture as `champion_status`.
        "calibration_status": {"calibrated": "CALIBRATED", "uncalibrated": "INSUFFICIENT_PRODUCTION_DATA"}.get(
            prediction.calibration_status, "UNKNOWN"
        ),
        "explanation_status": "GENERATED" if explanation.ai_explanation else "UNAVAILABLE",
    }


async def _resolve_model_metadata(session: AsyncSession, prediction: Prediction) -> tuple[str | None, str | None]:
    """Real `algorithm`/`framework` for the model that produced this prediction — a plain lookup
    by `prediction.model_id` (never re-resolves Champion, never re-runs selection), degrading to
    `(None, None)` on any failure so a metadata-display concern can never block or corrupt a
    prediction response that already succeeded."""
    if prediction.model_id is None:
        return None, None
    try:
        model = await SqlAlchemyModelRepository(session=session).get(prediction.model_id)
    except Exception:  # noqa: BLE001
        return None, None
    return (model.algorithm, model.framework) if model is not None else (None, None)


def _blocked_detail(reason_code: str, message: str) -> dict:
    """Structured diagnostic body for a blocked/failed `POST /predictions/generate` (spec §27) —
    passed as `HTTPException.detail`, which FastAPI serializes verbatim (any JSON-serializable
    value, not just a string), so the HTTP status code stays meaningful while the body carries a
    real, parseable reason instead of a bare message string."""
    return {"prediction_status": "BLOCKED", "reason_code": reason_code, "failed_gates": [reason_code], "message": message}


class GeneratePredictionBody(BaseModel):
    market_key: str
    entity_type: str
    entity_id: str
    subject_ref: str
    include_contextual_review: bool = False
    include_football_explanation: bool = False


class ReviewPredictionBody(BaseModel):
    reason: str | None = None


@router.get("/entitlement")
async def get_prediction_entitlement(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Mobile V1 monetization (spec Phase 3). Lazily initializes a first-time caller's balance to
    `INITIAL_FREE_PREDICTIONS` — this is the real "first eligible access" moment, not `/generate`,
    since a user should see "5 remaining" the first time they open the app, before ever
    generating anything."""
    credit_service = build_prediction_credit_service(session)
    credit = await credit_service.get_entitlement(user.id.value, _now())
    return envelope(
        data={
            "available_predictions": credit.available_predictions,
            "initial_free_predictions": INITIAL_FREE_PREDICTIONS,
            "rewarded_predictions_granted": credit.rewarded_predictions_granted,
            "requires_rewarded_ad": credit.available_predictions <= 0,
        }
    )


class AdMobRewardGrantResult(BaseModel):
    granted: bool
    available_predictions: int


@router.get("/credits/admob-ssv-callback")
async def admob_ssv_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Google AdMob's rewarded-ad Server-Side Verification callback (spec Phase 5) — called
    directly by Google's own servers, not by the TitanIQ frontend, so this is deliberately
    unauthenticated by the normal JWT/PAT path. The SSV signature itself (verified against
    Google's published public keys — see `modules.predictions.application.admob_ssv_verifier`)
    is what proves the caller is legitimately Google; there is no other credential to check.

    REQUIRES EXTERNAL CONFIGURATION: this endpoint's full URL must be entered into the AdMob
    console (Rewarded ad unit -> Server-side verification -> Callback URL) before Google will
    ever actually call it — that's a dashboard action outside this codebase. Until then this
    route exists and is correct, but receives zero real traffic.

    `user_id` must be set as the ad request's server-side-verification `userId` custom parameter
    by the native app (see `RewardedAdService` on the frontend) before the ad is shown — Google
    echoes it back here unmodified, inside the signed payload, so it can't be tampered with
    in transit.
    """
    try:
        params = await verify_admob_ssv_callback(request.url.query, get_admob_ssv_key_provider())
    except AdMobSsvVerificationError as exc:
        raise HTTPException(status_code=400, detail=f"SSV verification failed: {exc}") from None

    user_id_raw = params.get("user_id")
    transaction_id = params.get("transaction_id")
    if not user_id_raw or not transaction_id:
        raise HTTPException(status_code=400, detail="SSV callback missing user_id or transaction_id") from None
    try:
        user_id = uuid.UUID(user_id_raw)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"malformed user_id in SSV callback: {user_id_raw!r}") from None

    credit_service = build_prediction_credit_service(session)
    credit, granted = await credit_service.grant_rewarded_ad(
        user_id=user_id, provider_event_id=transaction_id, now=_now()
    )
    # Google expects a 200 with an empty body to consider the callback delivered — no response
    # schema is defined by AdMob for this endpoint, so this return value is for our own
    # tests/observability only, not something Google reads.
    return envelope(data=AdMobRewardGrantResult(granted=granted, available_predictions=credit.available_predictions).model_dump())


@router.post(
    "/generate",
    dependencies=[Depends(rate_limit_by_user("predictions_generate", limit=30, window_seconds=60))],
)
async def generate_prediction(
    body: GeneratePredictionBody,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_scope("predictions:generate")),
):
    # Mobile V1 monetization — consume BEFORE attempting generation, not after. The atomic
    # guarded UPDATE inside `consume_for_generation` is what makes this race-safe under
    # concurrent requests; raising here (uncommitted) is what makes "don't consume a credit for a
    # failed generation" correct for every failure path below — `get_session()` only commits on a
    # clean return, so any exception past this point rolls the consume back too, automatically.
    credit_service = build_prediction_credit_service(session)
    try:
        await credit_service.consume_for_generation(user.id.value, _now())
    except PredictionCreditExhaustedError:
        # `reason_code` (not `code`) matches `_blocked_detail`'s existing field name below, so
        # the frontend's one shared ApiError parser (client.ts) already surfaces this correctly
        # without a second, endpoint-specific parsing branch.
        raise HTTPException(
            status_code=402,
            detail={
                "reason_code": "PREDICTION_CREDIT_REQUIRED",
                "message": "Watch a rewarded video to unlock 2 additional predictions.",
                "available_predictions": 0,
                "reward_amount": REWARDED_AD_CREDIT_GRANT,
            },
        ) from None

    service = build_prediction_cache_service(session)
    try:
        prediction = await service.get_or_generate(
            body.market_key, _parse_entity_type(body.entity_type), body.entity_id, body.subject_ref, _now(),
            actor=str(user.id),
        )
    except MarketNotFoundError:
        raise HTTPException(status_code=404, detail=_blocked_detail("MARKET_NOT_FOUND", "market not found")) from None
    except MarketNotInProductionError as exc:
        raise HTTPException(status_code=409, detail=_blocked_detail("MARKET_NOT_IN_PRODUCTION", str(exc))) from None
    except NoChampionModelError as exc:
        raise HTTPException(status_code=409, detail=_blocked_detail("NO_CHAMPION_MODEL", str(exc))) from None
    except MissingRequiredFeatureError as exc:
        # Milestone 16 — a required feature genuinely has no verified pre-match value yet (most
        # commonly: real point-in-time news/structured-intelligence sync hasn't run or hasn't
        # found qualifying evidence for this fixture). The check itself, and the required/optional
        # feature-market contract behind it, are intentionally NOT weakened here — this only turns
        # an internal implementation detail (an uncaught ValueError) into the same honest
        # "insufficient data" response MarketNotInProductionError/NoChampionModelError already get.
        raise HTTPException(status_code=409, detail=_blocked_detail("MISSING_REQUIRED_FEATURE", str(exc))) from None

    contextual_review: ContextualReview | None = None
    if body.include_contextual_review:
        try:
            market = await SqlAlchemyMarketRepository(session=session).get_by_key(body.market_key)
            if market is not None:
                contextual_review = await build_contextual_reasoning_service(session).review(
                    prediction, market, _now()
                )
        except Exception:  # noqa: BLE001 — an opt-in contextual review must never break the base
            # prediction response; the base quantitative prediction above is already committed.
            contextual_review = None

    football_explanation: FootballExplanation | None = None
    if body.include_football_explanation:
        try:
            market = await SqlAlchemyMarketRepository(session=session).get_by_key(body.market_key)
            if market is not None:
                football_explanation = await build_football_explanation_service(session).explain(
                    prediction, market, _now()
                )
        except Exception:  # noqa: BLE001 — an opt-in explanation must never break the base
            # prediction response; the base quantitative prediction above is already committed.
            football_explanation = None

    model_algorithm, model_framework = await _resolve_model_metadata(session, prediction)
    return envelope(
        data=_serialize_prediction(prediction, contextual_review, football_explanation, model_algorithm, model_framework)
    )


@router.get("/{prediction_id}")
async def get_prediction(
    prediction_id: str, session: AsyncSession = Depends(get_session), _user: User = Depends(get_current_user)
):
    service = build_prediction_cache_service(session)
    prediction = await service.predictions.get(_parse_prediction_id(prediction_id))
    if prediction is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    model_algorithm, model_framework = await _resolve_model_metadata(session, prediction)
    return envelope(data=_serialize_prediction(prediction, model_algorithm=model_algorithm, model_framework=model_framework))


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
    # One model lookup per distinct model_id, not per prediction row — a market's results are
    # overwhelmingly produced by the same one or two Champion versions, so this stays far short of
    # a real N+1 even for the max page size (500).
    metadata_by_model: dict[str, tuple[str | None, str | None]] = {}
    serialized = []
    for p in results:
        model_key = str(p.model_id) if p.model_id else None
        if model_key is not None and model_key not in metadata_by_model:
            metadata_by_model[model_key] = await _resolve_model_metadata(session, p)
        algorithm, framework = metadata_by_model.get(model_key, (None, None))
        serialized.append(_serialize_prediction(p, model_algorithm=algorithm, model_framework=framework))
    return envelope(data=serialized, meta={"limit": limit, "count": len(results)})


@router.post("/{prediction_id}/approve")
async def approve_prediction(
    prediction_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.ADMINISTRATOR)),
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
    user: User = Depends(require_role(Role.ADMINISTRATOR)),
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
