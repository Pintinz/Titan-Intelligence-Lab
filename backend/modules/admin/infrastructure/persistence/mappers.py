from __future__ import annotations

import uuid

from modules.admin.domain.entities import (
    FeatureFlag,
    ProviderCredential,
    ProviderDefinition,
    ProviderHealthCheck,
    ProviderHealthState,
    ProviderIncident,
    ProviderUsageRecord,
)
from modules.admin.domain.value_objects import (
    CredentialId,
    FlagId,
    HealthStatus,
    IncidentId,
    IncidentSeverity,
    ProviderCategory,
    ProviderId,
    ProviderStatus,
    QuotaPeriod,
)
from modules.admin.infrastructure.persistence.models import (
    FeatureFlagModel,
    ProviderCredentialModel,
    ProviderHealthCheckModel,
    ProviderHealthStateModel,
    ProviderIncidentModel,
    ProviderModel,
    ProviderUsageRecordModel,
)


def provider_to_domain(model: ProviderModel) -> ProviderDefinition:
    return ProviderDefinition(
        id=ProviderId(model.id),
        key=model.key,
        name=model.name,
        category=ProviderCategory(model.category),
        status=ProviderStatus(model.status),
        priority=model.priority,
        daily_quota_limit=model.daily_quota_limit,
        monthly_quota_limit=model.monthly_quota_limit,
        cache_ttl_seconds=model.cache_ttl_seconds,
        poll_interval_seconds=model.poll_interval_seconds,
        base_url=model.base_url,
        auth_type=model.auth_type,
        auth_header_name=model.auth_header_name,
        region=model.region,
        version=model.version,
        environment=model.environment,
        timeout_seconds=model.timeout_seconds,
        retry_count=model.retry_count,
        retry_delay_seconds=model.retry_delay_seconds,
        created_by=str(model.created_by) if model.created_by else None,
        updated_by=str(model.updated_by) if model.updated_by else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
        capability_note=model.capability_note,
        capability_checked_at=model.capability_checked_at,
    )


def provider_to_model(entity: ProviderDefinition, model: ProviderModel | None = None) -> ProviderModel:
    model = model or ProviderModel(id=entity.id.value)
    model.key = entity.key
    model.name = entity.name
    model.category = entity.category.value
    model.status = entity.status.value
    model.priority = entity.priority
    model.daily_quota_limit = entity.daily_quota_limit
    model.monthly_quota_limit = entity.monthly_quota_limit
    model.cache_ttl_seconds = entity.cache_ttl_seconds
    model.poll_interval_seconds = entity.poll_interval_seconds
    model.base_url = entity.base_url
    model.auth_type = entity.auth_type
    model.auth_header_name = entity.auth_header_name
    model.region = entity.region
    model.version = entity.version
    model.environment = entity.environment
    model.timeout_seconds = entity.timeout_seconds
    model.retry_count = entity.retry_count
    model.retry_delay_seconds = entity.retry_delay_seconds
    model.created_by = uuid.UUID(entity.created_by) if entity.created_by else model.created_by
    model.updated_by = uuid.UUID(entity.updated_by) if entity.updated_by else model.updated_by
    model.capability_note = entity.capability_note
    model.capability_checked_at = entity.capability_checked_at
    return model


def credential_to_domain(model: ProviderCredentialModel) -> ProviderCredential:
    return ProviderCredential(
        id=CredentialId(model.id),
        provider_id=ProviderId(model.provider_id),
        label=model.label,
        encrypted_value=model.encrypted_value,
        is_active=model.is_active,
        created_at=model.created_at,
        rotated_at=model.rotated_at,
        expires_at=model.expires_at,
    )


def credential_to_model(
    entity: ProviderCredential, model: ProviderCredentialModel | None = None
) -> ProviderCredentialModel:
    model = model or ProviderCredentialModel(id=entity.id.value)
    model.provider_id = entity.provider_id.value
    model.label = entity.label
    model.encrypted_value = entity.encrypted_value
    model.is_active = entity.is_active
    model.rotated_at = entity.rotated_at
    model.expires_at = entity.expires_at
    # Previously dropped entirely — `add_credential`'s explicit `created_at=now` was silently
    # discarded in favor of the column's own server_default(func.now()), which happened to (very
    # nearly) tie two credentials added moments apart in the same request, undermining the
    # `list_by_provider` ORDER BY created_at DESC fix this same incident needed. `is None` guard
    # keeps the server-default behavior for any caller that genuinely never sets it.
    if entity.created_at is not None:
        model.created_at = entity.created_at
    return model


