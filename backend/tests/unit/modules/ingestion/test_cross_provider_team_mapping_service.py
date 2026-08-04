from dataclasses import dataclass, field

import pytest

from modules.ingestion.application.cross_provider_team_mapping_service import (
    ConfirmedTeamMapping,
    CrossProviderTeamMappingService,
    ExistingTeamRef,
)
from modules.ingestion.domain.entities import ProviderRefIndexEntry
from modules.ingestion.domain.value_objects import EntityKind
from modules.sports.domain.value_objects import ProviderRef
from modules.sports.ports.provider_gateway import ProviderTeamRecord


@dataclass
class _InMemoryRefIndex:
    store: dict = field(default_factory=dict)

    async def get(self, provider, external_id, entity_kind):
        return self.store.get((provider, external_id, entity_kind))

    async def upsert(self, entry: ProviderRefIndexEntry) -> ProviderRefIndexEntry:
        self.store[(entry.provider, entry.external_id, entry.entity_kind)] = entry.entity_id
        return entry


def _fd_team(external_id: str, name: str) -> ProviderTeamRecord:
    return ProviderTeamRecord(
        external_ref=ProviderRef(provider="football_data_org", external_id=external_id),
        name=name, short_name=name[:3].upper(), country="England",
    )


def test_suggest_mappings_matches_by_exact_normalized_name():
    service = CrossProviderTeamMappingService(ref_index=_InMemoryRefIndex())
    fd_teams = [_fd_team("61", "Chelsea FC")]
    existing_teams = [ExistingTeamRef(id="titaniq-chelsea", name="Chelsea")]

    suggestions = service.suggest_mappings(fd_teams, existing_teams)

    assert suggestions[0].football_data_org_team_id == "61"
    assert suggestions[0].suggested_titaniq_team_id == "titaniq-chelsea"
    assert suggestions[0].suggested_titaniq_team_name == "Chelsea"
    assert suggestions[0].confidence == 1.0


def test_suggest_mappings_strips_diacritics_and_club_suffixes():
    service = CrossProviderTeamMappingService(ref_index=_InMemoryRefIndex())
    fd_teams = [_fd_team("5", "Bayern München FC")]
    existing_teams = [ExistingTeamRef(id="titaniq-bayern", name="Bayern Munchen")]

    suggestions = service.suggest_mappings(fd_teams, existing_teams)

    assert suggestions[0].suggested_titaniq_team_id == "titaniq-bayern"


def test_suggest_mappings_reports_no_match_honestly_instead_of_guessing():
    service = CrossProviderTeamMappingService(ref_index=_InMemoryRefIndex())
    fd_teams = [_fd_team("999", "Some Unrelated Club")]
    existing_teams = [ExistingTeamRef(id="titaniq-chelsea", name="Chelsea")]

    suggestions = service.suggest_mappings(fd_teams, existing_teams)

    assert suggestions[0].suggested_titaniq_team_id is None
    assert suggestions[0].suggested_titaniq_team_name is None
    assert suggestions[0].confidence == 0.0


def test_suggest_mappings_never_writes_anything():
    ref_index = _InMemoryRefIndex()
    service = CrossProviderTeamMappingService(ref_index=ref_index)

    service.suggest_mappings(
        [_fd_team("61", "Chelsea FC")], [ExistingTeamRef(id="titaniq-chelsea", name="Chelsea")]
    )

    assert ref_index.store == {}


@pytest.mark.asyncio
async def test_confirm_mappings_writes_a_second_provider_ref_alongside_any_existing_one():
    ref_index = _InMemoryRefIndex()
    # api-football already reconciled this same team under its own external id.
    await ref_index.upsert(ProviderRefIndexEntry("api_football", "50", EntityKind.TEAM, "titaniq-chelsea"))
    service = CrossProviderTeamMappingService(ref_index=ref_index)

    await service.confirm_mappings(
        [ConfirmedTeamMapping(football_data_org_team_id="61", titaniq_team_id="titaniq-chelsea")]
    )

    assert await ref_index.get("football_data_org", "61", EntityKind.TEAM) == "titaniq-chelsea"
    assert await ref_index.get("api_football", "50", EntityKind.TEAM) == "titaniq-chelsea"
