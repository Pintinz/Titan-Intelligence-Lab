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
    football_fixture_venue_strength_calculator,
    football_form_calculator,
    football_lineup_continuity_calculators,
    football_transfer_activity_calculators,
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


@dataclass
class InMemoryLineupRepository:
    store: list = field(default_factory=list)

    async def list_recent_by_team(self, team_id, before, limit=10):
        return []


@pytest.fixture
def lineups_repo():
    return InMemoryLineupRepository()


@dataclass
class InMemoryTransferRepository:
    store: list = field(default_factory=list)

    async def list_by_team(self, team_id):
        return []


@pytest.fixture
def transfers_repo():
    return InMemoryTransferRepository()


@dataclass
class InMemoryNewsEventRepositoryForSeeding:
    store: list = field(default_factory=list)

    async def list_for_entity(self, entity_ref):
        return []


@dataclass
class InMemoryKGNodeRepositoryForSeeding:
    store: list = field(default_factory=list)

    async def get_by_entity_ref(self, node_type, entity_ref):
        return None


@dataclass
class InMemoryPlayerRepositoryForSeeding:
    store: list = field(default_factory=list)

    async def list_by_team(self, team_id):
        return []


@pytest.fixture
def news_market_impact_engine(registration, store):
    from modules.predictions.application.news_market_impact_engine import NewsMarketImpactEngine

    return NewsMarketImpactEngine(
        registration=registration,
        store=store,
        events=InMemoryNewsEventRepositoryForSeeding(),
        kg_nodes=InMemoryKGNodeRepositoryForSeeding(),
        players=InMemoryPlayerRepositoryForSeeding(),
        sport_code="football",
    )


@pytest.fixture
def manager_change_calculator(registration, store):
    from modules.predictions.application.manager_change_context_calculator import ManagerChangeContextCalculator

    return ManagerChangeContextCalculator(
        registration=registration,
        store=store,
        events=InMemoryNewsEventRepositoryForSeeding(),
        kg_nodes=InMemoryKGNodeRepositoryForSeeding(),
        sport_code="football",
    )


