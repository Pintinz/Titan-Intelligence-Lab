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


# API-Sports' "short status" vocabulary is shared across its football/basketball/baseball
# products (same response envelope shape), so one pattern-based normalizer covers all sports
# rather than a table per sport — classifying by pattern instead of an exhaustive per-code list
# also survives sport-specific codes this wasn't tested against (e.g. baseball's inning codes)
# without silently dropping a live match back to "scheduled".
_FINISHED_CODES = {"FT", "AET", "PEN", "FT_PEN", "AOT", "FINISHED", "FINAL", "GAME OVER", "AWD", "WO"}
_SCHEDULED_CODES = {"NS", "TBD", "SCHEDULED", "TIMED"}
_POSTPONED_CODES = {"PST", "SUSP", "INT"}
_CANCELLED_CODES = {"CANC", "CANCELLED", "ABD"}


def normalize_provider_fixture_status(raw: str | None) -> FixtureStatus:
    """Maps a raw provider status code onto TitanIQ's own FixtureStatus vocabulary. Unrecognized
    non-empty codes fall back to LIVE — a match is either not-yet-started, finished, postponed,
    or cancelled (all closed, enumerable sets); anything else reported while a fixture has
    actually begun is safest classified as in-progress rather than silently reverting to
    "scheduled"."""
    if not raw:
        return FixtureStatus.SCHEDULED
    code = raw.strip().upper()
    if code in _FINISHED_CODES or "PEN" in code:
        return FixtureStatus.COMPLETED
    if code in _SCHEDULED_CODES:
        return FixtureStatus.SCHEDULED
    if code in _POSTPONED_CODES:
        return FixtureStatus.POSTPONED
    if code in _CANCELLED_CODES:
        return FixtureStatus.CANCELLED
    return FixtureStatus.LIVE


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
