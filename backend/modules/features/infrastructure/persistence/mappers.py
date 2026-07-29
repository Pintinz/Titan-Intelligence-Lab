from __future__ import annotations

import uuid

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
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
    FeatureValidationReportId,
    FeatureValueId,
    QualityFlag,
    ValidationStatus,
)
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

_VALUE_TYPES = {"int": int, "float": float, "str": str, "bool": bool}


def encode_feature_value(value: float | int | str | bool) -> dict:
    # bool is an int subclass — check it first or every bool gets stored as "int".
    if isinstance(value, bool):
        return {"type": "bool", "v": value}
    if isinstance(value, int):
        return {"type": "int", "v": value}
    if isinstance(value, float):
        return {"type": "float", "v": value}
    return {"type": "str", "v": value}


def decode_feature_value(payload: dict) -> float | int | str | bool:
    return _VALUE_TYPES[payload["type"]](payload["v"])


def definition_to_domain(model: FeatureDefinitionModel) -> FeatureDefinition:
    expected_range = (
        (model.expected_range_low, model.expected_range_high)
        if model.expected_range_low is not None and model.expected_range_high is not None
        else None
    )
    return FeatureDefinition(
        id=FeatureDefinitionId(model.id),
        feature_key=FeatureKey(model.feature_key),
        name=model.name,
        description=model.description,
        sport_code=model.sport_code,
        category=FeatureCategory(model.category),
        formula=model.formula,
        data_type=FeatureDataType(model.data_type),
        owner=model.owner,
        entity_type=EntityType(model.entity_type),
        unit=model.unit,
        expected_range=expected_range,
        update_frequency=model.update_frequency,
        online_ttl_seconds=model.online_ttl_seconds,
        source_provider_key=model.source_provider_key,
        version=model.version,
        status=FeatureStatus(model.status),
        dependencies=tuple(FeatureKey(d) for d in model.dependencies),
        leakage_reviewed=model.leakage_reviewed,
        reviewed_by=model.reviewed_by,
        reviewed_at=model.reviewed_at,
        rejection_reason=model.rejection_reason,
        deprecated_at=model.deprecated_at,
    )


def definition_to_model(
    entity: FeatureDefinition, model: FeatureDefinitionModel | None = None
) -> FeatureDefinitionModel:
    model = model or FeatureDefinitionModel(id=entity.id.value)
    model.feature_key = entity.feature_key.value
    model.name = entity.name
    model.description = entity.description
    model.sport_code = entity.sport_code
    model.category = entity.category.value
    model.formula = entity.formula
    model.data_type = entity.data_type.value
    model.owner = entity.owner
    model.entity_type = entity.entity_type.value
    model.unit = entity.unit
    model.expected_range_low = entity.expected_range[0] if entity.expected_range else None
    model.expected_range_high = entity.expected_range[1] if entity.expected_range else None
    model.update_frequency = entity.update_frequency
    model.online_ttl_seconds = entity.online_ttl_seconds
    model.source_provider_key = entity.source_provider_key
    model.version = entity.version
    model.status = entity.status.value
    model.dependencies = [d.value for d in entity.dependencies]
    model.leakage_reviewed = entity.leakage_reviewed
    model.reviewed_by = entity.reviewed_by
    model.reviewed_at = entity.reviewed_at
    model.rejection_reason = entity.rejection_reason
    model.deprecated_at = entity.deprecated_at
    return model


def version_snapshot_to_domain(model: FeatureDefinitionVersionModel) -> FeatureDefinitionVersionSnapshot:
    return FeatureDefinitionVersionSnapshot(
        feature_key=FeatureKey(model.feature_key),
        version=model.version,
        snapshot=_snapshot_definition(model.snapshot),
        recorded_at=model.recorded_at,
    )


def _snapshot_definition(payload: dict) -> FeatureDefinition:
    expected_range = tuple(payload["expected_range"]) if payload.get("expected_range") else None
    return FeatureDefinition(
        id=FeatureDefinitionId(uuid.UUID(payload["id"])),
        feature_key=FeatureKey(payload["feature_key"]),
        name=payload["name"],
        description=payload["description"],
        sport_code=payload["sport_code"],
        category=FeatureCategory(payload["category"]),
        formula=payload["formula"],
        data_type=FeatureDataType(payload["data_type"]),
        owner=payload["owner"],
        entity_type=EntityType(payload["entity_type"]),
        unit=payload.get("unit"),
        expected_range=expected_range,
        update_frequency=payload.get("update_frequency", "unspecified"),
        online_ttl_seconds=payload.get("online_ttl_seconds", 3600),
        source_provider_key=payload.get("source_provider_key"),
        version=payload["version"],
        status=FeatureStatus(payload["status"]),
        dependencies=tuple(FeatureKey(d) for d in payload.get("dependencies", [])),
        leakage_reviewed=payload.get("leakage_reviewed", False),
    )


def version_snapshot_to_model(entity: FeatureDefinitionVersionSnapshot) -> FeatureDefinitionVersionModel:
    d = entity.snapshot
    payload = {
        "id": str(d.id.value),
        "feature_key": d.feature_key.value,
        "name": d.name,
        "description": d.description,
        "sport_code": d.sport_code,
        "category": d.category.value,
        "formula": d.formula,
        "data_type": d.data_type.value,
        "owner": d.owner,
        "entity_type": d.entity_type.value,
        "unit": d.unit,
        "expected_range": list(d.expected_range) if d.expected_range else None,
        "update_frequency": d.update_frequency,
        "online_ttl_seconds": d.online_ttl_seconds,
        "source_provider_key": d.source_provider_key,
        "version": d.version,
        "status": d.status.value,
        "dependencies": [dep.value for dep in d.dependencies],
        "leakage_reviewed": d.leakage_reviewed,
    }
    return FeatureDefinitionVersionModel(
        feature_key=entity.feature_key.value, version=entity.version, snapshot=payload, recorded_at=entity.recorded_at
    )


