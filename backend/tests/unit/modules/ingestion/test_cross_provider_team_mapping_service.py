from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from modules.ingestion.application.cross_provider_team_mapping_service import (
    ConfirmedTeamMapping,
    CrossProviderTeamMappingService,
    ExistingTeamRef,
    UnknownTeamMappingTargetError,
)
from modules.ingestion.domain.entities import ProviderRefIndexEntry
from modules.ingestion.domain.value_objects import EntityKind
from modules.sports.domain.value_objects import ProviderRef, TeamId
from modules.sports.ports.provider_gateway import ProviderTeamRecord


@dataclass
class _InMemoryRefIndex:
    store: dict = field(default_factory=dict)

    async def get(self, provider, external_id, entity_kind):
        return self.store.get((provider, external_id, entity_kind))

    async def upsert(self, entry: ProviderRefIndexEntry) -> ProviderRefIndexEntry:
        self.store[(entry.provider, entry.external_id, entry.entity_kind)] = entry.entity_id
        return entry


@dataclass
class _FakeTeam:
    id: TeamId


@dataclass
class _InMemoryTeams:
    """Only the ids seeded here `exist` — everything else is `None`, matching a real
    `TeamRepositoryPort.get()` against a row that was never created or was deleted."""

    known_ids: set = field(default_factory=set)

    async def get(self, team_id: TeamId):
        return _FakeTeam(id=team_id) if str(team_id.value) in self.known_ids else None


def _fd_team(external_id: str, name: str) -> ProviderTeamRecord:
    return ProviderTeamRecord(
        external_ref=ProviderRef(provider="football_data_org", external_id=external_id),
        name=name, short_name=name[:3].upper(), country="England",
    )


def test_suggest_mappings_matches_by_exact_normalized_name():
    service = CrossProviderTeamMappingService(ref_index=_InMemoryRefIndex(), teams=_InMemoryTeams())
    fd_teams = [_fd_team("61", "Chelsea FC")]
    existing_teams = [ExistingTeamRef(id="titaniq-chelsea", name="Chelsea")]

    suggestions = service.suggest_mappings(fd_teams, existing_teams)

    assert suggestions[0].football_data_org_team_id == "61"
    assert suggestions[0].suggested_titaniq_team_id == "titaniq-chelsea"
    assert suggestions[0].suggested_titaniq_team_name == "Chelsea"
    assert suggestions[0].confidence == 1.0


def test_suggest_mappings_strips_diacritics_and_club_suffixes():
    service = CrossProviderTeamMappingService(ref_index=_InMemoryRefIndex(), teams=_InMemoryTeams())
    fd_teams = [_fd_team("5", "Bayern München FC")]
    existing_teams = [ExistingTeamRef(id="titaniq-bayern", name="Bayern Munchen")]

    suggestions = service.suggest_mappings(fd_teams, existing_teams)

    assert suggestions[0].suggested_titaniq_team_id == "titaniq-bayern"


def test_suggest_mappings_reports_no_match_honestly_instead_of_guessing():
    service = CrossProviderTeamMappingService(ref_index=_InMemoryRefIndex(), teams=_InMemoryTeams())
    fd_teams = [_fd_team("999", "Some Unrelated Club")]
    existing_teams = [ExistingTeamRef(id="titaniq-chelsea", name="Chelsea")]

    suggestions = service.suggest_mappings(fd_teams, existing_teams)

    assert suggestions[0].suggested_titaniq_team_id is None
    assert suggestions[0].suggested_titaniq_team_name is None
    assert suggestions[0].confidence == 0.0


def test_suggest_mappings_never_writes_anything():
    ref_index = _InMemoryRefIndex()
    service = CrossProviderTeamMappingService(ref_index=ref_index, teams=_InMemoryTeams())

    service.suggest_mappings(
        [_fd_team("61", "Chelsea FC")], [ExistingTeamRef(id="titaniq-chelsea", name="Chelsea")]
    )

    assert ref_index.store == {}


@pytest.mark.asyncio
async def test_confirm_mappings_writes_a_second_provider_ref_alongside_any_existing_one():
    chelsea_id = str(uuid4())
    ref_index = _InMemoryRefIndex()
    # api-football already reconciled this same team under its own external id.
    await ref_index.upsert(ProviderRefIndexEntry("api_football", "50", EntityKind.TEAM, chelsea_id))
    service = CrossProviderTeamMappingService(ref_index=ref_index, teams=_InMemoryTeams(known_ids={chelsea_id}))

    await service.confirm_mappings(
        [ConfirmedTeamMapping(football_data_org_team_id="61", titaniq_team_id=chelsea_id)]
    )

    assert await ref_index.get("football_data_org", "61", EntityKind.TEAM) == chelsea_id
    assert await ref_index.get("api_football", "50", EntityKind.TEAM) == chelsea_id


@pytest.mark.asyncio
async def test_confirm_mappings_rejects_a_target_team_that_does_not_exist():
    """Real production incident (2026-08-30): this write path used to trust `titaniq_team_id`
    blindly, so a confirmed mapping whose target team didn't (or no longer) exist became a
    permanently dangling `provider_ref_index` entry — reproduced live as a raw
    `ForeignKeyViolationError` when a fixture later referenced it. Must reject up front instead."""
    ref_index = _InMemoryRefIndex()
    service = CrossProviderTeamMappingService(ref_index=ref_index, teams=_InMemoryTeams())

    with pytest.raises(UnknownTeamMappingTargetError):
        await service.confirm_mappings(
            [ConfirmedTeamMapping(football_data_org_team_id="67", titaniq_team_id=str(uuid4()))]
        )

    assert ref_index.store == {}  # nothing was written — not even a partial batch
