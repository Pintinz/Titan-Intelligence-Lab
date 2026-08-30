"""Sports-Analyst Explainability — orchestrator tests."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from modules.predictions.application.football_explanation_service import (
    FootballExplanationService,
    _build_scoreline_reasoning_seed,
    _market_reasoning_kind,
    _narrate_evidence,
)
from modules.predictions.domain.contextual_reasoning import EvidenceItem
from modules.predictions.application.model_attribution_service import ModelAttributionService
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    MarketDefinition,
    ModelDefinition,
    Prediction,
)
from modules.predictions.domain.football_explanation import AttributionMethod, ExplanationStatus
from modules.predictions.domain.value_objects import (
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    ModelStatus,
    PredictionId,
    PredictionStatus,
    TargetType,
)
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.domain.ml_value_objects import MLAlgorithm

pytestmark = pytest.mark.asyncio


@dataclass
class _InMemoryArtifactStore:
    store: dict = field(default_factory=dict)

    async def save(self, key: str, payload: bytes) -> str:
        self.store[key] = payload
        return key

    async def load(self, ref: str) -> bytes:
        return self.store[ref]


@dataclass
class _NullEvidenceGatherer:
    async def gather(self, subject_ref, sport_code, prediction_cutoff):
        from modules.predictions.application.live_evidence_gatherer import GatheredEvidence
        return GatheredEvidence()


@dataclass
class _StubTextIntelligence:
    response: str | None
    calls: list = field(default_factory=list)

    async def explain_football_prediction(self, payload: dict) -> tuple[str, str]:
        self.calls.append(payload)
        if self.response is None:
            raise RuntimeError("Gemini unavailable")
        return self.response, "gemini"


def _valid_schema_response(key_reasons: list) -> str:
    return json.dumps(
        {
            "verdict": "Test verdict.",
            "key_reason_narration": [{"rank": r["rank"], "analysis": f"narration for {r['feature']}"} for r in key_reasons],
            "counter_signal_narration": [],
            "match_profile": "profile",
            "confidence_explanation": "confidence text",
            "bottom_line": "bottom line",
        }
    )


def _market(market_key="football.both_teams_to_score") -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key=market_key, sport_code="football", name="Test",
        category="totals", market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


def _prediction(model_id, feature_snapshot) -> Prediction:
    return Prediction(
        id=PredictionId(uuid4()), market_id=MarketId(uuid4()), model_id=model_id, subject_ref="fixture-1",
        value="positive", probability=0.7, confidence=ConfidenceBreakdown(*([0.7] * 9)),
        explanation=ExplanationBundle(
            top_positive_features=(("form_diff", 0.4),), top_negative_features=(("form_diff_b", -0.2),),
        ),
        feature_snapshot=feature_snapshot, model_version="1", status=PredictionStatus.PUBLISHED,
        generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


async def _binary_service(model_repo, response):
    rng = np.random.default_rng(4)
    X = rng.normal(size=(60, 2))
    y = (X[:, 0] - X[:, 1] > 0).astype(float)
    estimator = LogisticRegression().fit(X, y)
    adapter = SklearnAdapter(algorithm=MLAlgorithm.LOGISTIC_REGRESSION, target_type=TargetType.CLASSIFICATION)
    adapter.feature_order = ["form_diff", "form_diff_b"]
    adapter._model = estimator
    artifacts = _InMemoryArtifactStore()
    artifact_ref = await artifacts.save("m.bin", adapter.serialize())
    model_def = ModelDefinition(
        id=ModelId(uuid4()), market_id=MarketId(uuid4()), model_key="football.both_teams_to_score.logistic_regression",
        version=1, algorithm="logistic_regression", status=ModelStatus.CHAMPION, framework="sklearn",
        artifact_ref=artifact_ref,
    )
    await model_repo.upsert(model_def)

    from tests.unit.modules.predictions.conftest import InMemoryPredictionOutcomeRepository, InMemoryPredictionRepository

    dataset_builder = _EmptyDatasetBuilder()
    service = FootballExplanationService(
        attribution=ModelAttributionService(),
        evidence_gatherer=_NullEvidenceGatherer(),
        model_loader=ModelLoaderService(artifacts),
        models=model_repo,
        dataset_builder=dataset_builder,
        text_intelligence=_StubTextIntelligence(response=response),
    )
    prediction = _prediction(model_def.id, {"form_diff": 1.5, "form_diff_b": -0.5})
    return service, prediction, model_def


@dataclass
class _EmptyDatasetBuilder:
    """No background samples — exercises the BackgroundSampleRequiredError/heuristic-fallback
    path deliberately for markets without SHAP-eligible history yet, and forces `attribute()` to
    receive an empty background for the linear-coefficient path (which doesn't need one)."""

    async def build(self, market_id, now):
        from modules.predictions.domain.dataset import Dataset, DatasetLineage, DatasetStatistics, DatasetStatus
        from modules.predictions.domain.value_objects import MarketId as _MarketId
        from uuid import uuid4 as _uuid4
        return Dataset(
            id=None, market_id=market_id, version=1, content_hash="x", samples=[],
            statistics=DatasetStatistics(sample_count=0, feature_count=0, positive_rate=None),
            lineage=DatasetLineage(market_id=market_id, source_prediction_ids=(), feature_keys=(), built_at=now),
            status=DatasetStatus.DRAFT,
        )


class TestFootballExplanationService:
    async def test_no_model_id_returns_unavailable(self, model_repo):
        service = FootballExplanationService(
            attribution=ModelAttributionService(), evidence_gatherer=_NullEvidenceGatherer(),
            model_loader=ModelLoaderService(_InMemoryArtifactStore()), models=model_repo,
            dataset_builder=_EmptyDatasetBuilder(), text_intelligence=_StubTextIntelligence(response=None),
        )
        prediction = _prediction(None, {})
        market = _market()

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is ExplanationStatus.UNAVAILABLE
        assert result.unavailable_reason

    async def test_binary_model_produces_available_explanation(self, model_repo):
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_schema_response(key_reasons_payload))
        market = _market()

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is ExplanationStatus.AVAILABLE
        assert result.attribution_method is AttributionMethod.LINEAR_COEFFICIENT
        assert len(result.key_reasons) > 0
        assert result.key_reasons[0].analysis  # Gemini's narration made it through
        assert result.verdict == "Test verdict."

    async def test_gemini_failure_degrades_to_unavailable_not_raise(self, model_repo):
        service, prediction, model_def = await _binary_service(model_repo, None)
        market = _market()

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status in (ExplanationStatus.UNAVAILABLE, ExplanationStatus.VALIDATION_FAILED)
        # real attribution was still computed even though narration failed
        assert len(result.key_reasons) > 0

    async def test_gemini_malformed_json_degrades_gracefully(self, model_repo):
        service, prediction, model_def = await _binary_service(model_repo, "not valid json{{{")
        market = _market()

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is not ExplanationStatus.AVAILABLE

    async def test_never_raises_out_to_caller(self, model_repo):
        """Even a completely broken model artifact must degrade to UNAVAILABLE, never raise."""
        service = FootballExplanationService(
            attribution=ModelAttributionService(), evidence_gatherer=_NullEvidenceGatherer(),
            model_loader=ModelLoaderService(_InMemoryArtifactStore()), models=model_repo,
            dataset_builder=_EmptyDatasetBuilder(), text_intelligence=_StubTextIntelligence(response=None),
        )
        bad_model = ModelDefinition(
            id=ModelId(uuid4()), market_id=MarketId(uuid4()), model_key="broken.model", version=1,
            algorithm="logistic_regression", status=ModelStatus.CHAMPION, framework="sklearn",
            artifact_ref="nonexistent-ref",
        )
        await model_repo.upsert(bad_model)
        prediction = _prediction(bad_model.id, {"a": 1.0})
        market = _market()

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is ExplanationStatus.UNAVAILABLE

    async def test_payload_sent_to_gemini_uses_human_readable_market_and_prediction(self, model_repo):
        """The narration payload must never leak raw backend identifiers ("football.match_winner",
        "AWAY_WIN") into Gemini's prompt — Gemini narrates verbatim whatever it's given, so a raw
        key here becomes user-facing text like "...leans toward AWAY_WIN on football.match_winner"."""
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_schema_response(key_reasons_payload))
        prediction = dataclasses.replace(prediction, value="AWAY_WIN")
        market = _market(market_key="football.match_winner")
        market = dataclasses.replace(market, name="Match Winner")

        await service.explain(prediction, market, datetime.now(timezone.utc))

        sent_payload = service.text_intelligence.calls[0]
        assert sent_payload["market"] == "Match Winner"
        assert sent_payload["prediction"] == "Away Win"

    async def test_consistency_gate_failure_blocks_gemini_and_persists_diagnostic(self, model_repo):
        """Pre-Gemini Prediction-Explanation Consistency Gate (spec §23) — a failed check must
        skip Gemini (and attribution/evidence work) entirely and persist the exact diagnostic."""
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_schema_response(key_reasons_payload))
        market = _market()
        records = []

        class _RecordingExplanationRepo:
            async def record(self, prediction_id, explanation):
                records.append((prediction_id, explanation))

        service.explanations = _RecordingExplanationRepo()
        service.consistency_gate = _FakeConsistencyGate(passed=False)

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is ExplanationStatus.UNAVAILABLE
        assert result.unavailable_reason is not None
        assert "BLOCKED_INCONSISTENT_EVIDENCE" in result.unavailable_reason
        assert service.text_intelligence.calls == []  # Gemini never called
        assert len(records) == 1  # the diagnostic is still persisted
        assert records[0][0] == prediction.id

    async def test_consistency_gate_pass_proceeds_to_gemini_as_normal(self, model_repo):
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_schema_response(key_reasons_payload))
        market = _market()
        service.consistency_gate = _FakeConsistencyGate(passed=True)

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is ExplanationStatus.AVAILABLE
        assert len(service.text_intelligence.calls) == 1

    async def test_no_consistency_gate_wired_preserves_previous_behavior(self, model_repo):
        """Backward compatibility: `consistency_gate=None` (the default) must behave exactly as
        before this feature existed."""
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_schema_response(key_reasons_payload))
        market = _market()

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is ExplanationStatus.AVAILABLE


