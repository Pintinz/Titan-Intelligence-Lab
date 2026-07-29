"""Match lifecycle contracts — how a sport structures a match into periods, and what event
types it recognizes. Generic fixture/match code depends only on this contract, never on a
sport name (see docs/architecture.md §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.sports.domain.value_objects import FixtureStatus, MatchPeriodKind

# Fixtures may only move forward through these states (never SCHEDULED -> COMPLETED directly,
# never backward out of COMPLETED/CANCELLED).
_ALLOWED_TRANSITIONS: dict[FixtureStatus, tuple[FixtureStatus, ...]] = {
    FixtureStatus.SCHEDULED: (FixtureStatus.LIVE, FixtureStatus.POSTPONED, FixtureStatus.CANCELLED),
    FixtureStatus.LIVE: (FixtureStatus.COMPLETED, FixtureStatus.POSTPONED),
    FixtureStatus.POSTPONED: (FixtureStatus.SCHEDULED, FixtureStatus.CANCELLED),
    FixtureStatus.COMPLETED: (),
    FixtureStatus.CANCELLED: (),
}


def is_valid_fixture_transition(current: FixtureStatus, target: FixtureStatus) -> bool:
    return target in _ALLOWED_TRANSITIONS[current]


@dataclass(frozen=True)
class MatchLifecycleRules:
    """Declares how a sport subdivides a match.

    Examples: football -> HALF x2 (+ optional OVERTIME); basketball -> QUARTER x4
    (+ optional OVERTIME); baseball -> INNING x9; table tennis -> SET, best-of-N.
    """

    period_kind: MatchPeriodKind
    regulation_periods: int
    allows_overtime: bool
    allows_draw: bool

    def __post_init__(self) -> None:
        if self.regulation_periods <= 0:
            raise ValueError("regulation_periods must be positive")


@dataclass(frozen=True)
class MatchEventTypeCatalog:
    """The closed set of match event types a sport plugin recognizes.

    ``match_events.payload`` (docs/database_schema.md §2) is only valid if its ``type`` is a
    member of the owning sport's catalog — enforced at the application layer, not the DB.
    """

    event_types: frozenset[str] = field(default_factory=frozenset)

    def is_recognized(self, event_type: str) -> bool:
        return event_type in self.event_types
