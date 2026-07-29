from __future__ import annotations

from modules.webhooks.domain.entities import WebhookDelivery, WebhookEndpoint
from modules.webhooks.domain.value_objects import DeliveryStatus, WebhookDeliveryId, WebhookEndpointId
from modules.webhooks.infrastructure.persistence.models import WebhookDeliveryModel, WebhookEndpointModel


def endpoint_to_domain(model: WebhookEndpointModel) -> WebhookEndpoint:
    return WebhookEndpoint(
        id=WebhookEndpointId(model.id),
        organization_id=model.organization_id,
        url=model.url,
        signing_secret_encrypted=model.signing_secret_encrypted,
        subscribed_events=list(model.subscribed_events or []),
        is_active=model.is_active,
        created_at=model.created_at,
        rotated_at=model.rotated_at,
    )


def endpoint_to_model(entity: WebhookEndpoint, model: WebhookEndpointModel | None = None) -> WebhookEndpointModel:
    model = model or WebhookEndpointModel(id=entity.id.value)
    model.organization_id = entity.organization_id
    model.url = entity.url
    model.signing_secret_encrypted = entity.signing_secret_encrypted
    model.subscribed_events = list(entity.subscribed_events)
    model.is_active = entity.is_active
    model.rotated_at = entity.rotated_at
    return model


def delivery_to_domain(model: WebhookDeliveryModel) -> WebhookDelivery:
    return WebhookDelivery(
        id=WebhookDeliveryId(model.id),
        endpoint_id=WebhookEndpointId(model.endpoint_id),
        event_type=model.event_type,
        payload=dict(model.payload or {}),
        status=DeliveryStatus(model.status),
        attempt_count=model.attempt_count,
        last_attempted_at=model.last_attempted_at,
        response_status_code=model.response_status_code,
        created_at=model.created_at,
    )


def delivery_to_model(entity: WebhookDelivery, model: WebhookDeliveryModel | None = None) -> WebhookDeliveryModel:
    model = model or WebhookDeliveryModel(
        id=entity.id.value, endpoint_id=entity.endpoint_id.value, event_type=entity.event_type, payload=entity.payload
    )
    model.status = entity.status.value
    model.attempt_count = entity.attempt_count
    model.last_attempted_at = entity.last_attempted_at
    model.response_status_code = entity.response_status_code
    return model