@dataclass
class _FakeSyncCache:
    """In-memory `SyncCachePort` — real get/set/TTL semantics (TTL not enforced, matching how
    every other fake port in this suite skips wall-clock behavior), so a cache-hit assertion is
    testing the service's own cache-check logic, not a mock's canned return value."""

    store: dict = field(default_factory=dict)

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value, ttl_seconds: int) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class TestExplanationCaching:
    """Real Gemini quota is scarce (free tier: a handful of requests/day/model) — a second
    `explain()` call for the same already-generated prediction with unchanged evidence must not
    burn a fresh Gemini call."""

    async def test_second_call_for_same_prediction_is_served_from_cache(self, model_repo):
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_schema_response(key_reasons_payload))
        service.cache = _FakeSyncCache()
        market = _market()

        first = await service.explain(prediction, market, datetime.now(timezone.utc))
        second = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert len(service.text_intelligence.calls) == 1  # Gemini called once, not twice
        assert first.status is ExplanationStatus.AVAILABLE
        assert second.status is ExplanationStatus.AVAILABLE
        assert second.verdict == first.verdict

    async def test_no_cache_wired_calls_gemini_every_time(self, model_repo):
        """Backward compatibility: `cache=None` (the default) must behave exactly as before this
        feature existed — every call reaches Gemini fresh."""
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_schema_response(key_reasons_payload))
        market = _market()

        await service.explain(prediction, market, datetime.now(timezone.utc))
        await service.explain(prediction, market, datetime.now(timezone.utc))

        assert len(service.text_intelligence.calls) == 2

    async def test_broken_cache_backend_degrades_to_always_miss_not_error(self, model_repo):
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_schema_response(key_reasons_payload))

        class _BrokenCache:
            async def get(self, key):
                raise ConnectionError("cache backend down")

            async def set(self, key, value, ttl_seconds):
                raise ConnectionError("cache backend down")

        service.cache = _BrokenCache()
        market = _market()

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is ExplanationStatus.AVAILABLE  # a broken cache never blocks a good explanation


