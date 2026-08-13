from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.predictions.application.windowed_feature_engineering_service import (
    TRANSFER_ACTIVITY_WINDOW_DAYS,
    baseball_form_calculator,
    basketball_form_calculator,
    football_fixture_expected_goals_calculator,
    football_fixture_form_differential_calculator,
    football_fixture_stat_differential_calculators,
    football_form_calculator,
    football_lineup_continuity_calculators,
    football_transfer_activity_calculators,
    table_tennis_form_calculator,
)
from modules.features.domain.value_objects import EntityType, FeatureKey
from modules.sports.domain.entities import Fixture, Lineup, LineupSlot, TeamStatistics, Transfer
from modules.sports.domain.value_objects import (
    EntityId,
    FixtureId,
    FixtureStatus,
    LineupId,
    LineupRole,
    MatchId,
    PlayerId,
    SeasonId,
    TeamId,
)

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
    store: list = field(default_factory=list)  # list[tuple[TeamId, Lineup, datetime]]

    def add(self, team_id, lineup, scheduled_at):
        self.store.append((team_id, lineup, scheduled_at))

    async def list_recent_by_team(self, team_id, before, limit=10):
        matches = [
            lineup for tid, lineup, scheduled_at in sorted(self.store, key=lambda row: row[2], reverse=True)
            if tid == team_id and scheduled_at < before
        ]
        return matches[:limit]


@pytest.fixture
def lineups_repo():
    return InMemoryLineupRepository()


def _lineup(team_id, player_ids, availability_classification="VERIFIED_PRE_MATCH", information_available_at=None):
    return Lineup(
        id=LineupId(uuid4()),
        match_id=MatchId(uuid4()),
        team_id=team_id,
        slots=tuple(LineupSlot(player_id=PlayerId(pid), role=LineupRole.STARTER) for pid in player_ids),
        availability_classification=availability_classification,
        information_available_at=information_available_at,
    )


@dataclass
class InMemoryTransferRepository:
    store: list = field(default_factory=list)  # list[Transfer]

    def add(self, transfer):
        self.store.append(transfer)

    async def list_by_team(self, team_id):
        return [t for t in self.store if t.from_team_id == team_id or t.to_team_id == team_id]


@pytest.fixture
def transfers_repo():
    return InMemoryTransferRepository()


def _transfer(
    team_id, effective_date, availability_classification="VERIFIED_PRE_MATCH", is_incoming=True,
):
    return Transfer(
        id=EntityId(uuid4()),
        player_id=PlayerId(uuid4()),
        from_team_id=None if is_incoming else team_id,
        to_team_id=team_id if is_incoming else None,
        effective_date=effective_date,
        availability_classification=availability_classification,
    )


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
async def test_registered_features_use_a_day_long_ttl_not_the_one_hour_default(
    registration, store, team_statistics_repo, fixtures_repo
):
    """These features only change once per fixture-reconciliation cycle, not continuously — the
    registry's generic 3600s default (built for live/streaming data) would make
    `PredictionContextBuilder`'s TTL-aware freshness scoring treat a normal few-hours-old value as
    maximally stale. Covers all three calculator families: TEAM-scoped rolling average,
    FIXTURE-scoped differential, and FIXTURE-scoped expected-goals."""
    form = football_form_calculator(registration, store, team_statistics_repo)
    await form.ensure_registered(T0)
    form_definition = await registration.definitions.get(FeatureKey(form.feature_key))
    assert form_definition.online_ttl_seconds == 24 * 3600

    differential = football_fixture_form_differential_calculator(registration, store, team_statistics_repo)
    await differential.ensure_registered(T0)
    differential_definition = await registration.definitions.get(FeatureKey(differential.feature_key))
    assert differential_definition.online_ttl_seconds == 24 * 3600

    expected_goals = football_fixture_expected_goals_calculator(registration, store, fixtures_repo)
    await expected_goals.ensure_registered(T0)
    home_definition = await registration.definitions.get(FeatureKey(expected_goals.home_feature_key))
    assert home_definition.online_ttl_seconds == 24 * 3600


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
async def test_fixture_form_differential_joins_home_and_away_team_form(registration, store, team_statistics_repo):
    calculator = football_fixture_form_differential_calculator(registration, store, team_statistics_repo, window=2)
    home_id, away_id = TeamId(uuid4()), TeamId(uuid4())
    team_statistics_repo.add(home_id, {"shots_on_target": 8}, T0.replace(day=20))
    team_statistics_repo.add(home_id, {"shots_on_target": 6}, T0.replace(day=21))
    team_statistics_repo.add(away_id, {"shots_on_target": 2}, T0.replace(day=20))
    team_statistics_repo.add(away_id, {"shots_on_target": 4}, T0.replace(day=21))

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write("fixture-1", home_id, away_id, T0.replace(day=25))

    assert value.value == pytest.approx(7.0 - 3.0)
    assert value.entity_type == EntityType.FIXTURE
    assert value.entity_id == "fixture-1"
    assert value.feature_key.value == "football.fixture.form_shots_on_target_diff_last2"


