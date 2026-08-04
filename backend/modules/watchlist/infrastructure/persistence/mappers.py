from __future__ import annotations

from modules.identity.domain.value_objects import UserId
from modules.watchlist.domain.entities import WatchlistEntry
from modules.watchlist.domain.value_objects import WatchlistEntityType, WatchlistEntryId
from modules.watchlist.infrastructure.persistence.models import WatchlistEntryModel


def entry_to_domain(model: WatchlistEntryModel) -> WatchlistEntry:
    return WatchlistEntry(
        id=WatchlistEntryId(model.id),
        user_id=UserId(model.user_id),
        entity_type=WatchlistEntityType(model.entity_type),
        entity_ref=model.entity_ref,
        created_at=model.created_at,
    )


def entry_to_model(entry: WatchlistEntry) -> WatchlistEntryModel:
    return WatchlistEntryModel(
        id=entry.id.value,
        user_id=entry.user_id.value,
        entity_type=entry.entity_type.value,
        entity_ref=entry.entity_ref,
        created_at=entry.created_at,
    )