class TestMarketReasoningKind:
    pytestmark = []  # pure sync functions — override the module-level asyncio mark

    def test_classifies_correct_score(self):
        assert _market_reasoning_kind("football.correct_score") == "correct_score"

    def test_classifies_both_teams_to_score(self):
        assert _market_reasoning_kind("football.both_teams_to_score") == "both_teams_to_score"
        assert _market_reasoning_kind("football.first_half_both_teams_to_score") == "both_teams_to_score"

    def test_classifies_totals(self):
        assert _market_reasoning_kind("football.total_goals_over_under_2_5") == "totals"
        assert _market_reasoning_kind("football.home_team_total_goals") == "totals"

    def test_classifies_match_winner(self):
        assert _market_reasoning_kind("football.match_winner") == "match_winner"

    def test_unknown_market_falls_back_to_generic(self):
        assert _market_reasoning_kind("football.home_clean_sheet") == "generic"


class TestScorelineReasoningSeed:
    pytestmark = []  # pure sync functions — override the module-level asyncio mark

    def test_extracts_real_alternatives_from_distribution(self):
        prediction = _prediction(None, {"football.fixture.expected_home_goals": 1.7, "football.fixture.expected_away_goals": 1.2})
        prediction = dataclasses.replace(
            prediction, value="2-1",
            probability_distribution={"2-1": 0.107, "1-1": 0.098, "2-0": 0.083, "0-0": 0.045},
        )

        seed = _build_scoreline_reasoning_seed(prediction)

        assert seed is not None
        assert seed.selected_score == "2-1"
        assert seed.selected_probability == 0.107
        assert seed.expected_home_goals == 1.7
        assert seed.expected_away_goals == 1.2
        assert set(a.score for a in seed.alternatives) == {"1-1", "2-0", "0-0"}
        # Sorted by real probability, descending
        assert seed.alternatives[0].score == "1-1"

    def test_expected_goals_rounds_up_only_at_or_above_point_eight(self):
        prediction = _prediction(None, {"football.fixture.expected_home_goals": 1.8, "football.fixture.expected_away_goals": 2.79})
        prediction = dataclasses.replace(
            prediction, value="2-1",
            probability_distribution={"2-1": 0.107, "1-1": 0.098, "2-0": 0.083, "0-0": 0.045},
        )

        seed = _build_scoreline_reasoning_seed(prediction)

        assert seed is not None
        assert seed.expected_home_goals == 2.0  # 1.8 -> rounds up (frac >= 0.8)
        assert seed.expected_away_goals == 2.79  # 2.79 -> left as-is (frac < 0.8)

    def test_non_score_value_returns_none(self):
        prediction = _prediction(None, {})
        prediction = dataclasses.replace(prediction, value="AWAY_WIN", probability_distribution={"HOME_WIN": 0.4, "AWAY_WIN": 0.6})

        assert _build_scoreline_reasoning_seed(prediction) is None

    def test_lone_score_like_value_with_no_siblings_returns_none(self):
        """A binary market whose generic value coincidentally looks like a scoreline ("2-1" as a
        set score, say) must not be misread as a real Correct Score grid."""
        prediction = _prediction(None, {})
        prediction = dataclasses.replace(prediction, value="2-1", probability_distribution={"2-1": 0.6, "1-2": 0.4})

        assert _build_scoreline_reasoning_seed(prediction) is None


