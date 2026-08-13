from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.intelligence.application.historical_entity_resolution_service import (
    HistoricalEntityResolutionService,
    PlayerMembershipStatus,
)
from modules.sports.domain.entities import Transfer
from modules.sports.domain.value_objects import EntityId, PlayerId, TeamId

T0 = datetime(2024, 3, 1, tzinfo=timezone.utc)
TEAM_A = TeamId(uuid4())
TEAM_B = TeamId(uuid4())
TEAM_C = TeamId(uuid4())
PLAYER = PlayerId(uuid4())


@dataclass
class _FakeTransferRepo:
    by_player: dict = field(default_factory=dict)

    async def list_by_player(self, player_id):
        return self.by_player.get(player_id, [])

    async def list_by_team(self, team_id):
        return []

    async def get(self, transfer_id):
        return None

    async def upsert(self, transfer):
        return transfer


def _transfer(from_team, to_team, effective_date: datetime) -> Transfer:
    return Transfer(
        id=EntityId(uuid4()), player_id=PLAYER, from_team_id=from_team, to_team_id=to_team,
        effective_date=effective_date,
    )


def _service(transfers: list[Transfer]) -> HistoricalEntityResolutionService:
    return HistoricalEntityResolutionService(transfers=_FakeTransferRepo(by_player={PLAYER: transfers}))


# --- A. Player with transfer history -----------------------------------------------------------

async def test_a_player_with_transfer_history_resolves():
    transfers = [_transfer(None, TEAM_A, T0 - timedelta(days=100))]
    service = _service(transfers)

    result = await service.resolve_player_membership(PLAYER, T0)

    assert result.status is PlayerMembershipStatus.HISTORICALLY_RESOLVED
    assert result.team_id == TEAM_A


# --- B. Player membership BEFORE a transfer ------------------------------------------------------

async def test_b_membership_before_a_later_transfer_resolves_to_the_earlier_team():
    transfers = [
        _transfer(None, TEAM_A, T0 - timedelta(days=100)),
        _transfer(TEAM_A, TEAM_B, T0 + timedelta(days=50)),
    ]
    service = _service(transfers)

    result = await service.resolve_player_membership(PLAYER, T0)

    assert result.status is PlayerMembershipStatus.HISTORICALLY_RESOLVED
    assert result.team_id == TEAM_A


# --- C. Player membership AFTER a transfer -------------------------------------------------------

async def test_c_membership_after_a_transfer_resolves_to_the_new_team():
    transfers = [
        _transfer(None, TEAM_A, T0 - timedelta(days=100)),
        _transfer(TEAM_A, TEAM_B, T0 - timedelta(days=10)),
    ]
    service = _service(transfers)

    result = await service.resolve_player_membership(PLAYER, T0)

    assert result.status is PlayerMembershipStatus.HISTORICALLY_RESOLVED
    assert result.team_id == TEAM_B


# --- D. Multiple transfers ------------------------------------------------------------------------

async def test_d_multiple_transfers_resolve_to_the_team_valid_at_reference_time():
    transfers = [
        _transfer(None, TEAM_A, T0 - timedelta(days=1000)),
        _transfer(TEAM_A, TEAM_B, T0 - timedelta(days=500)),
        _transfer(TEAM_B, TEAM_C, T0 - timedelta(days=10)),
        _transfer(TEAM_C, TEAM_A, T0 + timedelta(days=200)),  # future relative to T0 — ignored
    ]
    service = _service(transfers)

    result = await service.resolve_player_membership(PLAYER, T0)

    assert result.status is PlayerMembershipStatus.HISTORICALLY_RESOLVED
    assert result.team_id == TEAM_C


# --- E. Missing transfer history -------------------------------------------------------------------

async def test_e_missing_transfer_history_is_unresolved():
    service = _service([])

    result = await service.resolve_player_membership(PLAYER, T0)

    assert result.status is PlayerMembershipStatus.HISTORICALLY_UNRESOLVED
    assert result.team_id is None
    assert "no transfer history" in result.evidence


# --- F. Reference time before earliest known transfer ------------------------------------------------

async def test_f_reference_time_before_earliest_transfer_is_unresolved():
    transfers = [_transfer(None, TEAM_A, T0)]
    service = _service(transfers)

    result = await service.resolve_player_membership(PLAYER, T0 - timedelta(days=1))

    assert result.status is PlayerMembershipStatus.HISTORICALLY_UNRESOLVED
    assert result.team_id is None
    assert "predates the earliest known transfer" in result.evidence


# --- G. Reference time after the latest known transfer, which released the player (no club) -------

async def test_g_reference_time_after_a_release_resolves_to_no_club_not_unresolved():
    """A released player (transfer.to_team_id is None) is still a genuine, evidenced historical
    fact — RESOLVED with team_id=None — distinct from having no evidence at all (case E/F)."""
    transfers = [
        _transfer(None, TEAM_A, T0 - timedelta(days=100)),
        _transfer(TEAM_A, None, T0 - timedelta(days=10)),  # released, no new club
    ]
    service = _service(transfers)

    result = await service.resolve_player_membership(PLAYER, T0)

    assert result.status is PlayerMembershipStatus.HISTORICALLY_RESOLVED
    assert result.team_id is None


# --- H. Current Player.team_id must never be consulted --------------------------------------------

async def test_h_service_has_no_dependency_on_player_repository_at_all():
    """Structural proof, not just behavioral: `HistoricalEntityResolutionService` only depends on
    `TransferRepositoryPort` — it is architecturally impossible for it to read `Player.team_id`,
    since it never receives a player repository to read from."""
    import dataclasses

    field_types = {f.name: f.type for f in dataclasses.fields(HistoricalEntityResolutionService)}
    assert set(field_types.keys()) == {"transfers"}


async def test_h_historical_evidence_wins_even_when_it_contradicts_a_hypothetical_current_team():
    """Behavioral companion to the structural test above: even though nothing here ever consults
    a "current" team, confirm the resolved team is driven purely by transfer evidence — which, in
    a real system, could differ arbitrarily from whatever Player.team_id happens to say today."""
    transfers = [_transfer(None, TEAM_A, T0 - timedelta(days=5))]
    service = _service(transfers)
    hypothetical_current_team_id = TEAM_C  # deliberately different, never passed to the service

    result = await service.resolve_player_membership(PLAYER, T0)

    assert result.team_id == TEAM_A
    assert result.team_id != hypothetical_current_team_id
