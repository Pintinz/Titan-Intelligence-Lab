from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from modules.identity.domain.value_objects import UserId
from modules.watchlist.domain.entities import WatchlistEntry
from modules.watchlist.domain.value_objects import WatchlistEntityType, WatchlistEntryId
from modules.watchlist.ports.repositories import WatchlistRepositoryPort


class WatchlistEntryNotFoundError(Exception):
    pass


class NotWatchlistEntryOwnerError(Exception):
    pass


@dataclass
class WatchlistService:
    repository: WatchlistRepositoryPort

    async def follow(
        self, user_id: UserId, entity_type: WatchlistEntityType, entity_ref: str, now: datetime
    ) -> WatchlistEntry:
        """Idempotent — following something already followed returns the existing entry rather
        than erroring, so a "Follow" button never has to check state first to avoid a 409."""
        existing = await self.repository.get_by_entity(user_id, entity_type, entity_ref)
        if existing is not None:
            return existing
        entry = WatchlistEntry(
            id=WatchlistEntryId(uuid.uuid4()),
            user_id=user_id,
            entity_type=entity_type,
            entity_ref=entity_ref,
            created_at=now,
        )
        return await self.repository.add(entry)

    async def unfollow(self, user_id: UserId, entry_id: WatchlistEntryId) -> None:
        entry = await self.repository.get_by_id(entry_id)
        if entry is None:
            raise WatchlistEntryNotFoundError(str(entry_id))
        if entry.user_id != user_id:
            raise NotWatchlistEntryOwnerError(str(entry_id))
        await self.repository.remove(entry_id)

    async def list_for_user(
        self, user_id: UserId, entity_type: WatchlistEntityType | None = None
    ) -> list[WatchlistEntry]:
        return await self.repository.list_for_user(user_id, entity_type)
