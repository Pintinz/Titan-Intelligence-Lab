from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.application.market_registry_service import MarketRegistryService
from modules.predictions.application.windowed_feature_engineering_service import football_form_calculator
from modules.predictions.domain.value_objects import MarketStatus
from modules.predictions.football.market_seeding import MARKETS, SINGLE_RECORD_FEATURES, FootballMarketSeeder
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
        return []

    async def list_dependents(self, feature_key):
        return []


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

    def add(self, team_id, stat_set, started_at):
        self.store.append((team_id, stat_set, started_at))

    async def list_recent_by_team(self, team_id, before, limit=10):
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
def market_registry(market_repo, feature_mapping_repo):
    return MarketRegistryService(markets=market_repo, feature_mappings=feature_mapping_repo)


@pytest.fixture
def mapping_service(feature_mapping_repo, market_repo, feature_definition_repo):
    return FeatureMarketMappingService(
        mappings=feature_mapping_repo, markets=market_repo, feature_definitions=feature_definition_repo
    )


@pytest.fixture
def team_statistics_repo():
    return InMemoryTeamStatisticsRepository()


@pytest.fixture
def seeder(registration, store, market_registry, mapping_service, team_statistics_repo):
    return FootballMarketSeeder(
        registration=registration,
        markets=market_registry,
        mappings=mapping_service,
        windowed_calculator=football_form_calculator(registration, store, team_statistics_repo),
    )


@pytest.mark.asyncio
async def test_seed_registers_every_single_record_feature(seeder, feature_definition_repo):
    from modules.features.domain.value_objects import FeatureKey

    await seeder.seed(T0)

    for feature_key in SINGLE_RECORD_FEATURES:
        definition = await feature_definition_repo.get(FeatureKey(feature_key))
        assert definition is not None
        assert definition.is_consumable()


@pytest.mark.asyncio
async def test_seed_registers_windowed_feature(seeder, feature_definition_repo):
    from modules.features.domain.value_objects import FeatureKey

    await seeder.seed(T0)

    definition = await feature_definition_repo.get(FeatureKey("football.team.form_shots_on_target_last5"))
    assert definition is not None
    assert definition.is_consumable()


@pytest.mark.asyncio
async def test_seed_promotes_every_market_to_production(seeder, market_repo):
    await seeder.seed(T0)

    for spec in MARKETS:
        market = await market_repo.get_by_key(spec["market_key"])
        assert market is not None
        assert market.status is MarketStatus.PRODUCTION
        assert market.market_kind == spec["market_kind"]


@pytest.mark.asyncio
async def test_seed_maps_every_declared_required_feature(seeder, feature_mapping_repo, market_repo):
    await seeder.seed(T0)

    for spec in MARKETS:
        market = await market_repo.get_by_key(spec["market_key"])
        mapped_keys = {m.feature_key for m in await feature_mapping_repo.list_by_market(market.id)}
        assert mapped_keys == set(spec["required_features"])


@pytest.mark.asyncio
async def test_seed_is_idempotent(seeder, market_repo):
    await seeder.seed(T0)
    await seeder.seed(T0)  # must not raise on re-run

    markets = await market_repo.list_by_sport("football")
    assert len(markets) == len(MARKETS)
    assert all(m.status is MarketStatus.PRODUCTION for m in markets)
