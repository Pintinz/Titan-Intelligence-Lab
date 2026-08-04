from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.domain.value_objects import UserId
from modules.watchlist.domain.entities import WatchlistEntry
from modules.watchlist.domain.value_objects import WatchlistEntityType, WatchlistEntryId
from modules.watchlist.infrastructure.persistence import mappers
from modules.watchlist.infrastructure.persistence.models import WatchlistEntryModel


@dataclass
class SqlAlchemyWatchlistRepository:
    session: AsyncSession

    async def add(self, entry: WatchlistEntry) -> WatchlistEntry:
        model = mappers.entry_to_model(entry)
        self.session.add(model)
        await self.session.flush()
        return mappers.entry_to_domain(model)

    async def get_by_id(self, entry_id: WatchlistEntryId) -> WatchlistEntry | None:
        stmt = select(WatchlistEntryModel).where(WatchlistEntryModel.id == entry_id.value)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.entry_to_domain(model) if model else None

    async def get_by_entity(
        self, user_id: UserId, entity_type: WatchlistEntityType, entity_ref: str
    ) -> WatchlistEntry | None:
        stmt = select(WatchlistEntryModel).where(
            WatchlistEntryModel.user_id == user_id.value,
            WatchlistEntryModel.entity_type == entity_type.value,
            WatchlistEntryModel.entity_ref == entity_ref,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.entry_to_domain(model) if model else None

    async def remove(self, entry_id: WatchlistEntryId) -> None:
        stmt = select(WatchlistEntryModel).where(WatchlistEntryModel.id == entry_id.value)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()

    async def list_for_user(
        self, user_id: UserId, entity_type: WatchlistEntityType | None = None
    ) -> list[WatchlistEntry]:
        conditions = [WatchlistEntryModel.user_id == user_id.value]
        if entity_type is not None:
            conditions.append(WatchlistEntryModel.entity_type == entity_type.value)
        stmt = select(WatchlistEntryModel).where(*conditions).order_by(WatchlistEntryModel.created_at.desc())
        result = await self.session.execute(stmt)
        return [mappers.entry_to_domain(row) for row in result.scalars().all()]

    async def list_watchers(self, entity_type: WatchlistEntityType, entity_ref: str) -> list[UserId]:
        stmt = select(WatchlistEntryModel.user_id).where(
            WatchlistEntryModel.entity_type == entity_type.value,
            WatchlistEntryModel.entity_ref == entity_ref,
        )
        result = await self.session.execute(stmt)
        return [UserId(row) for row in result.scalars().all()]
