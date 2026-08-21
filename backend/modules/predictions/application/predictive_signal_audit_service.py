"""Predictive Signal Recovery charter, Phase 1 — builds the "market matrix" the charter's Phase 1
asks for: sample count, feature count, missingness, temporal availability, provenance/leakage,
preflight status, current Champion + algorithm, validation/calibration metrics, prediction/
outcome counts, and baseline-vs-ML candidate scores, for every registered market.

Never trains a model, never builds a fresh `Dataset` itself — the matrix's own numbers come from
whatever is already persisted (`DatasetRepositoryPort.get_latest_version()`,
`ModelRepositoryPort.get_champion()`, `ExperimentRepositoryPort.list_by_market()`, ...).
`TrainingPreflightService` remains the one place that legitimately rebuilds a dataset (for its own
reproducibility check) — this service treats `include_preflight` as an explicit, optional,
expensive step rather than duplicating that build.
"""

from __future__ import annotations

import statistics as stats
from dataclasses import dataclass
from datetime import datetime

from modules.features.domain.value_objects import FeatureKey
from modules.features.ports.repositories import FeatureDefinitionRepositoryPort
from modules.predictions.application.training_preflight_service import TrainingPreflightService
from modules.predictions.domain.market_audit import MarketAuditRecord
from modules.predictions.domain.value_objects import MarketId
from modules.predictions.ports.dataset_repository import DatasetRepositoryPort
from modules.predictions.ports.repositories import (
    ExperimentRepositoryPort,
    FeatureMarketMappingRepositoryPort,
    MarketRepositoryPort,
    ModelEvaluationRepositoryPort,
    ModelRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)


class MarketNotFoundError(KeyError):
    pass


@dataclass
class PredictiveSignalAuditService:
    markets: MarketRepositoryPort
    mappings: FeatureMarketMappingRepositoryPort
    feature_definitions: FeatureDefinitionRepositoryPort
    dataset_repo: DatasetRepositoryPort
    models: ModelRepositoryPort
    model_evaluations: ModelEvaluationRepositoryPort
    predictions: PredictionRepositoryPort
    outcomes: PredictionOutcomeRepositoryPort
    experiments: ExperimentRepositoryPort
    preflight: TrainingPreflightService

    async def audit_market(
        self, market_key: str, now: datetime, *, include_preflight: bool = True
    ) -> MarketAuditRecord:
        market = await self.markets.get_by_key(market_key)
        if market is None:
            raise MarketNotFoundError(market_key)

        fields: dict = dict(
            market_key=market.market_key,
            sport_code=market.sport_code,
            market_kind=market.market_kind,
            target_type=market.target_type,
            market_status=market.status,
        )

        dataset = await self.dataset_repo.get_latest_version(market.id)
        if dataset is not None:
            target_variance = None
            if market.target_type.value == "regression" and dataset.samples:
                labels = [s.label for s in dataset.samples]
                target_variance = stats.pvariance(labels) if len(labels) > 1 else 0.0
            reference_times = [s.reference_time for s in dataset.samples if s.reference_time is not None]
            fields.update(
                has_persisted_dataset=True,
                dataset_version=dataset.version,
                dataset_status=dataset.status,
                dataset_built_at=dataset.created_at,
                sample_count=dataset.statistics.sample_count,
                feature_count=dataset.statistics.feature_count,
                positive_rate=dataset.statistics.positive_rate,
                target_variance=target_variance,
                missing_rate=dict(dataset.statistics.missing_rate),
                earliest_reference_time=min(reference_times) if reference_times else None,
                latest_reference_time=max(reference_times) if reference_times else None,
            )

        mappings = await self.mappings.list_by_market(market.id)
        required_keys = sorted(m.feature_key for m in mappings if m.is_required)
        optional_keys = sorted(m.feature_key for m in mappings if not m.is_required)
        unresolved: list[str] = []
        leakage_unsafe: list[str] = []
        unknown_provenance: list[str] = []
        for key in required_keys:
            definition = await self.feature_definitions.get(FeatureKey(key))
            if definition is None or not definition.is_consumable():
                unresolved.append(key)
                continue
            if not definition.is_market_safe():
                leakage_unsafe.append(key)
            if definition.leakage_classification == "UNKNOWN_PROVENANCE":
                unknown_provenance.append(key)
        fields.update(
            required_feature_keys=tuple(required_keys),
            optional_feature_keys=tuple(optional_keys),
            unresolved_feature_keys=tuple(unresolved),
            leakage_unsafe_required_keys=tuple(leakage_unsafe),
            unknown_provenance_keys=tuple(unknown_provenance),
        )

        if include_preflight:
            report = await self.preflight.check(market_key, now)
            fields.update(preflight_ready=report.ready, preflight_checks=report.checks)

        champion = await self.models.get_champion(market.id)
        if champion is not None:
            fields.update(
                champion_model_key=champion.model_key,
                champion_version=champion.version,
                champion_algorithm=champion.algorithm,
                champion_status=champion.status,
                champion_is_genuinely_trained=champion.is_genuinely_trained(),
                champion_trained_at=champion.trained_at,
            )
            evaluation = await self.model_evaluations.get_latest(champion.id)
            if evaluation is not None:
                fields.update(
                    champion_latest_evaluation_metrics=dict(evaluation.metrics),
                    champion_latest_calibration_report=dict(evaluation.calibration_report),
                    champion_latest_evaluated_at=evaluation.evaluated_at,
                )

        fields.update(
            prediction_count=await self.predictions.count_by_market(market.id),
            outcome_count=await self.outcomes.count_by_market(market.id),
        )

        experiments = await self.experiments.list_by_market(market.id, limit=3)
        latest_selection = next((e for e in experiments if e.config.get("kind") == "model_selection"), None)
        if latest_selection is not None:
            candidate_scores = {
                key.removeprefix("candidate."): value
                for key, value in latest_selection.metrics.items()
                if key.startswith("candidate.")
            }
            ranking_metric = ranking_value = None
            for key, value in latest_selection.metrics.items():
                if key.startswith("ranking."):
                    ranking_metric = key.removeprefix("ranking.")
                    ranking_value = value
                    break
            fields.update(
                latest_experiment_id=str(latest_selection.id),
                latest_experiment_created_at=latest_selection.created_at,
                baseline_candidate_algorithms=tuple(latest_selection.config.get("baseline_candidates", [])),
                winner_is_baseline=latest_selection.config.get("winner_is_baseline"),
                winning_algorithm=latest_selection.config.get("winning_algorithm"),
                candidate_scores=candidate_scores,
                ranking_metric=ranking_metric,
                ranking_value=ranking_value,
            )

        return MarketAuditRecord(**fields)

    async def audit_all(self, now: datetime, *, include_preflight: bool = True) -> tuple[MarketAuditRecord, ...]:
        markets = await self.markets.list_all()
        records = []
        for market in markets:
            records.append(await self.audit_market(market.market_key, now, include_preflight=include_preflight))
        return tuple(records)
