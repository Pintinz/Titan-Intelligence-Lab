from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.features.domain.entities import FeatureDefinition
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
)
from modules.predictions.football.odds_feature_writer import (
    IMPLIED_PROBABILITY_AWAY_KEY,
    IMPLIED_PROBABILITY_HOME_KEY,
    OVERROUND_KEY,
    football_odds_feature_writer,
)
from modules.sports.domain.value_objects import ProviderRef
from modules.sports.ports.provider_gateway import ProviderOddsRecord

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _active_definition(feature_key: str) -> FeatureDefinition:
    return FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey(feature_key),
        name=feature_key,
        description="d",
        sport_code="football",
        category=FeatureCategory.LIVE,
        formula="derived from the provider's live odds feed",
        data_type=FeatureDataType.FLOAT,
        owner="test",
        entity_type=EntityType.FIXTURE,
        status=FeatureStatus.ACTIVE,
    )


@pytest.fixture(autouse=True)
async def _register_odds_features(feature_definition_repo):
    for key in (IMPLIED_PROBABILITY_HOME_KEY, IMPLIED_PROBABILITY_AWAY_KEY, OVERROUND_KEY):
        await feature_definition_repo.upsert(_active_definition(key))


@pytest.fixture
def writer(store):
    return football_odds_feature_writer(store)


def _odds(**overrides) -> ProviderOddsRecord:
    kwargs = dict(fixture_ref=ProviderRef(provider="mock_football", external_id="fx1"), home_win=2.1, draw=3.4, away_win=3.6)
    kwargs.update(overrides)
    return ProviderOddsRecord(**kwargs)


@pytest.mark.asyncio
async def test_writes_all_three_features_for_a_complete_three_way_line(writer, store):
    written = await writer.compute_and_write("fixture-1", _odds(), T0)

    assert set(written) == {IMPLIED_PROBABILITY_HOME_KEY, IMPLIED_PROBABILITY_AWAY_KEY, OVERROUND_KEY}

    home = await store.read(IMPLIED_PROBABILITY_HOME_KEY, EntityType.FIXTURE, "fixture-1")
    assert home.value == pytest.approx(1 / 2.1)
    away = await store.read(IMPLIED_PROBABILITY_AWAY_KEY, EntityType.FIXTURE, "fixture-1")
    assert away.value == pytest.approx(1 / 3.6)
    overround = await store.read(OVERROUND_KEY, EntityType.FIXTURE, "fixture-1")
    assert overround.value == pytest.approx((1 / 2.1) + (1 / 3.4) + (1 / 3.6) - 1.0)


@pytest.mark.asyncio
async def test_two_way_line_still_writes_implied_probabilities_but_not_overround(writer, store):
    """No draw odds (a two-outcome sport) means OddsOverroundCalculator can't compute (needs
    all three legs) but the two ImpliedProbabilityCalculators still can."""
    written = await writer.compute_and_write("fixture-2", _odds(draw=None), T0)

    assert set(written) == {IMPLIED_PROBABILITY_HOME_KEY, IMPLIED_PROBABILITY_AWAY_KEY}
    assert await store.read(OVERROUND_KEY, EntityType.FIXTURE, "fixture-2") is None


@pytest.mark.asyncio
async def test_writes_under_the_exact_fixture_id_passed_in(writer, store):
    await writer.compute_and_write("4d193afe-6faf-4b63-9630-c6fa31c4d6aa", _odds(), T0)

    home = await store.read(IMPLIED_PROBABILITY_HOME_KEY, EntityType.FIXTURE, "4d193afe-6faf-4b63-9630-c6fa31c4d6aa")
    assert home is not None
