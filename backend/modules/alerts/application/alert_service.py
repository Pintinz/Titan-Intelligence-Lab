from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from modules.alerts.domain.entities import AlertEvent
from modules.alerts.domain.value_objects import AlertEventId, AlertType
from modules.alerts.ports.repositories import AlertEventRepositoryPort
from modules.identity.domain.value_objects import UserId
from modules.watchlist.domain.value_objects import WatchlistEntityType
from modules.watchlist.ports.repositories import WatchlistRepositoryPort


class AlertEventNotFoundError(Exception):
    pass


class NotAlertEventOwnerError(Exception):
    pass


@dataclass
class AlertService:
    events: AlertEventRepositoryPort
    watchlist: WatchlistRepositoryPort

    async def notify_watchers(
        self,
        entity_type: WatchlistEntityType,
        entity_ref: str,
        alert_type: AlertType,
        title: str,
        body: str,
        now: datetime,
    ) -> list[AlertEvent]:
        """Only ever creates events for users genuinely following entity_type/entity_ref right
        now — never speculative, never for users who aren't watching."""
        watcher_ids = await self.watchlist.list_watchers(entity_type, entity_ref)
        created: list[AlertEvent] = []
        for user_id in watcher_ids:
            event = AlertEvent(
                id=AlertEventId(uuid.uuid4()), user_id=user_id, alert_type=alert_type,
                entity_type=entity_type, entity_ref=entity_ref, title=title, body=body, created_at=now,
            )
            created.append(await self.events.add(event))
        return created

    async def list_for_user(self, user_id: UserId, unread_only: bool = False, limit: int = 50) -> list[AlertEvent]:
        return await self.events.list_for_user(user_id, unread_only, limit)

    async def unread_count(self, user_id: UserId) -> int:
        return await self.events.count_unread(user_id)

    async def mark_read(self, user_id: UserId, event_id: AlertEventId, now: datetime) -> None:
        event = await self.events.get(event_id)
        if event is None:
            raise AlertEventNotFoundError(str(event_id))
        if event.user_id != user_id:
            raise NotAlertEventOwnerError(str(event_id))
        await self.events.mark_read(event_id, now)
