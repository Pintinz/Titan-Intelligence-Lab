"""Gemini Prediction Reasoning Engine — live statistical-baseline lookup for the Gemini contract's
`statistical_baseline` field (spec Phase 9/11). Deliberately independent of Champion selection:
`_check_and_retrain` (`scheduled_retraining_orchestrator.py`) already benchmarks
`FootballGoalsPoissonAdapter` for real against the ML roster for its 12 eligible markets — this
service does NOT re-run or duplicate that competition, it only *reads back* whatever Poisson model
currently exists for the market (Champion or Challenger, doesn't matter) via
`ModelRepositoryPort.get_by_market_and_algorithm`, so Gemini can see the ML Champion's probability
next to a genuine statistical baseline even when Poisson lost its own Champion race.

Never fabricates: a market with no `market_shape` mapping is `applicable=False`; a mapped market
with no trained Poisson artifact yet is `applicable=True, available=False,
reason="BASELINE_DATA_INSUFFICIENT"`.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.predictions.application.outcome_label_mapper import map_generic_value_to_real_label
from modules.predictions.application.scheduled_retraining_orchestrator import POISSON_ELIGIBLE_MARKETS
from modules.predictions.domain.contextual_reasoning import StatisticalBaseline
from modules.predictions.domain.ml_value_objects import MLAlgorithm
from modules.predictions.domain.poisson_score_grid import both_teams_to_score_probabilities, match_winner_probabilities
from modules.predictions.domain.value_objects import MarketId, TargetType
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.ports.repositories import MarketRepositoryPort, ModelRepositoryPort

_CORRECT_SCORE_MARKET_KEY = "football.correct_score"

# Derived (not separately trained) markets: their baseline is read off the already-fitted
# `football.correct_score` Poisson model's lam_home/lam_away, via `poisson_score_grid` — see that
# module's docstring for why this is legitimate reuse rather than a second training pass.
_DERIVED_MARKETS: dict[str, str] = {
    "football.match_winner": "match_winner",
    "football.both_teams_to_score": "both_teams_to_score",
}


@dataclass
class StatisticalBaselineProvider:
    markets: MarketRepositoryPort
    models: ModelRepositoryPort
    model_loader: ModelLoaderService

    async def get(self, market_id: MarketId, market_key: str, features: dict[str, float]) -> StatisticalBaseline:
        if market_key in POISSON_ELIGIBLE_MARKETS:
            return await self._direct_baseline(market_id, market_key, features)
        if market_key in _DERIVED_MARKETS:
            return await self._derived_baseline(_DERIVED_MARKETS[market_key], features)
        return StatisticalBaseline(applicable=False, available=False)

    async def _direct_baseline(self, market_id: MarketId, market_key: str, features: dict[str, float]) -> StatisticalBaseline:
        model_def = await self.models.get_by_market_and_algorithm(market_id, MLAlgorithm.POISSON_GOALS_MODEL.value)
        if model_def is None or not model_def.is_genuinely_trained():
            return StatisticalBaseline(
                applicable=True, available=False,
                algorithm=MLAlgorithm.POISSON_GOALS_MODEL.value, reason="BASELINE_DATA_INSUFFICIENT",
            )
        adapter = await self.model_loader.load(
            model_def.id, model_def.framework, model_def.algorithm, TargetType.CLASSIFICATION, model_def.artifact_ref
        )
        prediction = adapter.predict_one(features)
        # Threshold-shaped Poisson predictions (total/team-total/clean-sheet/win-to-nil) emit the
        # generic "positive"/"negative" convention (`FootballGoalsPoissonAdapter.predict_one`),
        # not a real per-market label — this baseline is user-facing (Gemini's own contract and
        # `ContextualReviewPanel` both display `probabilities` keys directly), so it must carry the
        # market's real label exactly like `PredictionEngine._shape_outcome` already does for the
        # Champion model's own distribution, not leak the generic internal convention.
        if prediction.distribution:
            probabilities = prediction.distribution
        else:
            probabilities = {map_generic_value_to_real_label(market_key, prediction.value): prediction.probability}
        return StatisticalBaseline(
            applicable=True, available=True,
            algorithm=MLAlgorithm.POISSON_GOALS_MODEL.value, probabilities=probabilities,
        )

    async def _derived_baseline(self, derivation: str, features: dict[str, float]) -> StatisticalBaseline:
        correct_score_market = await self.markets.get_by_key(_CORRECT_SCORE_MARKET_KEY)
        if correct_score_market is None:
            return StatisticalBaseline(
                applicable=True, available=False,
                algorithm=MLAlgorithm.POISSON_GOALS_MODEL.value, reason="BASELINE_DATA_INSUFFICIENT",
            )
        model_def = await self.models.get_by_market_and_algorithm(
            correct_score_market.id, MLAlgorithm.POISSON_GOALS_MODEL.value
        )
        if model_def is None or not model_def.is_genuinely_trained():
            return StatisticalBaseline(
                applicable=True, available=False,
                algorithm=MLAlgorithm.POISSON_GOALS_MODEL.value, reason="BASELINE_DATA_INSUFFICIENT",
            )
        adapter = await self.model_loader.load(
            model_def.id, model_def.framework, model_def.algorithm, TargetType.CLASSIFICATION, model_def.artifact_ref
        )
        lam_home, lam_away = adapter.predict_lambdas(features)
        if derivation == "match_winner":
            probabilities = match_winner_probabilities(lam_home, lam_away)
        else:
            probabilities = both_teams_to_score_probabilities(lam_home, lam_away)
        return StatisticalBaseline(
            applicable=True, available=True,
            algorithm=MLAlgorithm.POISSON_GOALS_MODEL.value, probabilities=probabilities,
        )
