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
from modules.predictions.application.windowed_feature_engineering_service import (
    football_fixture_expected_goals_calculator,
    football_fixture_stat_differential_calculators,
    football_form_calculator,
)
from modules.predictions.domain.value_objects import MarketKind, MarketStatus, OutcomeType
from modules.predictions.football.market_seeding import MARKETS, SINGLE_RECORD_FEATURES, FootballMarketSeeder
from modules.sports.domain.entities import Fixture, TeamStatistics
from modules.sports.domain.value_objects import EntityId, FixtureId, FixtureStatus, MatchId, SeasonId, TeamId

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


@dataclass
class InMemoryFixtureRepository:
    store: list = field(default_factory=list)  # list[Fixture]

    def add_completed(self, home_team_id, away_team_id, home_score, away_score, scheduled_at):
        self.store.append(
            Fixture(
                id=FixtureId(uuid4()), season_id=SeasonId(uuid4()), home_team_id=home_team_id,
                away_team_id=away_team_id, venue_id=None, scheduled_at=scheduled_at,
                status=FixtureStatus.COMPLETED, home_score=home_score, away_score=away_score,
            )
        )

    async def list_recent_by_team(self, team_id, before, limit=10):
        matches = [
            f for f in sorted(self.store, key=lambda f: f.scheduled_at, reverse=True)
            if (f.home_team_id == team_id or f.away_team_id == team_id) and f.scheduled_at < before
        ]
        return matches[:limit]


@pytest.fixture
def team_statistics_repo():
    return InMemoryTeamStatisticsRepository()


@pytest.fixture
def fixtures_repo():
    return InMemoryFixtureRepository()


@pytest.fixture
def seeder(registration, store, market_registry, mapping_service, team_statistics_repo, fixtures_repo):
    return FootballMarketSeeder(
        registration=registration,
        markets=market_registry,
        mappings=mapping_service,
        windowed_calculator=football_form_calculator(registration, store, team_statistics_repo),
        differential_calculators=football_fixture_stat_differential_calculators(registration, store, team_statistics_repo),
        expected_goals_calculator=football_fixture_expected_goals_calculator(registration, store, fixtures_repo),
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
async def test_seed_applies_conservative_weights_to_new_stat_differential_features(
    seeder, feature_mapping_repo, market_repo
):
    """The new possession/shots_total/corners/fouls/cards features (2026-08-03), plus the
    original `form_shots_on_target_diff_last5` (audit fix, 2026-08-06 — see NEW_STAT_FEATURE_WEIGHTS'
    own comment), must not get the weight=1.0 default the still-genuinely-0..1-scaled
    implied-probability features correctly get — at their natural raw-stat scale that would swamp
    the weighted-sum predictors' `raw_score` and saturate the sigmoid (confirmed live: a real
    fixture landed at 99.97% before this fix, 82.9% after). football.both_teams_to_score is a
    representative market: only `football.market.overround` is left relying on the unweighted
    default here, correctly, since it's already a small bookmaker-margin fraction."""
    from modules.predictions.football.market_seeding import NEW_STAT_FEATURE_WEIGHTS

    await seeder.seed(T0)

    market = await market_repo.get_by_key("football.both_teams_to_score")
    mappings = {m.feature_key: m.weight for m in await feature_mapping_repo.list_by_market(market.id)}

    for feature_key, expected_weight in NEW_STAT_FEATURE_WEIGHTS.items():
        assert mappings[feature_key] == pytest.approx(expected_weight)
        assert expected_weight < 1.0
    assert mappings["football.market.overround"] == 1.0


@pytest.mark.asyncio
async def test_seed_marks_new_stat_differential_features_optional(seeder, feature_mapping_repo, market_repo):
    """Regression test for a real bug found live-verifying this feature: a fixture whose
    TeamStatistics predate cards support (or that simply has fewer than 5 prior matches of
    history for one team) has no value at all for one of the five new stat-differential
    features — not a zero, an absent key. If these were `is_required=True` (the mistake this
    guards against), `PredictionContextBuilder` would raise `MissingRequiredFeatureError` and
    block generation entirely for any such fixture, defeating the whole "fine-tune when
    available" point of adding them. Only the original shots_on_target differential — which
    every fixture in dev.db already has — stays required."""
    from modules.predictions.football.market_seeding import _NEW_STAT_DIFFERENTIAL_FEATURES

    await seeder.seed(T0)

    market = await market_repo.get_by_key("football.both_teams_to_score")
    mappings = {m.feature_key: m.is_required for m in await feature_mapping_repo.list_by_market(market.id)}

    assert mappings["football.fixture.form_shots_on_target_diff_last5"] is True
    for feature_key in _NEW_STAT_DIFFERENTIAL_FEATURES:
        assert mappings[feature_key] is False


@pytest.mark.asyncio
async def test_seed_registers_match_winner_as_home_draw_away_kind(seeder, market_repo):
    """Milestone 9.2 Phase 3 — the first market registered with the genuinely 3-way
    MarketKind.HOME_DRAW_AWAY, backed by WeightedOrdinalPredictor rather than a relabeled binary."""
    await seeder.seed(T0)

    market = await market_repo.get_by_key("football.match_winner")
    assert market is not None
    assert market.market_kind is MarketKind.HOME_DRAW_AWAY
    assert market.status is MarketStatus.PRODUCTION


@pytest.mark.asyncio
async def test_seed_pulls_real_outcome_contract_from_the_catalog(seeder, market_repo):
    """Every seeded market's outcome_type/allowed_values/resolver_key comes from Milestone 9.2
    Phase 1's MARKET_OUTCOME_CATALOG (domain/market_outcome_registry.py), not invented here."""
    await seeder.seed(T0)

    match_winner = await market_repo.get_by_key("football.match_winner")
    assert match_winner.outcome_type is OutcomeType.HOME_DRAW_AWAY
    assert set(match_winner.allowed_values) == {"HOME_WIN", "DRAW", "AWAY_WIN"}
    assert match_winner.resolver_key == "football.match_winner"

    both_teams_to_score = await market_repo.get_by_key("football.both_teams_to_score")
    assert both_teams_to_score.resolver_key == "football.both_teams_to_score"

    # first_half_winner has a real catalog entry (2026-08-02 expansion) specifying its 3-way
    # label space — but still no resolver_key, honestly: no sub-match score data is ingested yet
    # to actually evaluate it.
    first_half_winner = await market_repo.get_by_key("football.first_half_winner")
    assert first_half_winner.outcome_type is OutcomeType.HOME_DRAW_AWAY
    assert set(first_half_winner.allowed_values) == {"HOME_WIN", "DRAW", "AWAY_WIN"}
    assert first_half_winner.resolver_key is None

    # home_clean_sheet has a real catalog entry AND a real resolver (computable from the final
    # score alone) — the 2026-08-02 expansion's fully-resolved shape.
    home_clean_sheet = await market_repo.get_by_key("football.home_clean_sheet")
    assert home_clean_sheet.outcome_type is OutcomeType.BINARY_YES_NO
    assert set(home_clean_sheet.allowed_values) == {"YES", "NO"}
    assert home_clean_sheet.resolver_key == "football.home_clean_sheet"


@pytest.mark.asyncio
async def test_seed_is_idempotent(seeder, market_repo):
    await seeder.seed(T0)
    await seeder.seed(T0)  # must not raise on re-run

    markets = await market_repo.list_by_sport("football")
    assert len(markets) == len(MARKETS)
    assert all(m.status is MarketStatus.PRODUCTION for m in markets)