@pytest.mark.asyncio
async def test_fixture_form_differential_returns_none_when_either_side_has_no_data(
    registration, store, team_statistics_repo
):
    calculator = football_fixture_form_differential_calculator(registration, store, team_statistics_repo)
    home_id, away_id = TeamId(uuid4()), TeamId(uuid4())
    team_statistics_repo.add(home_id, {"shots_on_target": 8}, T0.replace(day=20))
    # away side has no statistics at all

    await calculator.ensure_registered(T0)
    value = await calculator.compute_and_write("fixture-1", home_id, away_id, T0.replace(day=25))

    assert value is None


@pytest.mark.asyncio
async def test_stat_differential_calculators_covers_shots_on_target_plus_the_five_newly_wired_stats(
    registration, store, team_statistics_repo
):
    """Universal Probability Engine follow-up (2026-08-03): the already-synced-but-previously-
    unused TeamStatistics fields (possession/shots_total/corners/fouls) plus cards (newly synced
    by the same change) all get a real fixture-level differential feature now, built the same way
    shots_on_target already was — not just shots_on_target alone."""
    calculators = football_fixture_stat_differential_calculators(registration, store, team_statistics_repo, window=5)

    stat_keys = {c.stat_key for c in calculators}
    assert stat_keys == {
        "shots_on_target", "possession_pct", "shots_total", "corners", "fouls", "cards_yellow",
    }
    feature_keys = {c.feature_key for c in calculators}
    assert feature_keys == {
        "football.fixture.form_shots_on_target_diff_last5",
        "football.fixture.form_possession_pct_diff_last5",
        "football.fixture.form_shots_total_diff_last5",
        "football.fixture.form_corners_diff_last5",
        "football.fixture.form_fouls_diff_last5",
        "football.fixture.form_cards_yellow_diff_last5",
    }
    # The shots_on_target entry must be identical in shape to the original single-calculator
    # factory — this is additive, not a divergent reimplementation.
    original = football_fixture_form_differential_calculator(registration, store, team_statistics_repo, window=5)
    shots_calculator = next(c for c in calculators if c.stat_key == "shots_on_target")
    assert shots_calculator.feature_key == original.feature_key


@pytest.mark.asyncio
async def test_stat_differential_calculator_computes_a_new_stat_correctly(registration, store, team_statistics_repo):
    """One representative new stat (possession) proves the generic calculator genuinely reads
    the right `stat_set` key end-to-end, not just that it was constructed with the right name."""
    calculators = football_fixture_stat_differential_calculators(registration, store, team_statistics_repo, window=2)
    possession_calculator = next(c for c in calculators if c.stat_key == "possession_pct")
    home_id, away_id = TeamId(uuid4()), TeamId(uuid4())
    team_statistics_repo.add(home_id, {"possession_pct": 60.0}, T0.replace(day=20))
    team_statistics_repo.add(home_id, {"possession_pct": 58.0}, T0.replace(day=21))
    team_statistics_repo.add(away_id, {"possession_pct": 40.0}, T0.replace(day=20))
    team_statistics_repo.add(away_id, {"possession_pct": 42.0}, T0.replace(day=21))

    await possession_calculator.ensure_registered(T0)
    value = await possession_calculator.compute_and_write("fixture-1", home_id, away_id, T0.replace(day=25))

    assert value.value == pytest.approx(59.0 - 41.0)
    assert value.feature_key.value == "football.fixture.form_possession_pct_diff_last2"


