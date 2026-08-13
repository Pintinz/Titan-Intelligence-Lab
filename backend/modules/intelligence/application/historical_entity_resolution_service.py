"""Milestone 13 — Point-in-time player -> team membership resolution.

CRITICAL RULE (the M13 audit's own finding, non-negotiable): historical membership must NEVER be
read from `Player.team_id` (a single mutable "current" pointer with no history — confirmed by the
audit: `Player` carries exactly one `team_id` field, overwritten on every re-sync) or from
Knowledge Graph `PLAYS_FOR` edges (temporally-typed in schema since Milestone 7 — `KGEdge.valid_from`/
`valid_to` exist — but in practice never superseded by any real production pipeline: confirmed live
against `dev.db`, 100 `plays_for` edges exist and 0 have ever been closed, because the only code
that ever calls `TemporalGraphService.supersede_edge` for a transfer,
`KnowledgeGraphEnrichmentService`, has zero real call sites anywhere in `apps/`).

The only reliable historical source is the `Transfer` entity's `effective_date` — real,
provider-backed, append-only (dev.db: 308 real records spanning 2010-09-17 to 2026-07-22).

Chains a player's transfers chronologically and asks "which team, if any, was this player on at
`reference_time`". Two outcomes:

- `HISTORICALLY_RESOLVED` — real evidence brackets `reference_time`. `team_id` may itself be
  ``None`` if the applicable transfer's own `to_team_id` is ``None`` (a genuine "released, no
  club" state, e.g. the terminal record in a chain) — that is still a resolved fact, not missing
  data, and downstream relevance matching will correctly find no team to compare against.
- `HISTORICALLY_UNRESOLVED` — no evidence exists: the player has no transfer records at all, or
  `reference_time` predates every known transfer for this player. Never guessed, never filled in
  from `Player.team_id`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from modules.sports.domain.value_objects import PlayerId, TeamId
from modules.sports.ports.repositories import TransferRepositoryPort


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — same duplicated
    helper used throughout this codebase's ingestion/intelligence modules."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


class PlayerMembershipStatus(str, Enum):
    HISTORICALLY_RESOLVED = "historically_resolved"
    HISTORICALLY_UNRESOLVED = "historically_unresolved"


@dataclass(frozen=True)
class PlayerMembershipResolution:
    status: PlayerMembershipStatus
    team_id: TeamId | None
    evidence: str


@dataclass
class HistoricalEntityResolutionService:
    transfers: TransferRepositoryPort

    async def resolve_player_membership(
        self, player_id: PlayerId, reference_time: datetime,
    ) -> PlayerMembershipResolution:
        records = await self.transfers.list_by_player(player_id)
        if not records:
            return PlayerMembershipResolution(
                status=PlayerMembershipStatus.HISTORICALLY_UNRESOLVED, team_id=None,
                evidence="no transfer history exists for this player — current team_id was not consulted",
            )

        aware = sorted(
            ((record, _ensure_aware(record.effective_date, reference_time)) for record in records),
            key=lambda pair: pair[1],
        )

        applicable = [pair for pair in aware if pair[1] <= reference_time]
        if not applicable:
            earliest_effective = aware[0][1]
            return PlayerMembershipResolution(
                status=PlayerMembershipStatus.HISTORICALLY_UNRESOLVED, team_id=None,
                evidence=(
                    f"reference_time ({reference_time.isoformat()}) predates the earliest known "
                    f"transfer (effective_date={earliest_effective.isoformat()}) — membership "
                    "before that date is unknown, not assumed"
                ),
            )

        latest_transfer, latest_effective = applicable[-1]
        return PlayerMembershipResolution(
            status=PlayerMembershipStatus.HISTORICALLY_RESOLVED,
            team_id=latest_transfer.to_team_id,
            evidence=(
                f"transfer.effective_date={latest_effective.isoformat()} "
                f"transfer.id={latest_transfer.id.value}"
            ),
        )
