from __future__ import annotations

from datetime import datetime, timezone

import pytest

from modules.features.domain.value_objects import FeatureKey
from modules.predictions.application.windowed_feature_engineering_service import (
    baseball_fixture_form_differential_calculator,
    baseball_form_calculator,
)
from modules.predictions.baseball.market_seeding import MARKETS, SINGLE_RECORD_FEATURES, BaseballMarketSeeder
from modules.predictions.domain.value_objects import MarketStatus

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture
def seeder(registration, store, market_registry, mapping_service, team_statistics_repo):
    return BaseballMarketSeeder(
        registration=registration,
        markets=market_registry,
        mappings=mapping_service,
        windowed_calculator=baseball_form_calculator(registration, store, team_statistics_repo),
        differential_calculator=baseball_fixture_form_differential_calculator(registration, store, team_statistics_repo),
    )


@pytest.mark.asyncio
async def test_seed_registers_every_single_record_feature(seeder, feature_definition_repo):
    await seeder.seed(T0)

    for feature_key in SINGLE_RECORD_FEATURES:
        definition = await feature_definition_repo.get(FeatureKey(feature_key))
        assert definition is not None
        assert definition.is_consumable()


@pytest.mark.asyncio
async def test_seed_registers_windowed_feature(seeder, feature_definition_repo):
    await seeder.seed(T0)

    definition = await feature_definition_repo.get(FeatureKey("baseball.team.form_runs_last5"))
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
    await seeder.seed(T0)

    markets = await market_repo.list_by_sport("baseball")
    assert len(markets) == len(MARKETS)
    assert all(m.status is MarketStatus.PRODUCTION for m in markets)
