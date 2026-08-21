"""Gemini Prediction Reasoning Engine — orchestrator (spec Phase 22-23).

Wires `StatisticalBaselineProvider` (Part 1) + `LiveEvidenceGatherer` (cutoff-safe context) +
`GeminiAdapter.assess_prediction_context` (via `TextIntelligenceRouter`, real/mock resolution
reused unchanged) + `GeminiReasoningResponseSchema` (strict validation) into one call:
`review()`. Every failure mode (Gemini unavailable, malformed JSON, schema validation failure)
degrades to a `ContextualReview` with `review_status=INSUFFICIENT_CONTEXT` — this method never
raises out to its caller, matching the absolute rule that a contextual-reasoning failure must
never break the underlying quantitative prediction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from modules.ingestion.ports.cache import SyncCachePort
from modules.intelligence.ports.text_intelligence_provider import TextIntelligenceProviderPort
from modules.predictions.domain.contextual_reasoning import (
    ConfidenceLevel,
    ContextualCategoryAssessment,
    ContextualReview,
    EvidenceQualityReport,
    PredictionReconsideration,
    PredictionReviewStatus,
    RiskFactor,
    StatisticalBaseline,
    SupportingFactor,
)
from modules.predictions.domain.entities import MarketDefinition, Prediction
from modules.predictions.application.live_evidence_gatherer import GatheredEvidence, LiveEvidenceGatherer
from modules.predictions.application.prediction_consistency_gate import PredictionConsistencyGate
from modules.predictions.application.statistical_baseline_provider import StatisticalBaselineProvider
from modules.predictions.infrastructure.gemini_reasoning_schema import GeminiReasoningResponseSchema
from modules.predictions.ports.context_review_repository import ContextReviewRepositoryPort

_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6h — long enough to absorb repeat views of the same fixture,
# short enough that a genuinely new sync (fresh injury/news) is picked up well before kickoff.
_PROMPT_VERSION = "TITANIQ_GEMINI_REASONING_V1"


def _insufficient_context_review(
    market: MarketDefinition, prediction: Prediction, baseline: StatisticalBaseline,
    now: datetime, prediction_cutoff: datetime, reason: str,
) -> ContextualReview:
    return ContextualReview(
        review_status=PredictionReviewStatus.INSUFFICIENT_CONTEXT,
        overall_assessment=reason,
        confidence_level=ConfidenceLevel.VERY_LOW,
        confidence_score=0.0,
        market_key=market.market_key,
        base_selection=prediction.value,
        base_probability=prediction.probability,
        model_version=prediction.model_version,
        statistical_baseline=baseline,
        prediction_cutoff=prediction_cutoff,
        prompt_version=_PROMPT_VERSION,
        generated_at=now,
    )


def _context_hash(evidence: GatheredEvidence) -> str:
    ids = sorted(
        item.source_id
        for items in evidence.items_by_category.values()
        for item in items
    )
    return hashlib.sha256(",".join(ids).encode("utf-8")).hexdigest()[:16]


def _build_payload(
    market: MarketDefinition, prediction: Prediction, baseline: StatisticalBaseline,
    evidence: GatheredEvidence, prediction_cutoff: datetime,
) -> dict:
    return {
        "sport": market.sport_code,
        "market": market.market_key,
        "prediction_cutoff": prediction_cutoff.isoformat(),
        "base_prediction": {
            "market": market.market_key,
            "selection": prediction.value,
            "probability": prediction.probability,
            "probability_distribution": prediction.probability_distribution,
            "model": prediction.model_id and str(prediction.model_id.value),
            "model_version": prediction.model_version,
        },
        "statistical_baseline": {
            "applicable": baseline.applicable,
            "available": baseline.available,
            "algorithm": baseline.algorithm,
            "probabilities": baseline.probabilities,
            "reason": baseline.reason,
        },
        "context": {
            category: [
                {
                    "source_id": item.source_id,
                    "summary": item.summary,
                    "source_name": item.source_name,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                }
                for item in items
            ]
            for category, items in evidence.items_by_category.items()
        },
        "missing_context": list(evidence.missing_context),
    }


def _review_from_validated(
    parsed: GeminiReasoningResponseSchema, market: MarketDefinition, prediction: Prediction,
    baseline: StatisticalBaseline, evidence: GatheredEvidence, now: datetime, prediction_cutoff: datetime,
    narration_source: str = "gemini",
) -> ContextualReview:
    all_source_ids = tuple(
        item.source_id for items in evidence.items_by_category.values() for item in items
    )
    return ContextualReview(
        review_status=parsed.prediction_review.status,
        overall_assessment=parsed.prediction_review.overall_assessment,
        confidence_level=parsed.prediction_review.confidence.level,
        confidence_score=parsed.prediction_review.confidence.score,
        market_key=market.market_key,
        base_selection=prediction.value,
        base_probability=prediction.probability,
        model_version=prediction.model_version,
        statistical_baseline=baseline,
        contextual_assessment={
            category: ContextualCategoryAssessment(
                impact=value.impact, strength=value.strength, score=value.score, reason=value.reason
            )
            for category, value in parsed.contextual_assessment.items()
        },
        supporting_factors=tuple(
            SupportingFactor(f.factor, f.impact, f.strength, f.evidence, f.source_ids)
            for f in parsed.supporting_factors
        ),
        risk_factors=tuple(
            RiskFactor(f.factor, f.impact, f.strength, f.evidence, f.source_ids) for f in parsed.risk_factors
        ),
        missing_context=tuple(parsed.missing_context) or evidence.missing_context,
        reconsideration=PredictionReconsideration(
            direction=parsed.prediction_reconsideration.direction,
            material_change=parsed.prediction_reconsideration.material_change,
            reason=parsed.prediction_reconsideration.reason,
        ),
        evidence_quality=EvidenceQualityReport(
            overall=parsed.evidence_quality.overall,
            source_count=parsed.evidence_quality.source_count,
            timestamp_valid=parsed.evidence_quality.timestamp_valid,
            pre_event_only=parsed.evidence_quality.pre_event_only,
            conflicting_information=parsed.evidence_quality.conflicting_information,
        ),
        source_ids=all_source_ids,
        prediction_cutoff=prediction_cutoff,
        prompt_version=_PROMPT_VERSION,
        generated_at=now,
        narration_source=narration_source,
    )


@dataclass
class ContextualReasoningService:
    baseline_provider: StatisticalBaselineProvider
    evidence_gatherer: LiveEvidenceGatherer
    text_intelligence: TextIntelligenceProviderPort
    cache: SyncCachePort
    context_reviews: ContextReviewRepositoryPort | None = None
    # Pre-Gemini Prediction-Explanation Consistency Gate (spec §23) — optional, matching every
    # other port on this service, but real production wiring provides it (composition.py). When
    # set, checked as the very first step: a failed check skips Gemini entirely and returns
    # (and persists) a `review_status=INSUFFICIENT_CONTEXT` review whose `overall_assessment`
    # names the exact failed checks, rather than narrating a prediction that has drifted out of
    # sync with the market's current state.
    consistency_gate: PredictionConsistencyGate | None = None

    async def review(
        self, prediction: Prediction, market: MarketDefinition, now: datetime,
        prediction_cutoff: datetime | None = None,
    ) -> ContextualReview:
        cutoff = prediction_cutoff or now

        if self.consistency_gate is not None:
            check = await self.consistency_gate.check(prediction, market, now)
            if not check.passed:
                review = _insufficient_context_review(
                    market, prediction, StatisticalBaseline(applicable=False, available=False, reason=check.reason),
                    now, cutoff, check.reason,
                )
                if self.context_reviews is not None:
                    try:
                        await self.context_reviews.record(prediction.id, review)
                    except Exception:  # noqa: BLE001 — persistence failure must not mask the real diagnostic
                        pass
                return review

        try:
            baseline = await self.baseline_provider.get(market.id, market.market_key, dict(prediction.feature_snapshot))
        except Exception:  # noqa: BLE001 — a baseline lookup failure never blocks contextual reasoning
            baseline = StatisticalBaseline(applicable=False, available=False)

        try:
            evidence = await self.evidence_gatherer.gather(prediction.subject_ref, market.sport_code, cutoff)
        except Exception:  # noqa: BLE001 — evidence gathering must never take down the whole review
            evidence = GatheredEvidence()

        cache_key = (
            f"gemini_reasoning:{prediction.subject_ref}:{market.market_key}:{prediction.model_version}:"
            f"{_context_hash(evidence)}:{cutoff.isoformat()}"
        )
        try:
            cached = await self.cache.get(cache_key)
        except Exception:  # noqa: BLE001 — a broken cache backend degrades to "always miss," never an error
            cached = None
        if cached is not None:
            try:
                return _review_from_validated(
                    GeminiReasoningResponseSchema.model_validate(cached), market, prediction, baseline, evidence,
                    now, cutoff, "cached",
                )
            except ValidationError:
                pass  # stale/incompatible cache entry — fall through to a fresh call

        payload = _build_payload(market, prediction, baseline, evidence, cutoff)

        raw = None
        narration_source = "unavailable"
        # TextIntelligenceRouter already retries a transient GeminiRequestError once at the source
        # before falling back to the mock adapter (see _call), so by the time assess_prediction_
        # context returns here it has either succeeded or already exhausted its own retry — this
        # loop's retry is reserved for schema-level failures only, to avoid compounding latency.
        for attempt in range(2):  # one retry with the validation error appended, per spec Phase 23
            try:
                raw, narration_source = await self.text_intelligence.assess_prediction_context(
                    payload if attempt == 0 else {**payload, "_previous_validation_error": last_error}
                )
                parsed = GeminiReasoningResponseSchema.model_validate(json.loads(raw))
                break
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                parsed = None
                continue
            except Exception:  # noqa: BLE001 — Gemini unavailable/timeout/network — never raise out
                parsed = None
                break
        else:
            parsed = None

        if parsed is None:
            return _insufficient_context_review(
                market, prediction, baseline, now, cutoff,
                "Contextual analysis unavailable — Gemini did not return a schema-valid assessment.",
            )

        review = _review_from_validated(parsed, market, prediction, baseline, evidence, now, cutoff, narration_source)

        try:
            await self.cache.set(cache_key, json.loads(raw), _CACHE_TTL_SECONDS)
        except Exception:  # noqa: BLE001 — a cache write failure must not lose an otherwise-good review
            pass

        if self.context_reviews is not None:
            try:
                await self.context_reviews.record(prediction.id, review)
            except Exception:  # noqa: BLE001 — persistence failure must not lose an otherwise-good review
                pass

        return review