def usage_to_domain(model: ProviderUsageRecordModel) -> ProviderUsageRecord:
    return ProviderUsageRecord(
        provider_id=ProviderId(model.provider_id),
        period=QuotaPeriod(model.period),
        window_key=model.window_key,
        credential_id=CredentialId(model.credential_id) if model.credential_id else None,
        request_count=model.request_count,
        error_count=model.error_count,
    )


def usage_to_model(
    entity: ProviderUsageRecord, model: ProviderUsageRecordModel | None = None
) -> ProviderUsageRecordModel:
    model = model or ProviderUsageRecordModel(
        provider_id=entity.provider_id.value,
        credential_id=entity.credential_id.value if entity.credential_id else None,
        period=entity.period.value,
        window_key=entity.window_key,
    )
    model.request_count = entity.request_count
    model.error_count = entity.error_count
    return model


def health_check_to_domain(model: ProviderHealthCheckModel) -> ProviderHealthCheck:
    return ProviderHealthCheck(
        provider_id=ProviderId(model.provider_id),
        checked_at=model.checked_at,
        success=model.success,
        latency_ms=model.latency_ms,
        message=model.message,
    )


def health_check_to_model(entity: ProviderHealthCheck) -> ProviderHealthCheckModel:
    return ProviderHealthCheckModel(
        provider_id=entity.provider_id.value,
        checked_at=entity.checked_at,
        success=entity.success,
        latency_ms=entity.latency_ms,
        message=entity.message,
    )


def health_state_to_domain(model: ProviderHealthStateModel) -> ProviderHealthState:
    return ProviderHealthState(
        provider_id=ProviderId(model.provider_id),
        status=HealthStatus(model.status),
        consecutive_failures=model.consecutive_failures,
        consecutive_successes=model.consecutive_successes,
        last_check_at=model.last_check_at,
        last_success_at=model.last_success_at,
        last_failure_at=model.last_failure_at,
        open_incident_id=IncidentId(model.open_incident_id) if model.open_incident_id else None,
    )


def health_state_to_model(
    entity: ProviderHealthState, model: ProviderHealthStateModel | None = None
) -> ProviderHealthStateModel:
    model = model or ProviderHealthStateModel(provider_id=entity.provider_id.value)
    model.status = entity.status.value
    model.consecutive_failures = entity.consecutive_failures
    model.consecutive_successes = entity.consecutive_successes
    model.last_check_at = entity.last_check_at
    model.last_success_at = entity.last_success_at
    model.last_failure_at = entity.last_failure_at
    model.open_incident_id = entity.open_incident_id.value if entity.open_incident_id else None
    return model


def incident_to_domain(model: ProviderIncidentModel) -> ProviderIncident:
    return ProviderIncident(
        id=IncidentId(model.id),
        provider_id=ProviderId(model.provider_id),
        severity=IncidentSeverity(model.severity),
        opened_at=model.opened_at,
        trigger=model.trigger,
        resolved_at=model.resolved_at,
    )


def incident_to_model(
    entity: ProviderIncident, model: ProviderIncidentModel | None = None
) -> ProviderIncidentModel:
    model = model or ProviderIncidentModel(id=entity.id.value)
    model.provider_id = entity.provider_id.value
    model.severity = entity.severity.value
    model.opened_at = entity.opened_at
    model.trigger = entity.trigger
    model.resolved_at = entity.resolved_at
    return model


def feature_flag_to_domain(model: FeatureFlagModel) -> FeatureFlag:
    return FeatureFlag(
        id=FlagId(model.id),
        key=model.key,
        name=model.name,
        description=model.description,
        enabled=model.enabled,
        rollout_percentage=model.rollout_percentage,
        updated_at=model.updated_at,
    )


def feature_flag_to_model(entity: FeatureFlag, model: FeatureFlagModel | None = None) -> FeatureFlagModel:
    model = model or FeatureFlagModel(id=entity.id.value)
    model.key = entity.key
    model.name = entity.name
    model.description = entity.description
    model.enabled = entity.enabled
    model.rollout_percentage = entity.rollout_percentage
    model.updated_at = entity.updated_at
    return model
