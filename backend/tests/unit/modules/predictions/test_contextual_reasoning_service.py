"""Gemini Prediction Reasoning Engine — `ContextualReasoningService.review()` orchestration (spec
Phase 22-23, Part 2i). The absolute rule under test throughout: a failure anywhere in this
pipeline (baseline lookup, evidence gathering, cache, Gemini itself, schema validation) must
degrade to an `INSUFFICIENT_CONTEXT` review, never raise out to the caller — the base quantitative
prediction must never be put at risk by this feature."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.contextual_reasoning_service import ContextualReasoningService
from modules.predictions.application.live_evidence_gatherer import GatheredEvidence
from modules.predictions.domain.contextual_reasoning import (
    EvidenceItem,
    PredictionReviewStatus,
    StatisticalBaseline,
)
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    MarketDefinition,
    Prediction,
)
from modules.predictions.domain.value_objects import (
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    PredictionId,
    PredictionStatus,
    TargetType,
)

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)

_VALID_GEMINI_JSON = json.dumps(
    {
        "prediction_review": {
            "status": "SUPPORTED",
            "overall_assessment": "Evidence agrees with the base prediction.",
            "confidence": {"level": "MEDIUM", "score": 0.6},
        },
        "contextual_assessment": {},
        "supporting_factors": [],
        "risk_factors": [],
        "missing_context": [],
        "prediction_reconsideration": {
            "direction": "SUPPORTS_BASE_PREDICTION", "material_change": False, "reason": "Agrees.",
        },
        "evidence_quality": {
            "overall": "MEDIUM", "source_count": 1, "timestamp_valid": True,
            "pre_event_only": True, "conflicting_information": False,
        },
    }
)


def _market() -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key="football.match_winner", sport_code="football", name="Match Winner",
        category="match_outcome", market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


def _prediction(market: MarketDefinition) -> Prediction:
    confidence = ConfidenceBreakdown(0.8, 0.8, 0.7, 0.6, 0.5, 0.5, 0.8, 0.7, 0.7)
    return Prediction(
        id=PredictionId(uuid4()), market_id=market.id, model_id=ModelId(uuid4()), subject_ref="fixture-1",
        value="HOME_WIN", probability=0.62, confidence=confidence, explanation=ExplanationBundle(),
        feature_snapshot={"football.fixture.expected_home_goals": 1.8}, model_version="v1",
        status=PredictionStatus.PUBLISHED,
    )


@dataclass
class _FakeBaselineProvider:
    baseline: StatisticalBaseline = field(
        default_factory=lambda: StatisticalBaseline(applicable=False, available=False)
    )
    raises: bool = False

    async def get(self, market_id, market_key, features):
        if self.raises:
            raise RuntimeError("baseline lookup failed")
        return self.baseline


@dataclass
class _FakeEvidenceGatherer:
    evidence: GatheredEvidence = field(default_factory=GatheredEvidence)
    raises: bool = False

    async def gather(self, subject_ref, sport_code, prediction_cutoff):
        if self.raises:
            raise RuntimeError("evidence gathering failed")
        return self.evidence


@dataclass
class _FakeTextIntelligence:
    responses: list = field(default_factory=lambda: [_VALID_GEMINI_JSON])
    raises: bool = False
    calls: list = field(default_factory=list)

    async def assess_prediction_context(self, payload):
        self.calls.append(payload)
        if self.raises:
            raise RuntimeError("gemini unavailable")
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index], "gemini"


@dataclass
class _FakeCache:
    store: dict = field(default_factory=dict)
    raises: bool = False

    async def get(self, key):
        if self.raises:
            raise RuntimeError("cache unavailable")
        return self.store.get(key)

    async def set(self, key, value, ttl_seconds):
        if self.raises:
            raise RuntimeError("cache unavailable")
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


@dataclass
class _FakeContextReviewRepo:
    records: list = field(default_factory=list)
    raises: bool = False

    async def record(self, prediction_id, review):
        if self.raises:
            raise RuntimeError("persistence failed")
        self.records.append((prediction_id, review))


@dataclass
class _FakeConsistencyGate:
    passed: bool = True
    reason: str = "BLOCKED_INCONSISTENT_EVIDENCE: model_no_longer_champion"
    calls: list = field(default_factory=list)

    async def check(self, prediction, market, now):
        from modules.predictions.application.prediction_consistency_gate import ConsistencyCheckResult

        self.calls.append((prediction.id, market.id, now))
        if self.passed:
            return ConsistencyCheckResult(passed=True)
        return ConsistencyCheckResult(passed=False, failed_checks=("model_no_longer_champion",))


def _service(*, baseline=None, evidence=None, text_intelligence=None, cache=None, context_reviews=None, consistency_gate=None):
    return ContextualReasoningService(
        baseline_provider=baseline or _FakeBaselineProvider(),
        evidence_gatherer=evidence or _FakeEvidenceGatherer(),
        text_intelligence=text_intelligence or _FakeTextIntelligence(),
        cache=cache or _FakeCache(),
        context_reviews=context_reviews or _FakeContextReviewRepo(),
        consistency_gate=consistency_gate,
    )


@pytest.mark.asyncio
async def test_valid_gemini_response_produces_supported_review_and_persists():
    market = _market()
    prediction = _prediction(market)
    context_reviews = _FakeContextReviewRepo()
    service = _service(context_reviews=context_reviews)

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.SUPPORTED
    assert review.base_selection == "HOME_WIN"
    assert review.base_probability == 0.62
    assert len(context_reviews.records) == 1
    assert context_reviews.records[0][0] == prediction.id


@pytest.mark.asyncio
async def test_gemini_unavailable_degrades_to_insufficient_context_without_raising():
    market = _market()
    prediction = _prediction(market)
    service = _service(text_intelligence=_FakeTextIntelligence(raises=True))

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.INSUFFICIENT_CONTEXT
    assert review.base_probability == 0.62  # base prediction fields still faithfully carried through


@pytest.mark.asyncio
async def test_malformed_json_retries_once_then_degrades_to_insufficient_context():
    market = _market()
    prediction = _prediction(market)
    text_intelligence = _FakeTextIntelligence(responses=["not valid json", "still not valid json"])
    service = _service(text_intelligence=text_intelligence)

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.INSUFFICIENT_CONTEXT
    assert len(text_intelligence.calls) == 2  # one retry, per spec Phase 23


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    market = _market()
    prediction = _prediction(market)
    text_intelligence = _FakeTextIntelligence(responses=["not valid json", _VALID_GEMINI_JSON])
    service = _service(text_intelligence=text_intelligence)

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.SUPPORTED
    assert len(text_intelligence.calls) == 2


@pytest.mark.asyncio
async def test_schema_violating_response_degrades_to_insufficient_context():
    """A response that is valid JSON but violates the strict schema (e.g. a hallucinated field)
    must be treated exactly like malformed JSON — never partially trusted."""
    hallucinated = json.loads(_VALID_GEMINI_JSON)
    hallucinated["official_probability"] = 0.99
    market = _market()
    prediction = _prediction(market)
    text_intelligence = _FakeTextIntelligence(responses=[json.dumps(hallucinated), json.dumps(hallucinated)])
    service = _service(text_intelligence=text_intelligence)

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.INSUFFICIENT_CONTEXT


@pytest.mark.asyncio
async def test_baseline_lookup_failure_does_not_break_review():
    market = _market()
    prediction = _prediction(market)
    service = _service(baseline=_FakeBaselineProvider(raises=True))

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.SUPPORTED
    assert review.statistical_baseline.applicable is False
    assert review.statistical_baseline.available is False


@pytest.mark.asyncio
async def test_evidence_gathering_failure_does_not_break_review():
    market = _market()
    prediction = _prediction(market)
    service = _service(evidence=_FakeEvidenceGatherer(raises=True))

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.SUPPORTED


@pytest.mark.asyncio
async def test_cache_read_failure_falls_back_to_a_fresh_call_not_an_error():
    market = _market()
    prediction = _prediction(market)
    service = _service(cache=_FakeCache(raises=True))

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.SUPPORTED


@pytest.mark.asyncio
async def test_persistence_failure_does_not_lose_an_otherwise_good_review():
    market = _market()
    prediction = _prediction(market)
    service = _service(context_reviews=_FakeContextReviewRepo(raises=True))

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.SUPPORTED


@pytest.mark.asyncio
async def test_cache_hit_avoids_a_second_gemini_call():
    market = _market()
    prediction = _prediction(market)
    text_intelligence = _FakeTextIntelligence()
    cache = _FakeCache()
    service = _service(text_intelligence=text_intelligence, cache=cache)

    await service.review(prediction, market, T0)
    assert len(text_intelligence.calls) == 1

    await service.review(prediction, market, T0)
    assert len(text_intelligence.calls) == 1  # second call served entirely from cache


@pytest.mark.asyncio
async def test_material_context_change_invalidates_the_cache():
    """A different set of accepted evidence source_ids must produce a different cache key — a
    genuinely new injury/news item must not be masked by a stale cached review."""
    market = _market()
    prediction = _prediction(market)
    text_intelligence = _FakeTextIntelligence()
    cache = _FakeCache()
    evidence_v1 = GatheredEvidence(items_by_category={"news": (EvidenceItem(source_id="a", category="news", summary="x"),)})
    evidence_v2 = GatheredEvidence(items_by_category={"news": (EvidenceItem(source_id="b", category="news", summary="y"),)})

    service_v1 = _service(text_intelligence=text_intelligence, cache=cache, evidence=_FakeEvidenceGatherer(evidence=evidence_v1))
    await service_v1.review(prediction, market, T0)
    assert len(text_intelligence.calls) == 1

    service_v2 = _service(text_intelligence=text_intelligence, cache=cache, evidence=_FakeEvidenceGatherer(evidence=evidence_v2))
    await service_v2.review(prediction, market, T0)
    assert len(text_intelligence.calls) == 2  # different context hash — cache miss, fresh call made


@pytest.mark.asyncio
async def test_never_raises_even_when_every_dependency_fails():
    market = _market()
    prediction = _prediction(market)
    service = _service(
        baseline=_FakeBaselineProvider(raises=True), evidence=_FakeEvidenceGatherer(raises=True),
        text_intelligence=_FakeTextIntelligence(raises=True), cache=_FakeCache(raises=True),
        context_reviews=_FakeContextReviewRepo(raises=True),
    )

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.INSUFFICIENT_CONTEXT


@pytest.mark.asyncio
async def test_prediction_cutoff_defaults_to_now_when_not_supplied():
    market = _market()
    prediction = _prediction(market)
    service = _service()

    review = await service.review(prediction, market, T0)

    assert review.prediction_cutoff == T0


# --- Pre-Gemini Prediction-Explanation Consistency Gate (spec §23) ----------------------------


@pytest.mark.asyncio
async def test_consistency_gate_failure_blocks_gemini_and_persists_diagnostic():
    market = _market()
    prediction = _prediction(market)
    gate = _FakeConsistencyGate(passed=False)
    text_intelligence = _FakeTextIntelligence()
    context_reviews = _FakeContextReviewRepo()
    service = _service(consistency_gate=gate, text_intelligence=text_intelligence, context_reviews=context_reviews)

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.INSUFFICIENT_CONTEXT
    assert "BLOCKED_INCONSISTENT_EVIDENCE" in review.overall_assessment
    assert "model_no_longer_champion" in review.overall_assessment
    assert text_intelligence.calls == []  # Gemini never called
    assert len(context_reviews.records) == 1  # the diagnostic is still persisted
    assert context_reviews.records[0][0] == prediction.id


@pytest.mark.asyncio
async def test_consistency_gate_pass_proceeds_to_gemini_as_normal():
    market = _market()
    prediction = _prediction(market)
    gate = _FakeConsistencyGate(passed=True)
    text_intelligence = _FakeTextIntelligence()
    service = _service(consistency_gate=gate, text_intelligence=text_intelligence)

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.SUPPORTED
    assert len(text_intelligence.calls) == 1
    assert gate.calls == [(prediction.id, market.id, T0)]


@pytest.mark.asyncio
async def test_no_consistency_gate_wired_preserves_previous_behavior():
    """Backward compatibility: `consistency_gate=None` (the default) must behave exactly as
    before this feature existed — every existing caller/test that doesn't wire one unaffected."""
    market = _market()
    prediction = _prediction(market)
    service = _service()  # no consistency_gate

    review = await service.review(prediction, market, T0)

    assert review.review_status is PredictionReviewStatus.SUPPORTED
