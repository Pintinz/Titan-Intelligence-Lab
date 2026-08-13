"""Concrete SQLAlchemy repository implementations of modules.predictions.ports.repositories.

Application-layer code depends only on the ports, never on these classes directly — they're
wired up only in each app's composition module (docs/architecture.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.predictions.domain.dataset import Dataset, DatasetId
from modules.predictions.domain.entities import (
    Experiment,
    FeatureMarketMapping,
    MarketDefinition,
    ModelDefinition,
    ModelEvaluation,
    Prediction,
    PredictionAudit,
    PredictionOutcome,
)
from modules.predictions.domain.value_objects import (
    ExperimentId,
    MarketId,
    MarketStatus,
    ModelId,
    ModelStatus,
    PredictionId,
    PredictionStatus,
)
from modules.predictions.infrastructure.persistence import mappers
from modules.predictions.infrastructure.persistence.models import (
    DatasetModel,
    ExperimentModel,
    FeatureMarketMappingModel,
    MarketDefinitionModel,
    ModelDefinitionModel,
    ModelEvaluationModel,
    PredictionAuditModel,
    PredictionModel,
    PredictionOutcomeModel,
)


@dataclass
class SqlAlchemyMarketRepository:
    session: AsyncSession

    async def get(self, market_id: MarketId) -> MarketDefinition | None:
        model = await self.session.get(MarketDefinitionModel, market_id.value)
        return mappers.market_to_domain(model) if model else None

    async def get_by_key(self, market_key: str) -> MarketDefinition | None:
        result = await self.session.execute(
            select(MarketDefinitionModel).where(MarketDefinitionModel.market_key == market_key)
        )
        model = result.scalar_one_or_none()
        return mappers.market_to_domain(model) if model else None

    async def list_by_sport(self, sport_code: str) -> list[MarketDefinition]:
        result = await self.session.execute(
            select(MarketDefinitionModel).where(MarketDefinitionModel.sport_code == sport_code)
        )
        return [mappers.market_to_domain(row) for row in result.scalars().all()]

    async def list_by_status(self, status: MarketStatus) -> list[MarketDefinition]:
        result = await self.session.execute(
            select(MarketDefinitionModel).where(MarketDefinitionModel.status == status.value)
        )
        return [mappers.market_to_domain(row) for row in result.scalars().all()]

    async def list_all(self) -> list[MarketDefinition]:
        result = await self.session.execute(select(MarketDefinitionModel))
        return [mappers.market_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, market: MarketDefinition) -> MarketDefinition:
        existing = await self.session.get(MarketDefinitionModel, market.id.value)
        model = mappers.market_to_model(market, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.market_to_domain(model)


@dataclass
class SqlAlchemyFeatureMarketMappingRepository:
    session: AsyncSession

    async def list_by_market(self, market_id: MarketId) -> list[FeatureMarketMapping]:
        result = await self.session.execute(
            select(FeatureMarketMappingModel).where(FeatureMarketMappingModel.market_id == market_id.value)
        )
        return [mappers.feature_mapping_to_domain(row) for row in result.scalars().all()]

    async def list_by_feature(self, feature_key: str) -> list[FeatureMarketMapping]:
        result = await self.session.execute(
            select(FeatureMarketMappingModel).where(FeatureMarketMappingModel.feature_key == feature_key)
        )
        return [mappers.feature_mapping_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, mapping: FeatureMarketMapping) -> FeatureMarketMapping:
        existing = await self.session.get(FeatureMarketMappingModel, mapping.id.value)
        model = mappers.feature_mapping_to_model(mapping, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.feature_mapping_to_domain(model)


@dataclass
class SqlAlchemyModelRepository:
    session: AsyncSession

    async def get(self, model_id: ModelId) -> ModelDefinition | None:
        model = await self.session.get(ModelDefinitionModel, model_id.value)
        return mappers.model_definition_to_domain(model) if model else None

    async def get_by_key_version(self, model_key: str, version: int) -> ModelDefinition | None:
        result = await self.session.execute(
            select(ModelDefinitionModel).where(
                ModelDefinitionModel.model_key == model_key, ModelDefinitionModel.version == version
            )
        )
        model = result.scalar_one_or_none()
        return mappers.model_definition_to_domain(model) if model else None

    async def list_by_market(self, market_id: MarketId) -> list[ModelDefinition]:
        result = await self.session.execute(
            select(ModelDefinitionModel).where(ModelDefinitionModel.market_id == market_id.value)
        )
        return [mappers.model_definition_to_domain(row) for row in result.scalars().all()]

    async def get_champion(self, market_id: MarketId) -> ModelDefinition | None:
        result = await self.session.execute(
            select(ModelDefinitionModel).where(
                ModelDefinitionModel.market_id == market_id.value,
                ModelDefinitionModel.status == ModelStatus.CHAMPION.value,
            )
        )
        model = result.scalar_one_or_none()
        return mappers.model_definition_to_domain(model) if model else None

    async def list_by_status(self, market_id: MarketId, status: ModelStatus) -> list[ModelDefinition]:
        result = await self.session.execute(
            select(ModelDefinitionModel).where(
                ModelDefinitionModel.market_id == market_id.value, ModelDefinitionModel.status == status.value
            )
        )
        return [mappers.model_definition_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, model: ModelDefinition) -> ModelDefinition:
        existing = await self.session.get(ModelDefinitionModel, model.id.value)
        row = mappers.model_definition_to_model(model, existing)
        self.session.add(row)
        await self.session.flush()
        return mappers.model_definition_to_domain(row)


@dataclass
class SqlAlchemyPredictionRepository:
    session: AsyncSession

    async def get(self, prediction_id: PredictionId) -> Prediction | None:
        model = await self.session.get(PredictionModel, prediction_id.value)
        return mappers.prediction_to_domain(model) if model else None

    async def record(self, prediction: Prediction) -> Prediction:
        model = mappers.prediction_to_model(prediction)
        self.session.add(model)
        await self.session.flush()
        return mappers.prediction_to_domain(model)

    async def update(self, prediction: Prediction) -> Prediction:
        existing = await self.session.get(PredictionModel, prediction.id.value)
        model = mappers.prediction_to_model(prediction, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.prediction_to_domain(model)

    async def list_by_subject(self, subject_ref: str, market_id: MarketId | None = None) -> list[Prediction]:
        stmt = select(PredictionModel).where(PredictionModel.subject_ref == subject_ref)
        if market_id is not None:
            stmt = stmt.where(PredictionModel.market_id == market_id.value)
        stmt = stmt.order_by(PredictionModel.generated_at.desc())
        result = await self.session.execute(stmt)
        return [mappers.prediction_to_domain(row) for row in result.scalars().all()]

    async def list_by_market(
        self, market_id: MarketId, status: PredictionStatus | None = None, limit: int = 100
    ) -> list[Prediction]:
        stmt = select(PredictionModel).where(PredictionModel.market_id == market_id.value)
        if status is not None:
            stmt = stmt.where(PredictionModel.status == status.value)
        stmt = stmt.order_by(PredictionModel.generated_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.prediction_to_domain(row) for row in result.scalars().all()]

    async def list_recent(self, limit: int = 100) -> list[Prediction]:
        stmt = select(PredictionModel).order_by(PredictionModel.generated_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.prediction_to_domain(row) for row in result.scalars().all()]

    async def get_latest_for_subject(self, subject_ref: str, market_id: MarketId) -> Prediction | None:
        stmt = (
            select(PredictionModel)
            .where(PredictionModel.subject_ref == subject_ref, PredictionModel.market_id == market_id.value)
            .order_by(PredictionModel.generated_at.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.prediction_to_domain(model) if model else None


@dataclass
class SqlAlchemyPredictionOutcomeRepository:
    session: AsyncSession

    async def record(self, outcome: PredictionOutcome) -> PredictionOutcome:
        model = mappers.prediction_outcome_to_model(outcome)
        self.session.add(model)
        await self.session.flush()
        return mappers.prediction_outcome_to_domain(model)

    async def get_for_prediction(self, prediction_id: PredictionId) -> PredictionOutcome | None:
        result = await self.session.execute(
            select(PredictionOutcomeModel).where(PredictionOutcomeModel.prediction_id == prediction_id.value)
        )
        model = result.scalar_one_or_none()
        return mappers.prediction_outcome_to_domain(model) if model else None

    async def list_by_market(self, market_id: MarketId, limit: int = 500) -> list[PredictionOutcome]:
        stmt = (
            select(PredictionOutcomeModel)
            .join(PredictionModel, PredictionModel.id == PredictionOutcomeModel.prediction_id)
            .where(PredictionModel.market_id == market_id.value)
            .order_by(PredictionOutcomeModel.evaluated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.prediction_outcome_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyModelEvaluationRepository:
    session: AsyncSession

    async def record(self, evaluation: ModelEvaluation) -> ModelEvaluation:
        model = mappers.model_evaluation_to_model(evaluation)
        self.session.add(model)
        await self.session.flush()
        return mappers.model_evaluation_to_domain(model)

    async def list_by_model(self, model_id: ModelId, limit: int = 50) -> list[ModelEvaluation]:
        stmt = (
            select(ModelEvaluationModel)
            .where(ModelEvaluationModel.model_id == model_id.value)
            .order_by(ModelEvaluationModel.evaluated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.model_evaluation_to_domain(row) for row in result.scalars().all()]

    async def get_latest(self, model_id: ModelId) -> ModelEvaluation | None:
        stmt = (
            select(ModelEvaluationModel)
            .where(ModelEvaluationModel.model_id == model_id.value)
            .order_by(ModelEvaluationModel.evaluated_at.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.model_evaluation_to_domain(model) if model else None


@dataclass
class SqlAlchemyExperimentRepository:
    session: AsyncSession

    async def get(self, experiment_id: ExperimentId) -> Experiment | None:
        model = await self.session.get(ExperimentModel, experiment_id.value)
        return mappers.experiment_to_domain(model) if model else None

    async def record(self, experiment: Experiment) -> Experiment:
        model = mappers.experiment_to_model(experiment)
        self.session.add(model)
        await self.session.flush()
        return mappers.experiment_to_domain(model)

    async def update(self, experiment: Experiment) -> Experiment:
        existing = await self.session.get(ExperimentModel, experiment.id.value)
        model = mappers.experiment_to_model(experiment, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.experiment_to_domain(model)

    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[Experiment]:
        stmt = (
            select(ExperimentModel)
            .where(ExperimentModel.market_id == market_id.value)
            .order_by(ExperimentModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.experiment_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyPredictionAuditRepository:
    session: AsyncSession

    async def record(self, audit: PredictionAudit) -> PredictionAudit:
        model = mappers.prediction_audit_to_model(audit)
        self.session.add(model)
        await self.session.flush()
        return mappers.prediction_audit_to_domain(model)

    async def list_by_prediction(self, prediction_id: PredictionId) -> list[PredictionAudit]:
        stmt = (
            select(PredictionAuditModel)
            .where(PredictionAuditModel.prediction_id == prediction_id.value)
            .order_by(PredictionAuditModel.occurred_at.asc())
        )
        result = await self.session.execute(stmt)
        return [mappers.prediction_audit_to_domain(row) for row in result.scalars().all()]

    async def list_recent(self, since: datetime | None = None, limit: int = 200) -> list[PredictionAudit]:
        stmt = select(PredictionAuditModel)
        if since is not None:
            stmt = stmt.where(PredictionAuditModel.occurred_at >= since)
        stmt = stmt.order_by(PredictionAuditModel.occurred_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.prediction_audit_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyDatasetRepository:
    """Milestone 20: closes the `dataset_provenance_persisted` gap `TrainingPreflightService`
    (Milestone 19) surfaced — the `datasets` table has existed since Milestone 4/9
    (`DatasetModel`); this is the first repository to actually read/write it."""

    session: AsyncSession

    async def get(self, dataset_id: DatasetId) -> Dataset | None:
        model = await self.session.get(DatasetModel, dataset_id.value)
        return mappers.dataset_to_domain(model) if model else None

    async def get_latest_version(self, market_id: MarketId) -> Dataset | None:
        stmt = (
            select(DatasetModel)
            .where(DatasetModel.market_id == market_id.value)
            .order_by(DatasetModel.version.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.dataset_to_domain(model) if model else None

    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[Dataset]:
        stmt = (
            select(DatasetModel)
            .where(DatasetModel.market_id == market_id.value)
            .order_by(DatasetModel.version.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.dataset_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, dataset: Dataset) -> Dataset:
        existing = await self.session.get(DatasetModel, dataset.id.value)
        model = mappers.dataset_to_model(dataset, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.dataset_to_domain(model)
