from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from modules.alerts.application.alert_service import (
    AlertEventNotFoundError,
    AlertService,
    NotAlertEventOwnerError,
)
from modules.alerts.domain.entities import AlertEvent
from modules.alerts.domain.value_objects import AlertEventId, AlertType
from modules.identity.domain.value_objects import UserId
from modules.watchlist.domain.value_objects import WatchlistEntityType


@dataclass
class FakeAlertEventRepository:
    events: dict = field(default_factory=dict)

    async def add(self, event: AlertEvent) -> AlertEvent:
        self.events[event.id.value] = event
        return event

    async def get(self, event_id: AlertEventId):
        return self.events.get(event_id.value)

    async def list_for_user(self, user_id: UserId, unread_only: bool = False, limit: int = 50):
        results = [
            e for e in self.events.values()
            if e.user_id == user_id and (not unread_only or e.read_at is None)
        ]
        return sorted(results, key=lambda e: e.created_at, reverse=True)[:limit]

    async def mark_read(self, event_id: AlertEventId, now: datetime) -> None:
        event = self.events.get(event_id.value)
        if event is not None:
            event.read_at = now

    async def count_unread(self, user_id: UserId) -> int:
        return len([e for e in self.events.values() if e.user_id == user_id and e.read_at is None])


@dataclass
class FakeWatchlistRepository:
    watchers: dict  # (entity_type, entity_ref) -> list[UserId]

    async def list_watchers(self, entity_type: WatchlistEntityType, entity_ref: str):
        return self.watchers.get((entity_type, entity_ref), [])


def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def user_id():
    return UserId(uuid.uuid4())


@pytest.fixture
def other_user_id():
    return UserId(uuid.uuid4())


@pytest.fixture
def service(user_id):
    watchlist = FakeWatchlistRepository(watchers={(WatchlistEntityType.FIXTURE, "fx-1"): [user_id]})
    return AlertService(events=FakeAlertEventRepository(), watchlist=watchlist)


async def test_notify_watchers_creates_one_event_per_watcher(service, user_id):
    events = await service.notify_watchers(
        WatchlistEntityType.FIXTURE, "fx-1", AlertType.KICKOFF, "Kickoff", "Match started", now()
    )

    assert len(events) == 1
    assert events[0].user_id == user_id
    assert events[0].alert_type is AlertType.KICKOFF


async def test_notify_watchers_creates_nothing_for_unwatched_entity(service):
    events = await service.notify_watchers(
        WatchlistEntityType.FIXTURE, "fx-unwatched", AlertType.KICKOFF, "Kickoff", "Match started", now()
    )

    assert events == []


async def test_list_for_user_returns_only_that_users_events(service, user_id):
    await service.notify_watchers(WatchlistEntityType.FIXTURE, "fx-1", AlertType.KICKOFF, "t", "b", now())

    events = await service.list_for_user(user_id)

    assert len(events) == 1


async def test_mark_read_updates_event(service, user_id):
    [event] = await service.notify_watchers(WatchlistEntityType.FIXTURE, "fx-1", AlertType.KICKOFF, "t", "b", now())

    await service.mark_read(user_id, event.id, now())

    assert (await service.list_for_user(user_id, unread_only=True)) == []
    assert await service.unread_count(user_id) == 0


async def test_mark_read_unknown_event_raises(service, user_id):
    with pytest.raises(AlertEventNotFoundError):
        await service.mark_read(user_id, AlertEventId(uuid.uuid4()), now())


async def test_mark_read_someone_elses_event_raises(service, user_id, other_user_id):
    [event] = await service.notify_watchers(WatchlistEntityType.FIXTURE, "fx-1", AlertType.KICKOFF, "t", "b", now())

    with pytest.raises(NotAlertEventOwnerError):
        await service.mark_read(other_user_id, event.id, now())
