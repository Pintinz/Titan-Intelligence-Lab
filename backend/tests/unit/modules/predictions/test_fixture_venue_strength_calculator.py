from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.predictions.application.windowed_feature_engineering_service import (
    football_fixture_venue_strength_calculator,
)
from modules.sports.domain.entities import Fixture
from modules.sports.domain.value_objects import FixtureId, FixtureStatus, SeasonId, SportId, TeamId

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)
SEASON = SeasonId(uuid4())
OTHER_SEASON = SeasonId(uuid4())
SPORT = SportId(uuid4())


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
class InMemoryFixtureRepository:
    store: list = field(default_factory=list)  # list[Fixture]

    def add(
        self, *, home_team_id, away_team_id, home_score, away_score, scheduled_at,
        status: FixtureStatus = FixtureStatus.COMPLETED, season_id: SeasonId = SEASON,
    ) -> None:
        self.store.append(
            Fixture(
                id=FixtureId(uuid4()), season_id=season_id, home_team_id=home_team_id,
                away_team_id=away_team_id, venue_id=None, scheduled_at=scheduled_at,
                status=status, home_score=home_score, away_score=away_score,
            )
        )

    async def list_by_sport(self, sport_id, *, competition_id=None, season_id=None, status=None):
        results = self.store
        if season_id is not None:
            results = [f for f in results if f.season_id == season_id]
        if status is not None:
            results = [f for f in results if f.status.value == status]
        return list(results)

    async def list_recent_by_team(self, team_id, before, limit=10):
        matches = [
            f for f in sorted(self.store, key=lambda f: f.scheduled_at, reverse=True)
            if (f.home_team_id == team_id or f.away_team_id == team_id) and f.scheduled_at < before
        ]
        return matches[:limit]


@pytest.fixture
def fixtures_repo():
    return InMemoryFixtureRepository()


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


def _seed_league_baseline(fixtures_repo, *, count=10, home_goals=2, away_goals=1, season=SEASON, before=T0):
    for i in range(count):
        fixtures_repo.add(
            home_team_id=TeamId(uuid4()), away_team_id=TeamId(uuid4()),
            home_score=home_goals, away_score=away_goals,
            scheduled_at=before.replace(day=1 + i), season_id=season,
        )


@pytest.mark.asyncio
async def test_returns_all_none_when_league_sample_is_below_minimum(registration, store, fixtures_repo):
    calculator = football_fixture_venue_strength_calculator(registration, store, fixtures_repo, window=5)
    _seed_league_baseline(fixtures_repo, count=3)  # below default min_league_sample=10
    home_team, away_team = TeamId(uuid4()), TeamId(uuid4())

    await calculator.ensure_registered(T0)
    result = await calculator.compute_and_write(
        str(uuid4()), home_team, away_team, SPORT, SEASON, T0.replace(day=25),
    )

    assert result == (None, None, None, None)


@pytest.mark.asyncio
async def test_computes_attack_and_defence_strength_relative_to_league_venue_baseline(
    registration, store, fixtures_repo,
):
    calculator = football_fixture_venue_strength_calculator(registration, store, fixtures_repo, window=5)
    _seed_league_baseline(fixtures_repo, count=10, home_goals=2, away_goals=1)

    home_team, away_team = TeamId(uuid4()), TeamId(uuid4())
    # Seeded under a different season so these don't dilute SEASON's own league-wide baseline —
    # `_team_venue_rate` (list_recent_by_team) is season-agnostic by design, same as every other
    # per-team rolling calculator in this module, so the team's own rate is still picked up.
    # Home team scores 4 at home (twice league's home average of 2) and concedes 1 (league away avg).
    for i in range(3):
        fixtures_repo.add(
            home_team_id=home_team, away_team_id=TeamId(uuid4()), home_score=4, away_score=1,
            scheduled_at=T0.replace(day=10 + i), season_id=OTHER_SEASON,
        )
    # Away team scores 2 away (twice league's away average of 1) and concedes 2 (league home avg).
    for i in range(3):
        fixtures_repo.add(
            home_team_id=TeamId(uuid4()), away_team_id=away_team, home_score=2, away_score=2,
            scheduled_at=T0.replace(day=10 + i), season_id=OTHER_SEASON,
        )

    await calculator.ensure_registered(T0)
    home_attack, home_defence, away_attack, away_defence = await calculator.compute_and_write(
        str(uuid4()), home_team, away_team, SPORT, SEASON, T0.replace(day=25),
    )

    assert home_attack.value == pytest.approx(2.0)  # 4 / league_home_avg(2)
    assert home_defence.value == pytest.approx(1.0)  # 1 / league_away_avg(1)
    assert away_attack.value == pytest.approx(2.0)  # 2 / league_away_avg(1)
    assert away_defence.value == pytest.approx(1.0)  # 2 / league_home_avg(2)


