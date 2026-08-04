from __future__ import annotations

from typing import Protocol

from modules.identity.domain.value_objects import UserId
from modules.watchlist.domain.entities import WatchlistEntry
from modules.watchlist.domain.value_objects import WatchlistEntityType, WatchlistEntryId


class WatchlistRepositoryPort(Protocol):
    async def add(self, entry: WatchlistEntry) -> WatchlistEntry: ...

    async def get_by_id(self, entry_id: WatchlistEntryId) -> WatchlistEntry | None: ...

    async def get_by_entity(
        self, user_id: UserId, entity_type: WatchlistEntityType, entity_ref: str
    ) -> WatchlistEntry | None: ...

    async def remove(self, entry_id: WatchlistEntryId) -> None: ...

    async def list_for_user(
        self, user_id: UserId, entity_type: WatchlistEntityType | None = None
    ) -> list[WatchlistEntry]: ...

    async def list_watchers(self, entity_type: WatchlistEntityType, entity_ref: str) -> list[UserId]:
        """The inverse of list_for_user — every user following this exact entity. Alerts uses
        this to find who to notify when something real happens to a watched match/team/
        competition/prediction."""
        ...
