"""Experiment Tracking (Milestone 9.1) — records Validation/HPO runs into the EXISTING
`Experiment` entity/`ExperimentRepositoryPort` (Milestone 9's `experiments` table and
"No market's production model changes without one of these existing first" rule,
docs/prediction_markets.md §5). Extended additively: no new entity, no schema change — this
service is a new way of *populating* `Experiment.config`/`Experiment.metrics`, reusing exactly
the fields Milestone 9 already defined.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.predictions.domain.entities import Experiment
from modules.predictions.domain.model_selection import ModelSelectionResult
from modules.predictions.domain.validation import CrossValidationResult, HPOResult
from modules.predictions.domain.value_objects import ExperimentId, MarketId
from modules.predictions.ports.repositories import ExperimentRepositoryPort


class ExperimentNotFoundError(KeyError):
    pass


class InvalidExperimentDecisionError(ValueError):
    pass

_VALID_DECISIONS = {"promoted", "rejected", "pending"}


@dataclass
class ExperimentTrackingService:
    experiments: ExperimentRepositoryPort

    async def record_validation(self, market_id: MarketId, result: CrossValidationResult, now: datetime) -> Experiment:
        experiment = Experiment(
            id=ExperimentId(uuid4()),
            market_id=market_id,
            config={"kind": "validation", "strategy": result.strategy.value, "fold_count": len(result.fold_results)},
            metrics={"mean_metric": result.mean_metric, "std_metric": result.std_metric},
            decision="pending",
            created_at=now,
        )
        return await self.experiments.record(experiment)

    async def record_hpo(self, market_id: MarketId, result: HPOResult, now: datetime) -> Experiment:
        numeric_params = {
            f"param.{key}": value for key, value in result.best_params.items() if isinstance(value, (int, float))
        }
        experiment = Experiment(
            id=ExperimentId(uuid4()),
            market_id=market_id,
            config={"kind": "hpo", "strategy": result.strategy.value, "trial_count": len(result.trials)},
            metrics={"best_metric_value": result.best_metric_value, **numeric_params},
            decision="pending",
            created_at=now,
        )
        return await self.experiments.record(experiment)

    async def record_model_selection(self, market_id: MarketId, result: ModelSelectionResult, now: datetime) -> Experiment:
        """Automatic Model Selection's benchmark (Milestone 9.1 task #164) — records every
        candidate considered and which one won, so "Never hardcode algorithm selection" is
        auditable after the fact, not just true at the moment it ran."""
        experiment = Experiment(
            id=ExperimentId(uuid4()),
            market_id=market_id,
            config={
                "kind": "model_selection",
                "candidates_considered": [c.algorithm.value for c in result.all_candidates],
                "candidates_skipped": [c.algorithm.value for c, _ in result.skipped_candidates],
                "winning_algorithm": result.winning_candidate.algorithm.value,
                "winning_framework": result.winning_candidate.framework.value,
            },
            metrics={f"ranking.{result.ranking_metric}": result.ranking_value},
            decision="pending",
            created_at=now,
        )
        return await self.experiments.record(experiment)

    async def compare(self, market_id: MarketId, limit: int = 50) -> list[Experiment]:
        """Milestone 9.1 "Model Comparison" — every recorded experiment for a market, most
        recent first (whatever order `ExperimentRepositoryPort.list_by_market` returns)."""
        return await self.experiments.list_by_market(market_id, limit=limit)

    async def decide(self, experiment_id: ExperimentId, decision: str) -> Experiment:
        if decision not in _VALID_DECISIONS:
            raise InvalidExperimentDecisionError(f"'{decision}' is not one of {sorted(_VALID_DECISIONS)}")
        experiment = await self.experiments.get(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(str(experiment_id))
        experiment.decision = decision
        return await self.experiments.update(experiment)