@pytest.mark.asyncio
async def test_compute_and_write_raises_if_ensure_registered_was_never_called(registration, store, team_statistics_repo):
    from modules.features.application.feature_store_service import FeatureNotFoundError

    calculator = football_form_calculator(registration, store, team_statistics_repo)
    team_id = TeamId(uuid4())
    team_statistics_repo.add(team_id, {"shots_on_target": 6}, T0.replace(day=20))

    with pytest.raises(FeatureNotFoundError):
        await calculator.compute_and_write(team_id, T0.replace(day=25))


@pytest.mark.asyncio
async def test_expected_goals_calculator_averages_each_sides_own_goals_scored(registration, store, fixtures_repo):
    calculator = football_fixture_expected_goals_calculator(registration, store, fixtures_repo, window=2)
    home_id, away_id = TeamId(uuid4()), TeamId(uuid4())
    # home_id scored 3 then 1 (as home both times) -> average 2.0
    fixtures_repo.add_completed(home_id, TeamId(uuid4()), home_score=3, away_score=0, scheduled_at=T0.replace(day=20))
    fixtures_repo.add_completed(home_id, TeamId(uuid4()), home_score=1, away_score=1, scheduled_at=T0.replace(day=21))
    # away_id scored 2 as away (away_score counts), then 4 as home (home_score counts) -> average 3.0
    fixtures_repo.add_completed(TeamId(uuid4()), away_id, home_score=0, away_score=2, scheduled_at=T0.replace(day=20))
    fixtures_repo.add_completed(away_id, TeamId(uuid4()), home_score=4, away_score=0, scheduled_at=T0.replace(day=21))

    await calculator.ensure_registered(T0)
    home_value, away_value = await calculator.compute_and_write("fixture-1", home_id, away_id, T0.replace(day=25))

    assert home_value.value == pytest.approx(2.0)
    assert home_value.entity_type == EntityType.FIXTURE
    assert home_value.entity_id == "fixture-1"
    assert home_value.feature_key.value == "football.fixture.expected_home_goals"
    assert away_value.value == pytest.approx(3.0)
    assert away_value.feature_key.value == "football.fixture.expected_away_goals"


@pytest.mark.asyncio
async def test_expected_goals_calculator_ignores_incomplete_and_scoreless_fixtures(registration, store, fixtures_repo):
    calculator = football_fixture_expected_goals_calculator(registration, store, fixtures_repo, window=5)
    home_id, away_id = TeamId(uuid4()), TeamId(uuid4())
    fixtures_repo.add_completed(home_id, TeamId(uuid4()), home_score=2, away_score=0, scheduled_at=T0.replace(day=20))
    # a SCHEDULED (not yet played) fixture with no score must not count
    fixtures_repo.store.append(
        Fixture(
            id=FixtureId(uuid4()), season_id=SeasonId(uuid4()), home_team_id=home_id, away_team_id=TeamId(uuid4()),
            venue_id=None, scheduled_at=T0.replace(day=22), status=FixtureStatus.SCHEDULED,
        )
    )

    await calculator.ensure_registered(T0)
    home_value, away_value = await calculator.compute_and_write("fixture-1", home_id, away_id, T0.replace(day=25))

    assert home_value.value == pytest.approx(2.0)  # only the one completed, scored match counted
    assert away_value is None  # away_id has no completed fixtures at all


@pytest.mark.asyncio
async def test_expected_goals_calculator_returns_none_tuple_when_neither_side_has_history(
    registration, store, fixtures_repo
):
    calculator = football_fixture_expected_goals_calculator(registration, store, fixtures_repo)
    home_id, away_id = TeamId(uuid4()), TeamId(uuid4())

    await calculator.ensure_registered(T0)
    home_value, away_value = await calculator.compute_and_write("fixture-1", home_id, away_id, T0)

    assert home_value is None
    assert away_value is None


