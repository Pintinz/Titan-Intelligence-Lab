from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.alerts.domain.value_objects import AlertEventId, AlertType
from modules.identity.domain.value_objects import UserId
from modules.watchlist.domain.value_objects import WatchlistEntityType


@dataclass
class AlertEvent:
    """One fired alert delivered to one user — always because that user was following
    ``entity_type``/``entity_ref`` in their Watchlist at the moment the real trigger fired
    (AlertService.notify_watchers only ever creates these for actual watchers, never
    speculatively)."""

    id: AlertEventId
    user_id: UserId
    alert_type: AlertType
    entity_type: WatchlistEntityType
    entity_ref: str
    title: str
    body: str
    created_at: datetime
    read_at: datetime | None = None
