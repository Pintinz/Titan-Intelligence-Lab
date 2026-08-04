from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.alerts.domain.entities import AlertEvent
from modules.alerts.domain.value_objects import AlertEventId
from modules.alerts.infrastructure.persistence import mappers
from modules.alerts.infrastructure.persistence.models import AlertEventModel
from modules.identity.domain.value_objects import UserId


@dataclass
class SqlAlchemyAlertEventRepository:
    session: AsyncSession

    async def add(self, event: AlertEvent) -> AlertEvent:
        model = mappers.event_to_model(event)
        self.session.add(model)
        await self.session.flush()
        return mappers.event_to_domain(model)

    async def get(self, event_id: AlertEventId) -> AlertEvent | None:
        stmt = select(AlertEventModel).where(AlertEventModel.id == event_id.value)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.event_to_domain(model) if model else None

    async def list_for_user(self, user_id: UserId, unread_only: bool = False, limit: int = 50) -> list[AlertEvent]:
        conditions = [AlertEventModel.user_id == user_id.value]
        if unread_only:
            conditions.append(AlertEventModel.read_at.is_(None))
        stmt = select(AlertEventModel).where(*conditions).order_by(AlertEventModel.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.event_to_domain(row) for row in result.scalars().all()]

    async def mark_read(self, event_id: AlertEventId, now: datetime) -> None:
        model = await self.session.get(AlertEventModel, event_id.value)
        if model is not None:
            model.read_at = now
            self.session.add(model)
            await self.session.flush()

    async def count_unread(self, user_id: UserId) -> int:
        stmt = select(func.count()).select_from(AlertEventModel).where(
            AlertEventModel.user_id == user_id.value, AlertEventModel.read_at.is_(None)
        )
        return (await self.session.execute(stmt)).scalar_one()
