from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class WatchlistEntityType(str, Enum):
    """What a user is following. Deliberately its own enum rather than reusing
    modules.features.domain.value_objects.EntityType: that one models what a *feature value* is
    about (team/player/fixture/competition/season/venue) and has no "prediction" member — a user
    can follow a prediction, a feature can't be about one."""

    TEAM = "team"
    COMPETITION = "competition"
    FIXTURE = "fixture"
    PREDICTION = "prediction"


@dataclass(frozen=True)
class WatchlistEntryId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