@pytest.mark.asyncio
async def test_lineup_continuity_computes_overlap_ratio_with_previous_starters(registration, store, lineups_repo):
    home_calc, away_calc = football_lineup_continuity_calculators(registration, store, lineups_repo)
    team_id = TeamId(uuid4())
    p1, p2, p3, p4 = uuid4(), uuid4(), uuid4(), uuid4()
    previous = _lineup(team_id, [p1, p2, p3, p4])
    lineups_repo.add(team_id, previous, T0.replace(day=20))
    # 3 of the previous 4 starters start again -> 0.75
    current = _lineup(team_id, [p1, p2, p3, uuid4()], information_available_at=T0.replace(day=25))

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, current, T0.replace(day=25))

    assert value.value == pytest.approx(0.75)
    assert value.entity_type == EntityType.FIXTURE
    assert value.entity_id == "fixture-1"
    assert value.feature_key.value == "football.fixture.home_lineup_continuity"


@pytest.mark.asyncio
async def test_lineup_continuity_uses_away_feature_key_for_the_away_calculator(registration, store, lineups_repo):
    home_calc, away_calc = football_lineup_continuity_calculators(registration, store, lineups_repo)
    team_id = TeamId(uuid4())
    p1 = uuid4()
    lineups_repo.add(team_id, _lineup(team_id, [p1]), T0.replace(day=20))
    current = _lineup(team_id, [p1], information_available_at=T0.replace(day=25))

    await away_calc.ensure_registered(T0)
    value = await away_calc.compute_and_write("fixture-1", team_id, current, T0.replace(day=25))

    assert value.value == pytest.approx(1.0)
    assert value.feature_key.value == "football.fixture.away_lineup_continuity"


@pytest.mark.asyncio
async def test_lineup_continuity_returns_none_when_current_lineup_is_not_verified_pre_match(
    registration, store, lineups_repo
):
    home_calc, _ = football_lineup_continuity_calculators(registration, store, lineups_repo)
    team_id = TeamId(uuid4())
    p1 = uuid4()
    lineups_repo.add(team_id, _lineup(team_id, [p1]), T0.replace(day=20))
    current = _lineup(team_id, [p1], availability_classification="UNKNOWN_AVAILABILITY_TIME")

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, current, T0.replace(day=25))

    assert value is None


@pytest.mark.asyncio
async def test_lineup_continuity_returns_none_when_no_previous_lineup_exists(registration, store, lineups_repo):
    home_calc, _ = football_lineup_continuity_calculators(registration, store, lineups_repo)
    team_id = TeamId(uuid4())
    current = _lineup(team_id, [uuid4()], information_available_at=T0.replace(day=25))

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, current, T0.replace(day=25))

    assert value is None


@pytest.mark.asyncio
async def test_lineup_continuity_returns_none_when_previous_lineup_has_no_starters(
    registration, store, lineups_repo
):
    home_calc, _ = football_lineup_continuity_calculators(registration, store, lineups_repo)
    team_id = TeamId(uuid4())
    empty_previous = Lineup(id=LineupId(uuid4()), match_id=MatchId(uuid4()), team_id=team_id, slots=())
    lineups_repo.add(team_id, empty_previous, T0.replace(day=20))
    current = _lineup(team_id, [uuid4()], information_available_at=T0.replace(day=25))

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, current, T0.replace(day=25))

    assert value is None


@pytest.mark.asyncio
async def test_lineup_continuity_only_looks_before_information_available_at_not_now(
    registration, store, lineups_repo
):
    """The comparison baseline must be the team's previous lineup as of when *this* fixture's
    lineup became genuinely known (`information_available_at`), not as of `now` — otherwise a
    later-reconciled, later-scheduled lineup for a different fixture could leak into the
    baseline for an earlier one."""
    home_calc, _ = football_lineup_continuity_calculators(registration, store, lineups_repo)
    team_id = TeamId(uuid4())
    p1, p2 = uuid4(), uuid4()
    older = _lineup(team_id, [p1, p2])
    lineups_repo.add(team_id, older, T0.replace(day=15))
    # a lineup scheduled AFTER this fixture's own information_available_at must not count as "previous"
    newer = _lineup(team_id, [p1])
    lineups_repo.add(team_id, newer, T0.replace(month=8, day=30))
    current = _lineup(team_id, [p1, p2], information_available_at=T0.replace(day=20))

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, current, T0.replace(month=9, day=10))

    assert value.value == pytest.approx(1.0)  # matched against `older` (2/2), not `newer` (would be 1/1 too, but wrong basis)


