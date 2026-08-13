"""Milestone 5 — Verified Pre-Match Data Availability.

The reusable provenance mechanism behind `Injury`/`Transfer`/`Lineup`/`Suspension`'s
`availability_classification`/`information_available_at`/`fetched_at` fields
(modules/sports/domain/entities.py) — one classification function, not a lineup-specific one, so
adding a fifth structured-intelligence entity later needs no new mechanism, only a call site.

The governing rule (verbatim from the approved Milestone 5 spec): `information_available_at`
equals the reconciliation `now` ONLY when the sync was (1) initiated via the approved
`SyncTrigger.LIVE_SCHEDULED` pathway, (2) the fixture is within its configured pre-match
eligibility window (entity-specific — see `classify_availability`'s `window` parameter), (3) the
provider response is applicable to the entity being classified, (4) the sync completed
successfully, and (5) the data passed validation. Any other combination stays
`UNKNOWN_AVAILABILITY_TIME` (or a more specific non-verified state below) — never fabricated from
`created_at`/`updated_at`/`fetched_at`/kickoff as a substitute.

`fetched_at` (when the provider response was retrieved) and `information_available_at` (when the
underlying real-world fact became knowable) are deliberately different fields — the former is
recorded unconditionally on every successful fetch, regardless of trigger or provenance rules;
the latter is populated only when `classify_availability` returns `VERIFIED_PRE_MATCH`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from modules.ingestion.domain.value_objects import SyncTrigger
from modules.sports.domain.value_objects import FixtureStatus

# -- configurable windows (env-overridable, same pattern as apps/api/main.py's TITANIQ_CORS_ORIGINS)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Official football lineups are conventionally published ~60 minutes before kickoff; 90 minutes
# gives a real, if imperfect, margin for a periodic (not continuous) Beat schedule to still land
# a successful fetch inside the window rather than narrowly missing it. Not "the" correct value —
# a configured, documented default a future operator can retune without a code change.
LINEUP_PREMATCH_WINDOW_MINUTES = _env_int("TITANIQ_LINEUP_PREMATCH_WINDOW_MINUTES", 90)

# How far ahead of kickoff the structured-intelligence sync considers a fixture "upcoming" and
# therefore worth prioritizing for injury/transfer/lineup sync at all (Milestone 5 §1 — "do not
# blindly synchronize every fixture unnecessarily"). Injuries/transfers aren't kickoff-gated the
# way lineups are (§7), but they're still only synced for fixtures within this window, not the
# entire fixture catalog, matching the spec's explicit prioritization requirement.
STRUCTURED_INTEL_SYNC_WINDOW_HOURS = _env_int("TITANIQ_STRUCTURED_INTEL_SYNC_WINDOW_HOURS", 72)


class AvailabilityClassification(str, Enum):
    VERIFIED_PRE_MATCH = "VERIFIED_PRE_MATCH"
    UNKNOWN_AVAILABILITY_TIME = "UNKNOWN_AVAILABILITY_TIME"
    POST_MATCH = "POST_MATCH"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class AvailabilityResult:
    classification: AvailabilityClassification
    information_available_at: datetime | None  # only ever non-None for VERIFIED_PRE_MATCH


def is_within_prematch_window(kickoff: datetime, sync_time: datetime, window_minutes: int) -> bool:
    """True iff `sync_time` falls in `[kickoff - window_minutes, kickoff)` — strictly before
    kickoff, matching a lineup/prediction's actual pre-match cutoff, not merely "close to" it in
    either direction."""
    if sync_time >= kickoff:
        return False
    return (kickoff - sync_time).total_seconds() <= window_minutes * 60


def classify_availability(
    *,
    trigger: SyncTrigger,
    sync_succeeded: bool,
    validated: bool,
    applicable: bool,
    sync_time: datetime,
    kickoff: datetime | None = None,
    prematch_window_minutes: int | None = None,
    fixture_status: FixtureStatus | None = None,
    has_genuine_timestamp: bool = True,
) -> AvailabilityResult:
    """The single choke point every structured-intelligence reconciliation call routes through.

    `kickoff`/`prematch_window_minutes` are optional — pass both for a fixture-bound entity
    (lineups) to apply the kickoff-proximity gate; pass neither for an entity whose relevance
    isn't tied to one specific fixture's kickoff (transfers, and injuries per the spec's explicit
    "do not use the lineup one-hour kickoff rule for transfers/injuries" instruction) — those are
    verified purely on trigger + validity, with no window check.

    `has_genuine_timestamp` defaults True (most entities have nothing to doubt); injuries pass
    False explicitly today because no provider adapter supplies a real report timestamp (see
    `modules.sports.infrastructure.providers.api_sports_adapter.ApiFootballAdapter.fetch_injuries`'s
    own docstring) — this is what stops a scheduled injury sync from being trusted as
    VERIFIED_PRE_MATCH "merely because it was retrieved by a scheduled task", per the spec's
    explicit instruction, while still letting the mechanism produce VERIFIED_PRE_MATCH the moment
    a real provider timestamp genuinely exists.
    """
    if not applicable or not validated:
        return AvailabilityResult(AvailabilityClassification.INVALID, None)
    if not sync_succeeded:
        return AvailabilityResult(AvailabilityClassification.UNKNOWN_AVAILABILITY_TIME, None)

    if fixture_status is FixtureStatus.COMPLETED:
        return AvailabilityResult(AvailabilityClassification.EXPIRED, None)
    if kickoff is not None and sync_time >= kickoff:
        return AvailabilityResult(AvailabilityClassification.POST_MATCH, None)

    if trigger is not SyncTrigger.LIVE_SCHEDULED:
        return AvailabilityResult(AvailabilityClassification.UNKNOWN_AVAILABILITY_TIME, None)
    if not has_genuine_timestamp:
        return AvailabilityResult(AvailabilityClassification.UNKNOWN_AVAILABILITY_TIME, None)
    if kickoff is not None and prematch_window_minutes is not None:
        if not is_within_prematch_window(kickoff, sync_time, prematch_window_minutes):
            return AvailabilityResult(AvailabilityClassification.UNKNOWN_AVAILABILITY_TIME, None)

    return AvailabilityResult(AvailabilityClassification.VERIFIED_PRE_MATCH, sync_time)
