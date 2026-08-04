from __future__ import annotations

from modules.alerts.domain.entities import AlertEvent
from modules.alerts.domain.value_objects import AlertEventId, AlertType
from modules.alerts.infrastructure.persistence.models import AlertEventModel
from modules.identity.domain.value_objects import UserId
from modules.watchlist.domain.value_objects import WatchlistEntityType


def event_to_domain(model: AlertEventModel) -> AlertEvent:
    return AlertEvent(
        id=AlertEventId(model.id),
        user_id=UserId(model.user_id),
        alert_type=AlertType(model.alert_type),
        entity_type=WatchlistEntityType(model.entity_type),
        entity_ref=model.entity_ref,
        title=model.title,
        body=model.body,
        created_at=model.created_at,
        read_at=model.read_at,
    )


def event_to_model(event: AlertEvent) -> AlertEventModel:
    return AlertEventModel(
        id=event.id.value,
        user_id=event.user_id.value,
        alert_type=event.alert_type.value,
        entity_type=event.entity_type.value,
        entity_ref=event.entity_ref,
        title=event.title,
        body=event.body,
        created_at=event.created_at,
        read_at=event.read_at,
    )