@pytest.mark.asyncio
async def test_restricts_team_rate_to_matches_at_the_relevant_venue_only(registration, store, fixtures_repo):
    calculator = football_fixture_venue_strength_calculator(registration, store, fixtures_repo, window=5)
    _seed_league_baseline(fixtures_repo, count=10, home_goals=2, away_goals=1)

    home_team, away_team = TeamId(uuid4()), TeamId(uuid4())
    # home_team's AWAY fixtures should never feed its home_attack/home_defence rate.
    fixtures_repo.add(
        home_team_id=TeamId(uuid4()), away_team_id=home_team, home_score=0, away_score=9,
        scheduled_at=T0.replace(day=11),
    )
    # home_team has no HOME fixtures at all -> home_attack/home_defence stay honestly unavailable.
    fixtures_repo.add(
        home_team_id=away_team, away_team_id=TeamId(uuid4()), home_score=1, away_score=1,
        scheduled_at=T0.replace(day=11),
    )

    await calculator.ensure_registered(T0)
    home_attack, home_defence, away_attack, away_defence = await calculator.compute_and_write(
        str(uuid4()), home_team, away_team, SPORT, SEASON, T0.replace(day=25),
    )

    assert home_attack is None
    assert home_defence is None
    assert away_attack is None
    assert away_defence is None


@pytest.mark.asyncio
async def test_ignores_fixtures_scheduled_at_or_after_the_prediction_cutoff(registration, store, fixtures_repo):
    calculator = football_fixture_venue_strength_calculator(registration, store, fixtures_repo, window=5)
    now = T0.replace(day=15)
    _seed_league_baseline(fixtures_repo, count=10, home_goals=2, away_goals=1, before=T0.replace(month=6))

    home_team, away_team = TeamId(uuid4()), TeamId(uuid4())
    # A future (post-cutoff) home fixture with an inflated score must not leak into the rate.
    fixtures_repo.add(
        home_team_id=home_team, away_team_id=TeamId(uuid4()), home_score=99, away_score=0,
        scheduled_at=now.replace(month=8),
    )
    # A future league fixture must not leak into the league baseline either.
    fixtures_repo.add(
        home_team_id=TeamId(uuid4()), away_team_id=TeamId(uuid4()), home_score=99, away_score=99,
        scheduled_at=now.replace(month=8),
    )

    await calculator.ensure_registered(T0)
    home_attack, _, _, _ = await calculator.compute_and_write(
        str(uuid4()), home_team, away_team, SPORT, SEASON, now,
    )

    assert home_attack is None  # home_team has zero eligible (pre-cutoff) home fixtures


@pytest.mark.asyncio
async def test_registers_four_distinct_feature_keys_idempotently(registration, store, fixtures_repo):
    calculator = football_fixture_venue_strength_calculator(registration, store, fixtures_repo)

    await calculator.ensure_registered(T0)
    await calculator.ensure_registered(T0)  # idempotent — must not raise on re-registration

    for feature_key in (
        "football.fixture.home_attack_strength",
        "football.fixture.home_defence_strength",
        "football.fixture.away_attack_strength",
        "football.fixture.away_defence_strength",
    ):
        from modules.features.domain.value_objects import FeatureKey

        definition = await registration.definitions.get(FeatureKey(feature_key))
        assert definition is not None
