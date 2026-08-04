from __future__ import annotations

from datetime import datetime
from typing import Protocol

from modules.alerts.domain.entities import AlertEvent
from modules.alerts.domain.value_objects import AlertEventId
from modules.identity.domain.value_objects import UserId


class AlertEventRepositoryPort(Protocol):
    async def add(self, event: AlertEvent) -> AlertEvent: ...

    async def get(self, event_id: AlertEventId) -> AlertEvent | None: ...

    async def list_for_user(
        self, user_id: UserId, unread_only: bool = False, limit: int = 50
    ) -> list[AlertEvent]: ...

    async def mark_read(self, event_id: AlertEventId, now: datetime) -> None: ...

    async def count_unread(self, user_id: UserId) -> int: ...
