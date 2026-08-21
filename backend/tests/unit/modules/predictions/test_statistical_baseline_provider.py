"""Tests for `StatisticalBaselineProvider` — the live (never training-time) Poisson baseline
lookup that feeds the Gemini contract's `statistical_baseline` field. Uses real
`FootballGoalsPoissonAdapter` fit/serialize round trips (via `ModelLoaderService` +
`ModelArtifactStorePort`), not mocked ML internals — the same discipline
`test_football_goals_poisson_adapter.py` already established. `market_repo`/`model_repo`
fixtures come from this directory's `conftest.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from modules.predictions.application.statistical_baseline_provider import StatisticalBaselineProvider
from modules.predictions.domain.entities import MarketDefinition, ModelDefinition
from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.value_objects import MarketId, MarketKind, MarketStatus, ModelId, ModelStatus, TargetType
from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import FootballGoalsPoissonAdapter
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.ports.ml_model import TrainingSample


@dataclass
class _InMemoryArtifactStore:
    store: dict = field(default_factory=dict)

    async def save(self, key: str, payload: bytes) -> str:
        self.store[key] = payload
        return key

    async def load(self, ref: str) -> bytes:
        return self.store[ref]


def _market(market_key: str) -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key=market_key, sport_code="football", name=market_key,
        category="totals", market_kind=MarketKind.TOTAL, target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


def _poisson_training_samples(n: int = 40) -> list[TrainingSample]:
    samples = []
    for i in range(n):
        x1 = float(i % 10)
        samples.append(
            TrainingSample(
                features={"x1": x1}, label=0.0,
                raw_home_goals=max(0.0, round(0.35 * x1)), raw_away_goals=max(0.0, round(0.10 * x1)),
            )
        )
    return samples


async def _trained_model_def(
    market: MarketDefinition, market_shape: str, artifacts: _InMemoryArtifactStore, **extra_params
) -> ModelDefinition:
    adapter = FootballGoalsPoissonAdapter(params={"market_shape": market_shape, **extra_params})
    await adapter.fit(_poisson_training_samples())
    ref = await artifacts.save(f"{market.market_key}.poisson.bin", adapter.serialize())
    return ModelDefinition(
        id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.poisson_goals_model", version=6,
        algorithm=MLAlgorithm.POISSON_GOALS_MODEL.value, framework=MLFramework.POISSON_GOALS.value,
        status=ModelStatus.CHALLENGER, artifact_ref=ref,
    )


class TestDirectBaseline:
    async def test_eligible_market_with_trained_model_is_available(self, market_repo, model_repo):
        market = _market("football.total_goals_over_under")
        await market_repo.upsert(market)
        artifacts = _InMemoryArtifactStore()
        await model_repo.upsert(await _trained_model_def(market, "total_threshold", artifacts, line=2.5))
        provider = StatisticalBaselineProvider(markets=market_repo, models=model_repo, model_loader=ModelLoaderService(artifacts))

        baseline = await provider.get(market.id, market.market_key, {"x1": 5.0})

        assert baseline.applicable is True
        assert baseline.available is True
        assert baseline.algorithm == "poisson_goals_model"
        assert baseline.probabilities is not None
        assert baseline.reason is None
        # Threshold-shaped Poisson predictions emit the generic "positive"/"negative" convention
        # internally — the baseline is user-facing (Gemini's contract + ContextualReviewPanel
        # both render `probabilities` keys directly), so it must carry the market's real label.
        assert set(baseline.probabilities.keys()) <= {"OVER", "UNDER"}
        assert "positive" not in baseline.probabilities
        assert "negative" not in baseline.probabilities

    async def test_clean_sheet_market_uses_yes_no_label_not_generic_convention(self, market_repo, model_repo):
        market = _market("football.home_clean_sheet")
        await market_repo.upsert(market)
        artifacts = _InMemoryArtifactStore()
        await model_repo.upsert(await _trained_model_def(market, "clean_sheet", artifacts, team="home"))
        provider = StatisticalBaselineProvider(markets=market_repo, models=model_repo, model_loader=ModelLoaderService(artifacts))

        baseline = await provider.get(market.id, market.market_key, {"x1": 5.0})

        assert baseline.probabilities is not None
        assert set(baseline.probabilities.keys()) <= {"YES", "NO"}
        assert "positive" not in baseline.probabilities
        assert "negative" not in baseline.probabilities

    async def test_eligible_market_without_trained_model_is_unavailable_not_fabricated(self, market_repo, model_repo):
        market = _market("football.home_win_to_nil")
        await market_repo.upsert(market)
        provider = StatisticalBaselineProvider(
            markets=market_repo, models=model_repo, model_loader=ModelLoaderService(_InMemoryArtifactStore())
        )

        baseline = await provider.get(market.id, market.market_key, {"x1": 5.0})

        assert baseline.applicable is True
        assert baseline.available is False
        assert baseline.probabilities is None
        assert baseline.reason == "BASELINE_DATA_INSUFFICIENT"

    async def test_market_with_no_poisson_family_is_not_applicable(self, market_repo, model_repo):
        market = _market("football.match_result")  # not one of the 12 goals/score markets, no derivation either
        await market_repo.upsert(market)
        provider = StatisticalBaselineProvider(
            markets=market_repo, models=model_repo, model_loader=ModelLoaderService(_InMemoryArtifactStore())
        )

        baseline = await provider.get(market.id, market.market_key, {"x1": 5.0})

        assert baseline.applicable is False
        assert baseline.available is False


class TestDerivedBaseline:
    async def test_match_winner_derives_from_correct_score_model(self, market_repo, model_repo):
        correct_score_market = _market("football.correct_score")
        match_winner_market = _market("football.match_winner")
        await market_repo.upsert(correct_score_market)
        await market_repo.upsert(match_winner_market)
        artifacts = _InMemoryArtifactStore()
        await model_repo.upsert(await _trained_model_def(correct_score_market, "correct_score", artifacts))
        provider = StatisticalBaselineProvider(markets=market_repo, models=model_repo, model_loader=ModelLoaderService(artifacts))

        baseline = await provider.get(match_winner_market.id, match_winner_market.market_key, {"x1": 8.0})

        assert baseline.applicable is True
        assert baseline.available is True
        assert set(baseline.probabilities.keys()) == {"HOME_WIN", "DRAW", "AWAY_WIN"}
        assert abs(sum(baseline.probabilities.values()) - 1.0) < 1e-6

    async def test_both_teams_to_score_derives_from_correct_score_model(self, market_repo, model_repo):
        correct_score_market = _market("football.correct_score")
        btts_market = _market("football.both_teams_to_score")
        await market_repo.upsert(correct_score_market)
        await market_repo.upsert(btts_market)
        artifacts = _InMemoryArtifactStore()
        await model_repo.upsert(await _trained_model_def(correct_score_market, "correct_score", artifacts))
        provider = StatisticalBaselineProvider(markets=market_repo, models=model_repo, model_loader=ModelLoaderService(artifacts))

        baseline = await provider.get(btts_market.id, btts_market.market_key, {"x1": 8.0})

        assert baseline.applicable is True
        assert baseline.available is True
        assert set(baseline.probabilities.keys()) == {"YES", "NO"}

    async def test_derived_market_without_correct_score_model_is_unavailable(self, market_repo, model_repo):
        match_winner_market = _market("football.match_winner")
        await market_repo.upsert(match_winner_market)
        provider = StatisticalBaselineProvider(
            markets=market_repo, models=model_repo, model_loader=ModelLoaderService(_InMemoryArtifactStore())
        )

        baseline = await provider.get(match_winner_market.id, match_winner_market.market_key, {"x1": 8.0})

        assert baseline.applicable is True
        assert baseline.available is False
        assert baseline.reason == "BASELINE_DATA_INSUFFICIENT"