class TestNarrateEvidence:
    pytestmark = []  # pure sync functions — override the module-level asyncio mark

    def test_drops_narration_for_a_source_id_never_supplied(self):
        """§13 — Gemini may summarize evidence, never invent it: a hallucinated source_id must
        never surface as if it were real."""

        @dataclass
        class _FakeSchemaItem:
            source_id: str
            analysis: str

        real_item = EvidenceItem(source_id="real-1", category="injuries", summary="Out (hamstring)", entity_ref="team-1")

        class _FakeEvidence:
            items_by_category = {"injuries": (real_item,)}

        narrated = _narrate_evidence(_FakeEvidence(), "injuries", [_FakeSchemaItem(source_id="hallucinated-99", analysis="invented")])

        assert len(narrated) == 1
        assert narrated[0].source_id == "real-1"
        assert narrated[0].analysis == ""  # never narrated (the only narration supplied cited a fake id)

    def test_real_item_without_narration_still_appears(self):
        real_item = EvidenceItem(source_id="real-1", category="news", summary="Manager change reported", entity_ref="team-1")

        class _FakeEvidence:
            items_by_category = {"news": (real_item,)}

        narrated = _narrate_evidence(_FakeEvidence(), "news", [])

        assert len(narrated) == 1
        assert narrated[0].summary == "Manager change reported"
        assert narrated[0].analysis == ""


