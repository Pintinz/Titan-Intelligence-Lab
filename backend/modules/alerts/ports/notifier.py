from __future__ import annotations

from datetime import datetime
from typing import Protocol

from modules.alerts.domain.entities import AlertEvent
from modules.alerts.domain.value_objects import AlertType
from modules.watchlist.domain.value_objects import WatchlistEntityType


class AlertNotifierPort(Protocol):
    """What a real trigger (fixture status transition, prediction republish) depends on to emit
    alerts — deliberately narrower than the full AlertService, so ingestion/predictions couple to
    one method instead of the whole alerts module's internals."""

    async def notify_watchers(
        self,
        entity_type: WatchlistEntityType,
        entity_ref: str,
        alert_type: AlertType,
        title: str,
        body: str,
        now: datetime,
    ) -> list[AlertEvent]: ...
