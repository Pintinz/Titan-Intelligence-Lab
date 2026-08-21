"""Goal-Generative vs Direct-Classifier Comparison (spec §9) — for `football.match_winner` and
`football.both_teams_to_score`, empirically compares the derived Poisson baseline
(`StatisticalBaselineProvider`, reading a fitted `football.correct_score` model's
lam_home/lam_away) against the market's own direct-classifier Champion, using REAL resolved
outcome history — never a fresh training run, never a fabricated number.

Both sides are scored the identical way `TrainingPipelineService`'s own held-out evaluation
scores every ML candidate: log loss over "the probability each model assigned to whichever
outcome actually happened," recovered from `Prediction.probability_distribution` (the Champion's
own already-recorded call) and `StatisticalBaselineProvider.get()` (the same derivation Gemini's
contextual reasoning already reads, re-evaluated per historical fixture) against
`PredictionOutcome.actual_value` (the real resolved label — works for a 3-way market like
match_winner exactly the same as a binary one like both_teams_to_score, unlike the
positive/negative-only `outcome_label_mapper` helpers).

The result is recorded as an `Experiment` (`kind="goal_generative_vs_classifier"`) — spec §9's
own instruction: "Only introduce an ensemble if an experiment demonstrates improved out-of-sample
performance." This service produces exactly that experiment; it never auto-promotes, auto-
ensembles, or otherwise changes which model actually serves live traffic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.predictions.application.statistical_baseline_provider import StatisticalBaselineProvider
from modules.predictions.domain.entities import Experiment
from modules.predictions.domain.probability_metrics import log_loss
from modules.predictions.domain.value_objects import ExperimentId, MarketId
from modules.predictions.ports.repositories import (
    ExperimentRepositoryPort,
    ModelRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)

ELIGIBLE_MARKETS = ("football.match_winner", "football.both_teams_to_score")
DEFAULT_MIN_SAMPLES = 20


class MarketNotEligibleError(ValueError):
    pass


@dataclass(frozen=True)
class GoalGenerativeComparisonResult:
    market_key: str
    sample_count: int
    classifier_log_loss: float | None
    goal_generative_log_loss: float | None
    goal_generative_wins: bool | None
    reason: str | None = None


@dataclass
class GoalGenerativeComparisonService:
    models: ModelRepositoryPort
    predictions: PredictionRepositoryPort
    outcomes: PredictionOutcomeRepositoryPort
    baseline_provider: StatisticalBaselineProvider
    experiments: ExperimentRepositoryPort
    min_samples: int = DEFAULT_MIN_SAMPLES

    async def compare(self, market_id: MarketId, market_key: str, now: datetime) -> GoalGenerativeComparisonResult:
        if market_key not in ELIGIBLE_MARKETS:
            raise MarketNotEligibleError(f"'{market_key}' has no goal-generative derivation to compare against")

        champion = await self.models.get_champion(market_id)
        if champion is None:
            return GoalGenerativeComparisonResult(market_key, 0, None, None, None, reason="no champion model")

        recorded_outcomes = await self.outcomes.list_by_market(market_id, limit=2000)

        classifier_true_probs: list[float] = []
        baseline_true_probs: list[float] = []
        skipped_no_baseline = 0

        for outcome in recorded_outcomes:
            prediction = await self.predictions.get(outcome.prediction_id)
            if prediction is None or prediction.model_id != champion.id:
                continue
            actual = outcome.actual_value
            classifier_prob = (prediction.probability_distribution or {}).get(actual)
            if classifier_prob is None:
                continue

            baseline = await self.baseline_provider.get(market_id, market_key, dict(prediction.feature_snapshot))
            if not baseline.available or not baseline.probabilities:
                skipped_no_baseline += 1
                continue
            baseline_prob = baseline.probabilities.get(actual)
            if baseline_prob is None:
                continue

            classifier_true_probs.append(classifier_prob)
            baseline_true_probs.append(baseline_prob)

        n = len(classifier_true_probs)
        if n < self.min_samples:
            return GoalGenerativeComparisonResult(
                market_key, n, None, None, None,
                reason=(
                    f"fewer than {self.min_samples} usable samples with both a real Champion "
                    f"probability and an available goal-generative baseline "
                    f"({skipped_no_baseline} skipped for no baseline)"
                ),
            )

        classifier_ll = log_loss(classifier_true_probs)
        baseline_ll = log_loss(baseline_true_probs)

        experiment = Experiment(
            id=ExperimentId(uuid4()),
            market_id=market_id,
            config={
                "kind": "goal_generative_vs_classifier",
                "market_key": market_key,
                "classifier_algorithm": champion.algorithm,
                "classifier_model_id": str(champion.id),
                "sample_count": n,
            },
            metrics={"classifier_log_loss": classifier_ll, "goal_generative_log_loss": baseline_ll},
            decision="pending",
            created_at=now,
        )
        await self.experiments.record(experiment)

        return GoalGenerativeComparisonResult(
            market_key=market_key, sample_count=n, classifier_log_loss=classifier_ll,
            goal_generative_log_loss=baseline_ll, goal_generative_wins=baseline_ll < classifier_ll,
        )
