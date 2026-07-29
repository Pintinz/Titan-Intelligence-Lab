from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.predictions.application.windowed_feature_engineering_service import (
    baseball_form_calculator,
    basketball_form_calculator,
    football_form_calculator,
    table_tennis_form_calculator,
)
from modules.features.domain.value_objects import FeatureKey
from modules.sports.domain.entities import TeamStatistics
from modules.sports.domain.value_objects import EntityId, MatchId, TeamId

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@dataclass
class InMemoryFeatureVersionRepository:
    store: list = field(default_factory=list)

    async def record(self, snapshot):
        self.store.append(snapshot)
        return snapshot

    async def list_by_feature(self, feature_key):
        return [s for s in self.store if s.feature_key == feature_key]


@dataclass
class InMemoryFeatureLineageRepository:
    edges: list = field(default_factory=list)

    async def add_edge(self, edge):
        self.edges.append(edge)
        return edge

    async def list_dependencies(self, feature_key):
        return [e.depends_on_feature_key for e in self.edges if e.feature_key == feature_key]

    async def list_dependents(self, feature_key):
        return [e.feature_key for e in self.edges if e.depends_on_feature_key == feature_key]


@dataclass
class InMemoryOnlineFeatureStore:
    store: dict = field(default_factory=dict)

    async def get(self, feature_key, entity_type, entity_id):
        return self.store.get((feature_key, entity_type, entity_id))

    async def set(self, value, ttl_seconds):
        self.store[(value.feature_key, value.entity_type, value.entity_id)] = value

    async def delete(self, feature_key, entity_type, entity_id):
        self.store.pop((feature_key, entity_type, entity_id), None)


@dataclass
class InMemoryTeamStatisticsRepository:
    store: list = field(default_factory=list)

    def add(self, team_id: TeamId, stat_set: dict, started_at: datetime) -> None:
        self.store.append((team_id, stat_set, started_at))

    async def get_for_match_team(self, match_id, team_id):
        raise NotImplementedError

    async def list_by_match(self, match_id):
        raise NotImplementedError

    async def upsert(self, statistics):
        raise NotImplementedError

    async def list_recent_by_team(self, team_id: TeamId, before: datetime, limit: int = 10):
        matches = [
            TeamStatistics(id=EntityId(uuid4()), match_id=MatchId(uuid4()), team_id=team_id, stat_set=stat_set)
            for tid, stat_set, started_at in sorted(self.store, key=lambda row: row[2], reverse=True)
            if tid == team_id and started_at < before
        ]
        return matches[:limit]


@pytest.fixture
def registration(feature_definition_repo):
    lineage = FeatureLineageService(lineage=InMemoryFeatureLineageRepository(), definitions=feature_definition_repo)
    return FeatureRegistrationService(
        definitions=feature_definition_repo, versions=InMemoryFeatureVersionRepository(), lineage=lineage
    )


@pytest.fixture
def store(feature_definition_repo, feature_value_repo):
    return FeatureStoreService(
        definitions=feature_definition_repo, offline=feature_value_repo, online=InMemoryOnlineFeatureStore()
    )


@pytest.fixture
def team_statistics_repo():
    return InMemoryTeamStatisticsRepository()


@pytest.mark.asyncio
async def test_football_form_calculator_averages_shots_on_target(registration, store, team_statistics_repo):
    calculator = football_form_calculator(registration, store, team_statistics_repo, window=3)
    team_id = TeamId(uuid4())
    for i, shots in enumerate([4, 6, 8]):
        team_statistics_repo.add(team_id, {"shots_on_target": shots}, T0.replace(day=20 + i))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(team_id, T0.replace(day=25))

    assert value.value == pytest.approx((4 + 6 + 8) / 3)
    assert value.feature_key.value == "football.team.form_shots_on_target_last3"


@pytest.mark.asyncio
async def test_basketball_form_calculator_averages_points(registration, store, team_statistics_repo):
    calculator = basketball_form_calculator(registration, store, team_statistics_repo, window=2)
    team_id = TeamId(uuid4())
    team_statistics_repo.add(team_id, {"points": 100}, T0.replace(day=20))
    team_statistics_repo.add(team_id, {"points": 110}, T0.replace(day=21))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(team_id, T0.replace(day=25))

    assert value.value == pytest.approx(105.0)


@pytest.mark.asyncio
async def test_baseball_form_calculator_averages_runs(registration, store, team_statistics_repo):
    calculator = baseball_form_calculator(registration, store, team_statistics_repo, window=2)
    team_id = TeamId(uuid4())
    team_statistics_repo.add(team_id, {"runs": 3}, T0.replace(day=20))
    team_statistics_repo.add(team_id, {"runs": 7}, T0.replace(day=21))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(team_id, T0.replace(day=25))

    assert value.value == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_table_tennis_form_calculator_averages_points_won(registration, store, team_statistics_repo):
    calculator = table_tennis_form_calculator(registration, store, team_statistics_repo, window=2)
    team_id = TeamId(uuid4())
    team_statistics_repo.add(team_id, {"points_won": 11}, T0.replace(day=20))
    team_statistics_repo.add(team_id, {"points_won": 9}, T0.replace(day=21))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(team_id, T0.replace(day=25))

    assert value.value == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_compute_and_write_returns_none_with_no_matches(registration, store, team_statistics_repo):
    calculator = football_form_calculator(registration, store, team_statistics_repo)
    team_id = TeamId(uuid4())

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(team_id, T0)

    assert value is None


@pytest.mark.asyncio
async def test_compute_and_write_skips_matches_missing_the_stat_key(registration, store, team_statistics_repo):
    calculator = football_form_calculator(registration, store, team_statistics_repo, window=5)
    team_id = TeamId(uuid4())
    team_statistics_repo.add(team_id, {"shots_on_target": 6}, T0.replace(day=20))
    team_statistics_repo.add(team_id, {"possession_pct": 55.0}, T0.replace(day=21))  # missing shots_on_target

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write(team_id, T0.replace(day=25))

    assert value.value == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_ensure_registered_is_idempotent(registration, store, team_statistics_repo):
    calculator = football_form_calculator(registration, store, team_statistics_repo)

    await calculator.ensure_registered(T0)
    await calculator.ensure_registered(T0)  # must not raise FeatureAlreadyRegisteredError

    definition = await registration.definitions.get(FeatureKey(calculator.feature_key))
    assert definition is not None
    assert definition.is_consumable()


@pytest.mark.asyncio
async def test_compute_and_write_raises_if_ensure_registered_was_never_called(registration, store, team_statistics_repo):
    from modules.features.application.feature_store_service import FeatureNotFoundError

    calculator = football_form_calculator(registration, store, team_statistics_repo)
    team_id = TeamId(uuid4())
    team_statistics_repo.add(team_id, {"shots_on_target": 6}, T0.replace(day=20))

    with pytest.raises(FeatureNotFoundError):
        await calculator.compute_and_write(team_id, T0.replace(day=25))
