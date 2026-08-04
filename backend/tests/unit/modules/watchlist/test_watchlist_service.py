from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from modules.identity.domain.value_objects import UserId
from modules.watchlist.application.watchlist_service import (
    NotWatchlistEntryOwnerError,
    WatchlistEntryNotFoundError,
    WatchlistService,
)
from modules.watchlist.domain.entities import WatchlistEntry
from modules.watchlist.domain.value_objects import WatchlistEntityType, WatchlistEntryId


@dataclass
class FakeWatchlistRepository:
    entries: dict = field(default_factory=dict)

    async def add(self, entry: WatchlistEntry) -> WatchlistEntry:
        self.entries[entry.id.value] = entry
        return entry

    async def get_by_id(self, entry_id: WatchlistEntryId) -> WatchlistEntry | None:
        return self.entries.get(entry_id.value)

    async def get_by_entity(self, user_id: UserId, entity_type: WatchlistEntityType, entity_ref: str):
        for entry in self.entries.values():
            if entry.user_id == user_id and entry.entity_type == entity_type and entry.entity_ref == entity_ref:
                return entry
        return None

    async def remove(self, entry_id: WatchlistEntryId) -> None:
        self.entries.pop(entry_id.value, None)

    async def list_for_user(self, user_id: UserId, entity_type: WatchlistEntityType | None = None):
        return [
            e
            for e in self.entries.values()
            if e.user_id == user_id and (entity_type is None or e.entity_type == entity_type)
        ]


def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def service():
    return WatchlistService(repository=FakeWatchlistRepository())


@pytest.fixture
def user_id():
    return UserId(uuid.uuid4())


async def test_follow_creates_entry(service, user_id):
    entry = await service.follow(user_id, WatchlistEntityType.TEAM, "team-1", now())

    assert entry.user_id == user_id
    assert entry.entity_type is WatchlistEntityType.TEAM
    assert entry.entity_ref == "team-1"


async def test_follow_is_idempotent(service, user_id):
    first = await service.follow(user_id, WatchlistEntityType.FIXTURE, "fx-1", now())
    second = await service.follow(user_id, WatchlistEntityType.FIXTURE, "fx-1", now())

    assert first.id == second.id
    entries = await service.list_for_user(user_id)
    assert len(entries) == 1


async def test_unfollow_removes_entry(service, user_id):
    entry = await service.follow(user_id, WatchlistEntityType.COMPETITION, "comp-1", now())

    await service.unfollow(user_id, entry.id)

    assert await service.list_for_user(user_id) == []


async def test_unfollow_unknown_entry_raises(service, user_id):
    with pytest.raises(WatchlistEntryNotFoundError):
        await service.unfollow(user_id, WatchlistEntryId(uuid.uuid4()))


async def test_unfollow_someone_elses_entry_raises(service, user_id):
    other_user = UserId(uuid.uuid4())
    entry = await service.follow(other_user, WatchlistEntityType.TEAM, "team-2", now())

    with pytest.raises(NotWatchlistEntryOwnerError):
        await service.unfollow(user_id, entry.id)


async def test_list_for_user_filters_by_entity_type(service, user_id):
    await service.follow(user_id, WatchlistEntityType.TEAM, "team-1", now())
    await service.follow(user_id, WatchlistEntityType.PREDICTION, "pred-1", now())

    teams_only = await service.list_for_user(user_id, WatchlistEntityType.TEAM)

    assert len(teams_only) == 1
    assert teams_only[0].entity_type is WatchlistEntityType.TEAM


async def test_list_for_user_scopes_to_owner(service, user_id):
    other_user = UserId(uuid.uuid4())
    await service.follow(user_id, WatchlistEntityType.TEAM, "team-1", now())
    await service.follow(other_user, WatchlistEntityType.TEAM, "team-2", now())

    entries = await service.list_for_user(user_id)

    assert len(entries) == 1
    assert entries[0].entity_ref == "team-1"