@pytest.fixture
def seeder(
    registration, store, market_registry, mapping_service, team_statistics_repo, fixtures_repo, lineups_repo,
    transfers_repo, news_market_impact_engine, manager_change_calculator,
):
    return FootballMarketSeeder(
        registration=registration,
        markets=market_registry,
        mappings=mapping_service,
        windowed_calculator=football_form_calculator(registration, store, team_statistics_repo),
        differential_calculators=football_fixture_stat_differential_calculators(registration, store, team_statistics_repo),
        expected_goals_calculator=football_fixture_expected_goals_calculator(registration, store, fixtures_repo),
        lineup_continuity_calculators=football_lineup_continuity_calculators(registration, store, lineups_repo),
        transfer_activity_calculators=football_transfer_activity_calculators(registration, store, transfers_repo),
        venue_strength_calculator=football_fixture_venue_strength_calculator(registration, store, fixtures_repo),
        news_market_impact_engine=news_market_impact_engine,
        manager_change_calculator=manager_change_calculator,
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
    # label space, and now (post-M24) a real resolver_key too — the resolver itself still
    # honestly resolves nothing in production until a provider adapter starts parsing a football
    # fixture's half-time score (see outcome_resolution_service.py's docs), but the seeding
    # contract correctly reflects that the resolution *logic* now exists.
    first_half_winner = await market_repo.get_by_key("football.first_half_winner")
    assert first_half_winner.outcome_type is OutcomeType.HOME_DRAW_AWAY
    assert set(first_half_winner.allowed_values) == {"HOME_WIN", "DRAW", "AWAY_WIN"}
    assert first_half_winner.resolver_key == "football.first_half_winner"

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


_HEURISTIC_MARKET_KEYS = (
    "football.first_half_winner",
    "football.second_half_winner",
    "football.first_half_goals",
    "football.first_half_both_teams_to_score",
)


@pytest.mark.asyncio
async def test_seed_marks_structured_intel_features_optional_on_heuristic_markets(
    seeder, feature_mapping_repo, market_repo
):
    """Milestone 8 — these four markets are served live by a formula predictor (not a trained
    model), and zero fixtures anywhere have a non-null lineup-continuity/transfer-activity value
    yet. is_required=True here would raise MissingRequiredFeatureError on every prediction these
    markets serve today — the same class of incident `_NEW_STAT_DIFFERENTIAL_FEATURES` already
    guards against."""
    from modules.predictions.football.market_seeding import _LINEUP_CONTINUITY_FEATURES, _TRANSFER_ACTIVITY_FEATURES

    await seeder.seed(T0)

    for market_key in _HEURISTIC_MARKET_KEYS:
        market = await market_repo.get_by_key(market_key)
        mappings = {m.feature_key: m.is_required for m in await feature_mapping_repo.list_by_market(market.id)}
        for feature_key in (*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES):
            assert mappings[feature_key] is False, f"{feature_key} must be optional on {market_key}"


@pytest.mark.asyncio
async def test_seed_relaxes_structured_intel_features_to_optional_on_trained_markets(
    seeder, feature_mapping_repo, market_repo
):
    """Superseded by Post-M24 Phase 17 (docs/post_m24_phase17_football_prediction_recovery_report.md).

    Milestones 6/7 originally kept lineup_continuity/transfer_activity required=True on these 14
    genuinely-trained markets ("a training dataset should demand the pre-match feature exist").
    Milestone 16 later confirmed, for football.both_teams_to_score specifically, that this demand
    can structurally never be met for backfilled historical fixtures (VERIFIED_PRE_MATCH is only
    ever producible by a live LIVE_SCHEDULED sync) and deliberately chose to keep the requirement
    and serve an honest 409 rather than relax it.

    Phase 17 made the opposite, later call, for all 14 markets: every one of them already had a
    real, empirically-selected Champion whose training data never saw these features either (0%
    coverage in the persisted dataset, not just at inference) — the requirement was blocking a
    Champion that was already trained without this signal, not protecting training-data integrity.
    Relaxing to optional (the same pattern Milestone 8 already used for the 4 heuristic markets)
    unblocks 12 real, working predictions; the features remain fully wired and will be consumed the
    moment real pre-match coverage exists for a future fixture. This is a deliberate, evidence-backed
    reversal of the M16 policy, not an oversight — see the Phase 17 report for the full trade-off."""
    from modules.predictions.football.market_seeding import _LINEUP_CONTINUITY_FEATURES, _TRANSFER_ACTIVITY_FEATURES

    await seeder.seed(T0)

    trained_market_keys = {
        spec["market_key"] for spec in MARKETS
        if "football.fixture.home_lineup_continuity" in spec["required_features"]
        and spec["market_key"] not in _HEURISTIC_MARKET_KEYS
    }
    assert len(trained_market_keys) == 14

    for market_key in trained_market_keys:
        market = await market_repo.get_by_key(market_key)
        mappings = {m.feature_key: m.is_required for m in await feature_mapping_repo.list_by_market(market.id)}
        for feature_key in (*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES):
            assert mappings[feature_key] is False, f"{feature_key} must be optional on {market_key} (Phase 17)"


@pytest.mark.asyncio
async def test_seed_applies_conservative_weights_to_structured_intel_features_on_heuristic_markets(
    seeder, feature_mapping_repo, market_repo
):
    """Mirrors test_seed_applies_conservative_weights_to_new_stat_differential_features: transfer
    activity is an unbounded non-negative count, the exact shape that caused the 2026-08-06
    sigmoid-saturation incident, so it must not get the weight=1.0 default."""
    from modules.predictions.football.market_seeding import STRUCTURED_INTEL_OPTIONAL_WEIGHTS

    await seeder.seed(T0)

    market = await market_repo.get_by_key("football.first_half_winner")
    mappings = {m.feature_key: m.weight for m in await feature_mapping_repo.list_by_market(market.id)}

    for feature_key, expected_weight in STRUCTURED_INTEL_OPTIONAL_WEIGHTS.items():
        assert mappings[feature_key] == pytest.approx(expected_weight)
        assert expected_weight < 1.0


@pytest.mark.asyncio
async def test_seed_wires_news_goal_impact_features_as_optional_on_goal_markets(
    seeder, feature_mapping_repo, market_repo
):
    """Superseded by Post-M24 Phase 17 — see the sibling
    test_seed_relaxes_structured_intel_features_to_optional_on_trained_markets docstring for the
    full reasoning. news.football.*_goal_impact was required=True (Milestone 9's default) until
    Phase 17 confirmed it, too, is 0%-populated in every persisted training sample for these
    markets and relaxed it to optional alongside lineup/transfer."""
    from modules.predictions.football.market_seeding import _NEWS_GOAL_IMPACT_FEATURES

    await seeder.seed(T0)

    goal_markets = (
        "football.total_goals_over_under", "football.total_goals_over_under_0_5",
        "football.total_goals_over_under_1_5", "football.total_goals_over_under_3_5",
        "football.total_goals_over_under_4_5", "football.home_team_total_goals", "football.away_team_total_goals",
    )
    for market_key in goal_markets:
        market = await market_repo.get_by_key(market_key)
        mappings = {m.feature_key: m.is_required for m in await feature_mapping_repo.list_by_market(market.id)}
        for feature_key in _NEWS_GOAL_IMPACT_FEATURES:
            assert mappings[feature_key] is False, f"{feature_key} must be optional on {market_key} (Phase 17)"


@pytest.mark.asyncio
async def test_seed_wires_news_clean_sheet_impact_features_as_optional_on_clean_sheet_markets(
    seeder, feature_mapping_repo, market_repo
):
    """Superseded by Post-M24 Phase 17 — see
    test_seed_relaxes_structured_intel_features_to_optional_on_trained_markets for the reasoning."""
    from modules.predictions.football.market_seeding import _NEWS_CLEAN_SHEET_IMPACT_FEATURES

    await seeder.seed(T0)

    clean_sheet_markets = (
        "football.home_clean_sheet", "football.away_clean_sheet",
        "football.home_win_to_nil", "football.away_win_to_nil",
    )
    for market_key in clean_sheet_markets:
        market = await market_repo.get_by_key(market_key)
        mappings = {m.feature_key: m.is_required for m in await feature_mapping_repo.list_by_market(market.id)}
        for feature_key in _NEWS_CLEAN_SHEET_IMPACT_FEATURES:
            assert mappings[feature_key] is False, f"{feature_key} must be optional on {market_key} (Phase 17)"


@pytest.mark.asyncio
async def test_seed_wires_news_btts_impact_features_only_on_btts_market(seeder, feature_mapping_repo, market_repo):
    """Market-specific, not generic: the BTTS dimension must land on both_teams_to_score and
    nowhere else — not even on the goal/clean-sheet markets that share its INJURY event source."""
    from modules.predictions.football.market_seeding import _NEWS_BTTS_IMPACT_FEATURES

    await seeder.seed(T0)

    btts_market = await market_repo.get_by_key("football.both_teams_to_score")
    btts_mappings = {m.feature_key for m in await feature_mapping_repo.list_by_market(btts_market.id)}
    for feature_key in _NEWS_BTTS_IMPACT_FEATURES:
        assert feature_key in btts_mappings

    unrelated_market = await market_repo.get_by_key("football.total_goals_over_under")
    unrelated_mappings = {m.feature_key for m in await feature_mapping_repo.list_by_market(unrelated_market.id)}
    for feature_key in _NEWS_BTTS_IMPACT_FEATURES:
        assert feature_key not in unrelated_mappings


@pytest.mark.asyncio
async def test_seed_does_not_wire_news_features_into_unrelated_markets(seeder, feature_mapping_repo, market_repo):
    """football.correct_score and football.match_winner are neither goal/clean-sheet/BTTS
    target markets — none of the six news feature keys should appear on them."""
    from modules.predictions.football.market_seeding import (
        _NEWS_BTTS_IMPACT_FEATURES,
        _NEWS_CLEAN_SHEET_IMPACT_FEATURES,
        _NEWS_GOAL_IMPACT_FEATURES,
    )

    await seeder.seed(T0)

    all_news_features = {*_NEWS_GOAL_IMPACT_FEATURES, *_NEWS_CLEAN_SHEET_IMPACT_FEATURES, *_NEWS_BTTS_IMPACT_FEATURES}
    for market_key in ("football.correct_score", "football.match_winner"):
        market = await market_repo.get_by_key(market_key)
        mappings = {m.feature_key for m in await feature_mapping_repo.list_by_market(market.id)}
        assert mappings.isdisjoint(all_news_features), f"news features leaked into {market_key}"


async def test_seed_registers_news_market_impact_feature_keys(seeder):
    """seed() must call news_market_impact_engine.ensure_registered so the six feature keys are
    real Feature Registry entries, not just strings referenced by market_seeding.py."""
    from modules.features.domain.value_objects import FeatureKey
    from modules.predictions.football.market_seeding import (
        _NEWS_BTTS_IMPACT_FEATURES,
        _NEWS_CLEAN_SHEET_IMPACT_FEATURES,
        _NEWS_GOAL_IMPACT_FEATURES,
    )

    await seeder.seed(T0)

    for feature_key in (*_NEWS_GOAL_IMPACT_FEATURES, *_NEWS_CLEAN_SHEET_IMPACT_FEATURES, *_NEWS_BTTS_IMPACT_FEATURES):
        definition = await seeder.registration.definitions.get(FeatureKey(feature_key))
        assert definition is not None
        assert definition.leakage_classification == "PRE_MATCH_SAFE"


def test_both_teams_to_score_structured_intel_features_relaxed_to_optional_by_phase_17():
    """Milestone 16 (docs/milestone16_preimplementation_audit.md) found that
    football.both_teams_to_score's news + lineup-continuity + transfer-activity keys are required
    but never populated (root cause: VERIFIED_PRE_MATCH is only producible by a genuine
    LIVE_SCHEDULED sync, structurally impossible for the fixtures already backfilled into training
    data), and deliberately chose to keep all six required and serve an honest 409 from
    prediction_router.py rather than relax them — a considered call locked down by this test's
    original (now-superseded) assertion.

    Post-M24 Phase 17 (docs/post_m24_phase17_football_prediction_recovery_report.md) made the
    opposite call, explicitly and with full awareness of Milestone 16's reasoning: the same
    six-feature blocker exists on 13 other genuinely-trained markets whose real Champions were
    never trained with this signal either, and the product decision was to serve those 12 markets'
    real predictions today (features remain fully wired, will populate the moment real pre-match
    coverage exists) rather than hold every one of them to the same honest-409 standard Milestone
    16 chose for this one market alone. This test now asserts the Phase 17 state, superseding the
    Milestone 16 lock-down — not because Milestone 16 was wrong, but because a later, explicit
    decision reweighted the same trade-off differently. Do not re-flip this test back to asserting
    `required_features` without another equally explicit decision."""
    from modules.predictions.football.market_seeding import (
        _LINEUP_CONTINUITY_FEATURES,
        _NEWS_BTTS_IMPACT_FEATURES,
        _TRANSFER_ACTIVITY_FEATURES,
    )

    spec = next(m for m in MARKETS if m["market_key"] == "football.both_teams_to_score")

    for feature_key in (*_NEWS_BTTS_IMPACT_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES):
        assert feature_key in spec["required_features"]  # still declared — the mapping still exists
        assert feature_key in spec["optional_features"]  # but Phase 17 relaxed is_required to False