@pytest.mark.asyncio
async def test_lineup_continuity_ensure_registered_sets_pre_match_safe_leakage_classification(
    registration, store, lineups_repo
):
    home_calc, away_calc = football_lineup_continuity_calculators(registration, store, lineups_repo)

    await home_calc.ensure_registered(T0)
    await away_calc.ensure_registered(T0)

    home_definition = await registration.definitions.get(FeatureKey(home_calc.feature_key))
    away_definition = await registration.definitions.get(FeatureKey(away_calc.feature_key))
    assert home_definition.leakage_classification == "PRE_MATCH_SAFE"
    assert away_definition.leakage_classification == "PRE_MATCH_SAFE"
    assert home_definition.is_consumable()
    assert home_definition.online_ttl_seconds == 24 * 3600


@pytest.mark.asyncio
async def test_lineup_continuity_ensure_registered_is_idempotent(registration, store, lineups_repo):
    home_calc, _ = football_lineup_continuity_calculators(registration, store, lineups_repo)

    await home_calc.ensure_registered(T0)
    await home_calc.ensure_registered(T0)  # must not raise FeatureAlreadyRegisteredError

    definition = await registration.definitions.get(FeatureKey(home_calc.feature_key))
    assert definition is not None
    assert definition.is_consumable()


@pytest.mark.asyncio
async def test_transfer_activity_counts_verified_transfers_within_window(registration, store, transfers_repo):
    home_calc, _ = football_transfer_activity_calculators(registration, store, transfers_repo)
    team_id = TeamId(uuid4())
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=5), is_incoming=True))
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=10), is_incoming=False))
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=TRANSFER_ACTIVITY_WINDOW_DAYS + 5)))  # too old

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, T0)

    assert value.value == pytest.approx(2.0)
    assert value.entity_type == EntityType.FIXTURE
    assert value.entity_id == "fixture-1"
    assert value.feature_key.value == "football.fixture.home_transfer_activity"


@pytest.mark.asyncio
async def test_transfer_activity_excludes_unknown_availability_transfers(registration, store, transfers_repo):
    """Covers both the "manual/backfill sync" and "unknown timestamp" exclusion scenarios — a
    transfer synced via SyncTrigger.MANUAL/BACKFILL lands as UNKNOWN_AVAILABILITY_TIME at the
    reconciliation layer (modules.ingestion.application.provenance.classify_availability), and
    this calculator must never count it regardless of how recent its effective_date is."""
    home_calc, _ = football_transfer_activity_calculators(registration, store, transfers_repo)
    team_id = TeamId(uuid4())
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=1), availability_classification="VERIFIED_PRE_MATCH"))
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=1), availability_classification="UNKNOWN_AVAILABILITY_TIME"))

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, T0)

    assert value.value == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_transfer_activity_excludes_non_verified_pre_match_classifications(registration, store, transfers_repo):
    """The count filter is a strict `== VERIFIED_PRE_MATCH`, not merely "not UNKNOWN" — any other
    classification (EXPIRED/POST_MATCH/INVALID) must also be excluded."""
    home_calc, _ = football_transfer_activity_calculators(registration, store, transfers_repo)
    team_id = TeamId(uuid4())
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=1), availability_classification="VERIFIED_PRE_MATCH"))
    for bad_classification in ("POST_MATCH", "EXPIRED", "INVALID"):
        transfers_repo.add(_transfer(team_id, T0 - timedelta(days=1), availability_classification=bad_classification))

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, T0)

    assert value.value == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_transfer_activity_returns_none_when_no_verified_transfers_exist_at_all(
    registration, store, transfers_repo
):
    """No verified transfer history at all means unavailable, not a fabricated zero — even when
    UNKNOWN-classified records exist, since a 0 here would misleadingly read as 'no squad churn'
    rather than 'no verified visibility.'"""
    home_calc, _ = football_transfer_activity_calculators(registration, store, transfers_repo)
    team_id = TeamId(uuid4())
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=1), availability_classification="UNKNOWN_AVAILABILITY_TIME"))

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, T0)

    assert value is None