def _valid_scoreline_schema_response(key_reasons: list) -> str:
    return json.dumps(
        {
            "verdict": "Test verdict.",
            "key_reason_narration": [{"rank": r["rank"], "analysis": f"narration for {r['feature']}"} for r in key_reasons],
            "counter_signal_narration": [],
            "match_profile": "profile",
            "confidence_explanation": "confidence text",
            "bottom_line": "bottom line",
            "scoreline_reasoning": {
                "home_goal_case": "Home case narration.",
                "away_goal_case": "Away case narration.",
                "alternative_comparison": "Comparison narration.",
                "distribution_consistent": True,
            },
        }
    )


class TestCorrectScoreExplanation:
    async def test_correct_score_market_produces_real_scoreline_reasoning(self, model_repo):
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_scoreline_schema_response(key_reasons_payload))
        prediction = dataclasses.replace(
            prediction, value="2-1",
            probability_distribution={"2-1": 0.107, "1-1": 0.098, "2-0": 0.083, "0-0": 0.045},
            feature_snapshot={**prediction.feature_snapshot, "football.fixture.expected_home_goals": 1.7, "football.fixture.expected_away_goals": 1.2},
        )
        market = dataclasses.replace(_market(market_key="football.correct_score"), name="Correct Score")

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is ExplanationStatus.AVAILABLE
        assert result.scoreline_reasoning is not None
        assert result.scoreline_reasoning.selected_score == "2-1"
        assert result.scoreline_reasoning.selected_probability == 0.107
        assert result.scoreline_reasoning.expected_home_goals == 1.7
        assert result.scoreline_reasoning.home_goal_case == "Home case narration."
        assert result.scoreline_reasoning.alternative_comparison == "Comparison narration."

    async def test_non_correct_score_market_has_no_scoreline_reasoning(self, model_repo):
        key_reasons_payload = [{"rank": 1, "feature": "form_diff"}]
        service, prediction, model_def = await _binary_service(model_repo, _valid_schema_response(key_reasons_payload))
        market = _market()  # defaults to football.both_teams_to_score

        result = await service.explain(prediction, market, datetime.now(timezone.utc))

        assert result.status is ExplanationStatus.AVAILABLE
        assert result.scoreline_reasoning is None


@dataclass
class _FakeConsistencyGate:
    passed: bool = True

    async def check(self, prediction, market, now):
        from modules.predictions.application.prediction_consistency_gate import ConsistencyCheckResult

        if self.passed:
            return ConsistencyCheckResult(passed=True)
        return ConsistencyCheckResult(passed=False, failed_checks=("model_no_longer_champion",))