def value_to_domain(model: FeatureValueModel) -> FeatureValue:
    return FeatureValue(
        id=FeatureValueId(model.id),
        feature_key=FeatureKey(model.feature_key),
        entity_type=EntityType(model.entity_type),
        entity_id=model.entity_id,
        as_of=model.as_of,
        value=decode_feature_value(model.value),
        quality_flags=tuple(QualityFlag(f) for f in model.quality_flags),
    )


def value_to_model(entity: FeatureValue) -> FeatureValueModel:
    return FeatureValueModel(
        id=entity.id.value,
        feature_key=entity.feature_key.value,
        entity_type=entity.entity_type.value,
        entity_id=entity.entity_id,
        as_of=entity.as_of,
        value=encode_feature_value(entity.value),
        quality_flags=[f.value for f in entity.quality_flags],
    )


def lineage_edge_to_domain(model: FeatureLineageEdgeModel) -> FeatureLineageEdge:
    return FeatureLineageEdge(
        feature_key=FeatureKey(model.feature_key), depends_on_feature_key=FeatureKey(model.depends_on_feature_key)
    )


def lineage_edge_to_model(entity: FeatureLineageEdge) -> FeatureLineageEdgeModel:
    return FeatureLineageEdgeModel(
        feature_key=entity.feature_key.value, depends_on_feature_key=entity.depends_on_feature_key.value
    )


def drift_report_to_domain(model: FeatureDriftReportModel) -> FeatureDriftReport:
    return FeatureDriftReport(
        feature_key=FeatureKey(model.feature_key),
        window=model.window,
        drift_score=model.drift_score,
        method=model.method,
        detected_at=model.detected_at,
    )


def drift_report_to_model(entity: FeatureDriftReport) -> FeatureDriftReportModel:
    return FeatureDriftReportModel(
        feature_key=entity.feature_key.value,
        window=entity.window,
        drift_score=entity.drift_score,
        method=entity.method,
        detected_at=entity.detected_at,
    )


def validation_report_to_domain(model: FeatureValidationReportModel) -> FeatureValidationReport:
    return FeatureValidationReport(
        id=FeatureValidationReportId(model.id),
        feature_key=FeatureKey(model.feature_key),
        validated_at=model.validated_at,
        sample_size=model.sample_size,
        quality_score=model.quality_score,
        freshness_score=model.freshness_score,
        reliability_score=model.reliability_score,
        completeness_score=model.completeness_score,
        missing_pct=model.missing_pct,
        outlier_pct=model.outlier_pct,
        null_pct=model.null_pct,
        invalid_pct=model.invalid_pct,
        duplicate_pct=model.duplicate_pct,
        coverage_pct=model.coverage_pct,
        status=ValidationStatus(model.status),
        issues=tuple(model.issues),
    )


def validation_report_to_model(entity: FeatureValidationReport) -> FeatureValidationReportModel:
    return FeatureValidationReportModel(
        id=entity.id.value,
        feature_key=entity.feature_key.value,
        validated_at=entity.validated_at,
        sample_size=entity.sample_size,
        quality_score=entity.quality_score,
        freshness_score=entity.freshness_score,
        reliability_score=entity.reliability_score,
        completeness_score=entity.completeness_score,
        missing_pct=entity.missing_pct,
        outlier_pct=entity.outlier_pct,
        null_pct=entity.null_pct,
        invalid_pct=entity.invalid_pct,
        duplicate_pct=entity.duplicate_pct,
        coverage_pct=entity.coverage_pct,
        status=entity.status.value,
        issues=list(entity.issues),
    )


def computation_log_to_domain(model: FeatureComputationLogModel) -> FeatureComputationLog:
    return FeatureComputationLog(
        feature_key=FeatureKey(model.feature_key),
        recorded_at=model.recorded_at,
        duration_ms=model.duration_ms,
        memory_bytes=model.memory_bytes,
    )


def computation_log_to_model(entity: FeatureComputationLog) -> FeatureComputationLogModel:
    return FeatureComputationLogModel(
        feature_key=entity.feature_key.value,
        recorded_at=entity.recorded_at,
        duration_ms=entity.duration_ms,
        memory_bytes=entity.memory_bytes,
    )


def consumer_to_domain(model: FeatureConsumerModel) -> FeatureConsumer:
    return FeatureConsumer(
        feature_key=FeatureKey(model.feature_key), consumer_key=model.consumer_key, registered_at=model.registered_at
    )


def consumer_to_model(entity: FeatureConsumer) -> FeatureConsumerModel:
    return FeatureConsumerModel(
        feature_key=entity.feature_key.value, consumer_key=entity.consumer_key, registered_at=entity.registered_at
    )


def usage_record_to_domain(model: FeatureUsageRecordModel) -> FeatureUsageRecord:
    return FeatureUsageRecord(feature_key=FeatureKey(model.feature_key), window_key=model.window_key, read_count=model.read_count)


def usage_record_to_model(
    entity: FeatureUsageRecord, model: FeatureUsageRecordModel | None = None
) -> FeatureUsageRecordModel:
    model = model or FeatureUsageRecordModel(feature_key=entity.feature_key.value, window_key=entity.window_key)
    model.read_count = entity.read_count
    return model