@pytest.mark.asyncio
async def test_transfer_activity_returns_genuine_zero_when_verified_history_exists_outside_window(
    registration, store, transfers_repo
):
    """A team WITH verified transfer coverage but none inside the recent window gets a real 0.0 —
    distinct from the "no verified data at all" None case above."""
    home_calc, _ = football_transfer_activity_calculators(registration, store, transfers_repo)
    team_id = TeamId(uuid4())
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=TRANSFER_ACTIVITY_WINDOW_DAYS + 1)))

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, T0)

    assert value is not None
    assert value.value == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_transfer_activity_excludes_future_dated_transfers(registration, store, transfers_repo):
    """A transfer whose effective_date is at or after `now` (not yet in effect, or a same-instant
    edge) must not count as already-happened churn — historical leakage prevention."""
    home_calc, _ = football_transfer_activity_calculators(registration, store, transfers_repo)
    team_id = TeamId(uuid4())
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=1)))  # counts
    transfers_repo.add(_transfer(team_id, T0))  # exactly now -> excluded
    transfers_repo.add(_transfer(team_id, T0 + timedelta(days=5)))  # future -> excluded

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, T0)

    assert value.value == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_transfer_activity_window_boundary_is_inclusive_of_start_exclusive_of_now(
    registration, store, transfers_repo
):
    home_calc, _ = football_transfer_activity_calculators(registration, store, transfers_repo)
    team_id = TeamId(uuid4())
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=TRANSFER_ACTIVITY_WINDOW_DAYS)))  # exactly at window start -> counts
    transfers_repo.add(_transfer(team_id, T0 - timedelta(days=TRANSFER_ACTIVITY_WINDOW_DAYS, seconds=1)))  # just outside -> excluded

    await home_calc.ensure_registered(T0)
    value = await home_calc.compute_and_write("fixture-1", team_id, T0)

    assert value.value == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_transfer_activity_home_and_away_use_distinct_feature_keys_and_team_filters(
    registration, store, transfers_repo
):
    home_calc, away_calc = football_transfer_activity_calculators(registration, store, transfers_repo)
    home_team_id, away_team_id = TeamId(uuid4()), TeamId(uuid4())
    transfers_repo.add(_transfer(home_team_id, T0 - timedelta(days=1)))
    transfers_repo.add(_transfer(away_team_id, T0 - timedelta(days=1)))
    transfers_repo.add(_transfer(away_team_id, T0 - timedelta(days=2)))

    await home_calc.ensure_registered(T0)
    await away_calc.ensure_registered(T0)
    home_value = await home_calc.compute_and_write("fixture-1", home_team_id, T0)
    away_value = await away_calc.compute_and_write("fixture-1", away_team_id, T0)

    assert home_value.value == pytest.approx(1.0)
    assert home_value.feature_key.value == "football.fixture.home_transfer_activity"
    assert away_value.value == pytest.approx(2.0)
    assert away_value.feature_key.value == "football.fixture.away_transfer_activity"


@pytest.mark.asyncio
async def test_transfer_activity_ensure_registered_sets_pre_match_safe_leakage_classification(
    registration, store, transfers_repo
):
    home_calc, away_calc = football_transfer_activity_calculators(registration, store, transfers_repo)

    await home_calc.ensure_registered(T0)
    await away_calc.ensure_registered(T0)

    home_definition = await registration.definitions.get(FeatureKey(home_calc.feature_key))
    away_definition = await registration.definitions.get(FeatureKey(away_calc.feature_key))
    assert home_definition.leakage_classification == "PRE_MATCH_SAFE"
    assert away_definition.leakage_classification == "PRE_MATCH_SAFE"
    assert home_definition.is_consumable()
    assert home_definition.online_ttl_seconds == 24 * 3600


@pytest.mark.asyncio
async def test_transfer_activity_ensure_registered_is_idempotent(registration, store, transfers_repo):
    home_calc, _ = football_transfer_activity_calculators(registration, store, transfers_repo)

    await home_calc.ensure_registered(T0)
    await home_calc.ensure_registered(T0)  # must not raise FeatureAlreadyRegisteredError

    definition = await registration.definitions.get(FeatureKey(home_calc.feature_key))
    assert definition is not None
    assert definition.is_consumable()
