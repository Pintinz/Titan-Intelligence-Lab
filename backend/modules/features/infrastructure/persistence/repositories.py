from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.features.domain.entities import (
    FeatureComputationLog,
    FeatureConsumer,
    FeatureDefinition,
    FeatureDefinitionVersionSnapshot,
    FeatureDriftReport,
    FeatureLineageEdge,
    FeatureUsageRecord,
    FeatureValidationReport,
    FeatureValue,
)
from modules.features.domain.value_objects import EntityType, FeatureKey
from modules.features.infrastructure.persistence import mappers
from modules.features.infrastructure.persistence.models import (
    FeatureComputationLogModel,
    FeatureConsumerModel,
    FeatureDefinitionModel,
    FeatureDefinitionVersionModel,
    FeatureDriftReportModel,
    FeatureLineageEdgeModel,
    FeatureUsageRecordModel,
    FeatureValidationReportModel,
    FeatureValueModel,
)


@dataclass
class SqlAlchemyFeatureDefinitionRepository:
    session: AsyncSession

    async def get(self, feature_key: FeatureKey) -> FeatureDefinition | None:
        stmt = select(FeatureDefinitionModel).where(FeatureDefinitionModel.feature_key == feature_key.value)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.definition_to_domain(model) if model else None

    async def list_by_sport(self, sport_code: str) -> list[FeatureDefinition]:
        stmt = select(FeatureDefinitionModel).where(FeatureDefinitionModel.sport_code == sport_code)
        result = await self.session.execute(stmt)
        return [mappers.definition_to_domain(row) for row in result.scalars().all()]

    async def list_all(self) -> list[FeatureDefinition]:
        result = await self.session.execute(select(FeatureDefinitionModel))
        return [mappers.definition_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, definition: FeatureDefinition) -> FeatureDefinition:
        stmt = select(FeatureDefinitionModel).where(FeatureDefinitionModel.feature_key == definition.feature_key.value)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        model = mappers.definition_to_model(definition, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.definition_to_domain(model)


@dataclass
class SqlAlchemyFeatureVersionRepository:
    session: AsyncSession

    async def record(self, snapshot: FeatureDefinitionVersionSnapshot) -> FeatureDefinitionVersionSnapshot:
        model = mappers.version_snapshot_to_model(snapshot)
        self.session.add(model)
        await self.session.flush()
        return mappers.version_snapshot_to_domain(model)

    async def list_by_feature(self, feature_key: FeatureKey) -> list[FeatureDefinitionVersionSnapshot]:
        stmt = (
            select(FeatureDefinitionVersionModel)
            .where(FeatureDefinitionVersionModel.feature_key == feature_key.value)
            .order_by(FeatureDefinitionVersionModel.version.asc())
        )
        result = await self.session.execute(stmt)
        return [mappers.version_snapshot_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyFeatureValueRepository:
    session: AsyncSession

    async def record(self, value: FeatureValue) -> FeatureValue:
        model = mappers.value_to_model(value)
        self.session.add(model)
        await self.session.flush()
        return mappers.value_to_domain(model)

    async def get_latest(
        self, feature_key: FeatureKey, entity_type: EntityType, entity_id: str
    ) -> FeatureValue | None:
        stmt = (
            select(FeatureValueModel)
            .where(
                FeatureValueModel.feature_key == feature_key.value,
                FeatureValueModel.entity_type == entity_type.value,
                FeatureValueModel.entity_id == entity_id,
            )
            .order_by(FeatureValueModel.as_of.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.value_to_domain(model) if model else None

    async def list_history(
        self, feature_key: FeatureKey, entity_type: EntityType, entity_id: str, limit: int = 100
    ) -> list[FeatureValue]:
        stmt = (
            select(FeatureValueModel)
            .where(
                FeatureValueModel.feature_key == feature_key.value,
                FeatureValueModel.entity_type == entity_type.value,
                FeatureValueModel.entity_id == entity_id,
            )
            .order_by(FeatureValueModel.as_of.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.value_to_domain(row) for row in result.scalars().all()]

    async def list_all_recent(
        self, feature_key: FeatureKey, since: datetime | None = None, limit: int = 5000
    ) -> list[FeatureValue]:
        conditions = [FeatureValueModel.feature_key == feature_key.value]
        if since is not None:
            conditions.append(FeatureValueModel.as_of >= since)
        stmt = select(FeatureValueModel).where(*conditions).order_by(FeatureValueModel.as_of.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.value_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyFeatureLineageRepository:
    session: AsyncSession

    async def add_edge(self, edge: FeatureLineageEdge) -> FeatureLineageEdge:
        stmt = select(FeatureLineageEdgeModel).where(
            FeatureLineageEdgeModel.feature_key == edge.feature_key.value,
            FeatureLineageEdgeModel.depends_on_feature_key == edge.depends_on_feature_key.value,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return mappers.lineage_edge_to_domain(existing)
        model = mappers.lineage_edge_to_model(edge)
        self.session.add(model)
        await self.session.flush()
        return mappers.lineage_edge_to_domain(model)

    async def list_dependencies(self, feature_key: FeatureKey) -> list[FeatureKey]:
        stmt = select(FeatureLineageEdgeModel).where(FeatureLineageEdgeModel.feature_key == feature_key.value)
        result = await self.session.execute(stmt)
        return [FeatureKey(row.depends_on_feature_key) for row in result.scalars().all()]

    async def list_dependents(self, feature_key: FeatureKey) -> list[FeatureKey]:
        stmt = select(FeatureLineageEdgeModel).where(
            FeatureLineageEdgeModel.depends_on_feature_key == feature_key.value
        )
        result = await self.session.execute(stmt)
        return [FeatureKey(row.feature_key) for row in result.scalars().all()]


@dataclass
class SqlAlchemyFeatureDriftReportRepository:
    session: AsyncSession

    async def record(self, report: FeatureDriftReport) -> FeatureDriftReport:
        model = mappers.drift_report_to_model(report)
        self.session.add(model)
        await self.session.flush()
        return mappers.drift_report_to_domain(model)

    async def list_by_feature(self, feature_key: FeatureKey, limit: int = 50) -> list[FeatureDriftReport]:
        stmt = (
            select(FeatureDriftReportModel)
            .where(FeatureDriftReportModel.feature_key == feature_key.value)
            .order_by(FeatureDriftReportModel.detected_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.drift_report_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyFeatureValidationReportRepository:
    session: AsyncSession

    async def record(self, report: FeatureValidationReport) -> FeatureValidationReport:
        model = mappers.validation_report_to_model(report)
        self.session.add(model)
        await self.session.flush()
        return mappers.validation_report_to_domain(model)

    async def get_latest(self, feature_key: FeatureKey) -> FeatureValidationReport | None:
        stmt = (
            select(FeatureValidationReportModel)
            .where(FeatureValidationReportModel.feature_key == feature_key.value)
            .order_by(FeatureValidationReportModel.validated_at.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.validation_report_to_domain(model) if model else None

    async def list_by_feature(self, feature_key: FeatureKey, limit: int = 50) -> list[FeatureValidationReport]:
        stmt = (
            select(FeatureValidationReportModel)
            .where(FeatureValidationReportModel.feature_key == feature_key.value)
            .order_by(FeatureValidationReportModel.validated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.validation_report_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyFeatureComputationLogRepository:
    session: AsyncSession

    async def record(self, log: FeatureComputationLog) -> FeatureComputationLog:
        model = mappers.computation_log_to_model(log)
        self.session.add(model)
        await self.session.flush()
        return mappers.computation_log_to_domain(model)

    async def list_since(self, feature_key: FeatureKey, since: datetime) -> list[FeatureComputationLog]:
        stmt = select(FeatureComputationLogModel).where(
            FeatureComputationLogModel.feature_key == feature_key.value,
            FeatureComputationLogModel.recorded_at >= since,
        )
        result = await self.session.execute(stmt)
        return [mappers.computation_log_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyFeatureConsumerRepository:
    session: AsyncSession

    async def register(self, consumer: FeatureConsumer) -> FeatureConsumer:
        stmt = select(FeatureConsumerModel).where(
            FeatureConsumerModel.feature_key == consumer.feature_key.value,
            FeatureConsumerModel.consumer_key == consumer.consumer_key,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return mappers.consumer_to_domain(existing)
        model = mappers.consumer_to_model(consumer)
        self.session.add(model)
        await self.session.flush()
        return mappers.consumer_to_domain(model)

    async def list_by_feature(self, feature_key: FeatureKey) -> list[FeatureConsumer]:
        stmt = select(FeatureConsumerModel).where(FeatureConsumerModel.feature_key == feature_key.value)
        result = await self.session.execute(stmt)
        return [mappers.consumer_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyFeatureUsageRepository:
    session: AsyncSession

    async def get(self, feature_key: FeatureKey, window_key: str) -> FeatureUsageRecord | None:
        stmt = select(FeatureUsageRecordModel).where(
            FeatureUsageRecordModel.feature_key == feature_key.value,
            FeatureUsageRecordModel.window_key == window_key,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.usage_record_to_domain(model) if model else None

    async def upsert(self, record: FeatureUsageRecord) -> FeatureUsageRecord:
        stmt = select(FeatureUsageRecordModel).where(
            FeatureUsageRecordModel.feature_key == record.feature_key.value,
            FeatureUsageRecordModel.window_key == record.window_key,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        model = mappers.usage_record_to_model(record, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.usage_record_to_domain(model)

    async def list_since(self, feature_key: FeatureKey, since_window_key: str) -> list[FeatureUsageRecord]:
        stmt = select(FeatureUsageRecordModel).where(
            FeatureUsageRecordModel.feature_key == feature_key.value,
            FeatureUsageRecordModel.window_key >= since_window_key,
        )
        result = await self.session.execute(stmt)
        return [mappers.usage_record_to_domain(row) for row in result.scalars().all()]
