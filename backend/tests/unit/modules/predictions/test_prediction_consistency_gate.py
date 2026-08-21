"""Pre-Gemini Prediction-Explanation Consistency Gate (spec §23) — unit tests for the gate's own
check logic, independent of either caller (`ContextualReasoningService`/`FootballExplanationService`,
covered by their own test files)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.prediction_consistency_gate import PredictionConsistencyGate
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    MarketDefinition,
    ModelDefinition,
    Prediction,
)
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

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


@dataclass
class _FakeModelRepo:
    models: dict = field(default_factory=dict)  # ModelId -> ModelDefinition
    champion: ModelDefinition | None = None

    async def get(self, model_id):
        return self.models.get(model_id)

    async def get_champion(self, market_id):
        return self.champion


def _market() -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key="football.match_winner", sport_code="football", name="Match Winner",
        category="match_outcome", market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


def _trained_model(market_id, status=ModelStatus.CHAMPION) -> ModelDefinition:
    return ModelDefinition(
        id=ModelId(uuid4()), market_id=market_id, model_key="football.match_winner.logistic_regression",
        version=1, algorithm="logistic_regression", status=status, framework="sklearn",
        artifact_ref="real-artifact-ref",
    )


def _correct_score_market() -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key="football.correct_score", sport_code="football", name="Correct Score",
        category="scoreline", market_kind=MarketKind.CORRECT_SCORE, target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


def _prediction(model_id, *, feature_snapshot=None, generated_at=None, value="HOME_WIN") -> Prediction:
    if feature_snapshot is None:
        feature_snapshot = {"a": 1.0}
    return Prediction(
        id=PredictionId(uuid4()), market_id=MarketId(uuid4()), model_id=model_id, subject_ref="fixture-1",
        value=value, probability=0.6, confidence=ConfidenceBreakdown(*([0.7] * 9)),
        explanation=ExplanationBundle(), feature_snapshot=feature_snapshot, model_version="1",
        status=PredictionStatus.PUBLISHED, generated_at=generated_at,
    )


@pytest.mark.asyncio
async def test_passes_when_prediction_model_is_the_current_champion():
    market = _market()
    model = _trained_model(market.id)
    repo = _FakeModelRepo(models={model.id: model}, champion=model)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(model.id, generated_at=T0), market, T0)

    assert result.passed
    assert result.failed_checks == ()
    assert result.reason is None


@pytest.mark.asyncio
async def test_fails_when_model_no_longer_the_champion():
    """The exact scenario spec §23 exists to catch: a prediction generated against an old
    Champion, requested for explanation after a newer model has since been promoted."""
    market = _market()
    old_model = _trained_model(market.id, status=ModelStatus.RETIRED)
    new_champion = _trained_model(market.id, status=ModelStatus.CHAMPION)
    repo = _FakeModelRepo(models={old_model.id: old_model, new_champion.id: new_champion}, champion=new_champion)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(old_model.id, generated_at=T0), market, T0)

    assert not result.passed
    assert "model_no_longer_champion" in result.failed_checks
    assert result.reason == "BLOCKED_INCONSISTENT_EVIDENCE: model_no_longer_champion"


@pytest.mark.asyncio
async def test_fails_when_no_champion_set_for_market():
    market = _market()
    model = _trained_model(market.id)
    repo = _FakeModelRepo(models={model.id: model}, champion=None)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(model.id, generated_at=T0), market, T0)

    assert not result.passed
    assert "model_no_longer_champion" in result.failed_checks


@pytest.mark.asyncio
async def test_fails_when_model_definition_missing():
    market = _market()
    repo = _FakeModelRepo(models={}, champion=None)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(ModelId(uuid4()), generated_at=T0), market, T0)

    assert not result.passed
    assert result.failed_checks == ("model_definition_missing",)


@pytest.mark.asyncio
async def test_fails_when_prediction_has_no_associated_model():
    market = _market()
    repo = _FakeModelRepo()
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(None, generated_at=T0), market, T0)

    assert not result.passed
    assert result.failed_checks == ("no_associated_model",)


@pytest.mark.asyncio
async def test_fails_when_model_has_no_real_provenance():
    """A placeholder Champion (e.g. a heuristic fallback registered only to unblock generation,
    per `ModelDefinition.is_genuinely_trained()`'s own docstring) must not be explained as if it
    were a real trained model."""
    market = _market()
    placeholder = ModelDefinition(
        id=ModelId(uuid4()), market_id=market.id, model_key="football.match_winner.heuristic_logistic",
        version=1, algorithm="heuristic_logistic_v1", status=ModelStatus.CHAMPION, framework=None,
        artifact_ref=None, trained_at=None,
    )
    repo = _FakeModelRepo(models={placeholder.id: placeholder}, champion=placeholder)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(placeholder.id, generated_at=T0), market, T0)

    assert not result.passed
    assert "model_provenance_missing" in result.failed_checks


@pytest.mark.asyncio
async def test_fails_when_feature_snapshot_is_empty():
    market = _market()
    model = _trained_model(market.id)
    repo = _FakeModelRepo(models={model.id: model}, champion=model)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(model.id, feature_snapshot={}, generated_at=T0), market, T0)

    assert not result.passed
    assert "empty_feature_snapshot" in result.failed_checks


@pytest.mark.asyncio
async def test_fails_when_prediction_is_too_stale():
    market = _market()
    model = _trained_model(market.id)
    repo = _FakeModelRepo(models={model.id: model}, champion=model)
    gate = PredictionConsistencyGate(models=repo, max_prediction_age=timedelta(hours=48))
    stale_generated_at = T0 - timedelta(hours=72)

    result = await gate.check(_prediction(model.id, generated_at=stale_generated_at), market, T0)

    assert not result.passed
    assert "prediction_too_stale" in result.failed_checks


@pytest.mark.asyncio
async def test_no_staleness_check_when_generated_at_is_none():
    """A prediction with no `generated_at` yet (shouldn't normally happen, but the gate must not
    crash on it) skips the staleness check rather than raising."""
    market = _market()
    model = _trained_model(market.id)
    repo = _FakeModelRepo(models={model.id: model}, champion=model)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(model.id, generated_at=None), market, T0)

    assert result.passed


@pytest.mark.asyncio
async def test_multiple_failed_checks_are_all_reported():
    market = _market()
    model = _trained_model(market.id, status=ModelStatus.RETIRED)
    other_champion = _trained_model(market.id, status=ModelStatus.CHAMPION)
    repo = _FakeModelRepo(models={model.id: model, other_champion.id: other_champion}, champion=other_champion)
    gate = PredictionConsistencyGate(models=repo, max_prediction_age=timedelta(hours=48))
    stale_generated_at = T0 - timedelta(hours=72)

    result = await gate.check(
        _prediction(model.id, feature_snapshot={}, generated_at=stale_generated_at), market, T0,
    )

    assert not result.passed
    assert set(result.failed_checks) == {"model_no_longer_champion", "empty_feature_snapshot", "prediction_too_stale"}


# --- Correct-Score Consistency (spec §22) ------------------------------------------------------


@pytest.mark.asyncio
async def test_correct_score_well_formed_scoreline_passes():
    market = _correct_score_market()
    model = _trained_model(market.id)
    repo = _FakeModelRepo(models={model.id: model}, champion=model)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(model.id, generated_at=T0, value="1-2"), market, T0)

    assert result.passed


@pytest.mark.asyncio
async def test_correct_score_other_catch_all_passes():
    market = _correct_score_market()
    model = _trained_model(market.id)
    repo = _FakeModelRepo(models={model.id: model}, champion=model)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(model.id, generated_at=T0, value="OTHER"), market, T0)

    assert result.passed


@pytest.mark.asyncio
async def test_correct_score_malformed_value_fails():
    market = _correct_score_market()
    model = _trained_model(market.id)
    repo = _FakeModelRepo(models={model.id: model}, champion=model)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(model.id, generated_at=T0, value="HOME_WIN"), market, T0)

    assert not result.passed
    assert "malformed_correct_score_value" in result.failed_checks


@pytest.mark.asyncio
async def test_non_correct_score_market_skips_scoreline_check():
    """The scoreline check is scoped to `football.correct_score` only — a non-scoreline value on
    any other market must never trip it."""
    market = _market()
    model = _trained_model(market.id)
    repo = _FakeModelRepo(models={model.id: model}, champion=model)
    gate = PredictionConsistencyGate(models=repo)

    result = await gate.check(_prediction(model.id, generated_at=T0, value="HOME_WIN"), market, T0)

    assert result.passed
