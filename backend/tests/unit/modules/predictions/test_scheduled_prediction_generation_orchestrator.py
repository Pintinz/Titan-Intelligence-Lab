from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from modules.predictions.application.feature_market_mapping_service import MissingRequiredFeatureError
from modules.predictions.application.prediction_cache_service import MarketNotFoundError
from modules.predictions.application.prediction_context_builder import MarketNotInProductionError, NoChampionModelError
from modules.predictions.application.scheduled_prediction_generation_orchestrator import (
    ScheduledPredictionGenerationOrchestrator,
)
from modules.predictions.domain.entities import MarketDefinition
from modules.predictions.domain.value_objects import MarketId, MarketKind, MarketStatus, PredictionStatus, TargetType
from modules.sports.domain.entities import Sport
from modules.sports.domain.value_objects import FixtureId, SportCode, SportId

T0 = datetime(2026, 8, 26, tzinfo=timezone.utc)


def _market(key: str, sport_code: str = "football", status: MarketStatus = MarketStatus.PRODUCTION) -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key=key, sport_code=sport_code, name=key, category="match_outcome",
        market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION, status=status,
        confidence_threshold=0.5,
    )


@dataclass
class _Fixture:
    id: FixtureId
    scheduled_at: datetime
    status: str = "scheduled"


@dataclass
class FakeFixtureRepository:
    by_sport: dict = field(default_factory=dict)  # sport_id -> list[_Fixture]

    async def list_by_sport(self, sport_id, *, competition_id=None, season_id=None, status=None):
        fixtures = self.by_sport.get(sport_id, [])
        if status is not None:
            fixtures = [f for f in fixtures if f.status == status]
        return fixtures


@dataclass
class FakeSportRepository:
    by_code: dict = field(default_factory=dict)  # SportCode -> Sport

    async def get_by_code(self, code):
        return self.by_code.get(code)


@dataclass
class FakePredictionCacheService:
    """Records every (market_key, subject_ref) it was asked to generate; returns a PUBLISHED
    stub unless `raise_for` names that exact pair, in which case it raises the given error —
    exactly the seam the orchestrator's own per-pair error isolation needs to prove itself against."""

    calls: list = field(default_factory=list)
    raise_for: dict = field(default_factory=dict)  # (market_key, subject_ref) -> Exception
    status_for: dict = field(default_factory=dict)  # (market_key, subject_ref) -> PredictionStatus

    async def get_or_generate(self, market_key, entity_type, entity_id, subject_ref, now, actor="prediction-engine"):
        self.calls.append((market_key, subject_ref, actor))
        key = (market_key, subject_ref)
        if key in self.raise_for:
            raise self.raise_for[key]
        status = self.status_for.get(key, PredictionStatus.PUBLISHED)
        return SimpleNamespace(status=status)


def _sport(code: SportCode) -> Sport:
    return Sport(id=SportId(uuid4()), code=code, name=code.value.title())


@pytest.fixture
def cache():
    return FakePredictionCacheService()


@pytest.fixture
def sports_and_fixtures():
    football = _sport(SportCode.FOOTBALL)
    sports = FakeSportRepository(by_code={SportCode.FOOTBALL: football})
    fixture_soon = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 + timedelta(hours=6))
    fixtures = FakeFixtureRepository(by_sport={football.id: [fixture_soon]})
    return sports, fixtures, football, fixture_soon


def test_generates_a_prediction_for_every_production_market_of_an_upcoming_fixture(market_repo, cache, sports_and_fixtures):
    sports, fixtures, _football, fixture = sports_and_fixtures
    market_repo.store["football.match_winner"] = _market("football.match_winner")
    market_repo.store["football.both_teams_to_score"] = _market("football.both_teams_to_score")

    orchestrator = ScheduledPredictionGenerationOrchestrator(cache=cache, markets=market_repo, sports=sports, fixtures=fixtures)
    outcomes = asyncio.run(orchestrator.run(T0))

    called_pairs = {(m, s) for m, s, _actor in cache.calls}
    assert called_pairs == {
        ("football.match_winner", str(fixture.id)),
        ("football.both_teams_to_score", str(fixture.id)),
    }
    assert {o.status for o in outcomes} == {"published"}
    assert all(actor == "scheduled-prediction-generation" for _m, _s, actor in cache.calls)


def test_ignores_a_fixture_outside_the_lookahead_window(market_repo, cache, sports_and_fixtures):
    sports, fixtures, football, _fixture = sports_and_fixtures
    market_repo.store["football.match_winner"] = _market("football.match_winner")
    far_future = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 + timedelta(days=30))
    fixtures.by_sport[football.id].append(far_future)

    orchestrator = ScheduledPredictionGenerationOrchestrator(
        cache=cache, markets=market_repo, sports=sports, fixtures=fixtures, lookahead_hours=168,
    )
    asyncio.run(orchestrator.run(T0))

    called_subject_refs = {s for _m, s, _a in cache.calls}
    assert str(far_future.id) not in called_subject_refs


def test_ignores_a_fixture_whose_kickoff_has_already_passed(market_repo, cache, sports_and_fixtures):
    sports, fixtures, football, _fixture = sports_and_fixtures
    market_repo.store["football.match_winner"] = _market("football.match_winner")
    already_played = _Fixture(id=FixtureId(uuid4()), scheduled_at=T0 - timedelta(hours=2))
    fixtures.by_sport[football.id].append(already_played)

    orchestrator = ScheduledPredictionGenerationOrchestrator(cache=cache, markets=market_repo, sports=sports, fixtures=fixtures)
    asyncio.run(orchestrator.run(T0))

    called_subject_refs = {s for _m, s, _a in cache.calls}
    assert str(already_played.id) not in called_subject_refs


def test_ignores_a_market_not_in_production(market_repo, cache, sports_and_fixtures):
    sports, fixtures, _football, fixture = sports_and_fixtures
    market_repo.store["football.match_winner"] = _market("football.match_winner")
    market_repo.store["football.draft_market"] = _market("football.draft_market", status=MarketStatus.DRAFT)

    orchestrator = ScheduledPredictionGenerationOrchestrator(cache=cache, markets=market_repo, sports=sports, fixtures=fixtures)
    asyncio.run(orchestrator.run(T0))

    called_markets = {m for m, _s, _a in cache.calls}
    assert called_markets == {"football.match_winner"}


@pytest.mark.parametrize(
    "error",
    [
        MissingRequiredFeatureError("required feature has no verified pre-match value"),
        NoChampionModelError("market has no champion model"),
        MarketNotInProductionError("market not in production"),
        MarketNotFoundError("football.match_winner"),
    ],
)
def test_an_expected_generation_gap_is_recorded_as_skipped_not_a_failure(market_repo, cache, sports_and_fixtures, error):
    sports, fixtures, _football, fixture = sports_and_fixtures
    market_repo.store["football.match_winner"] = _market("football.match_winner")
    cache.raise_for[("football.match_winner", str(fixture.id))] = error

    orchestrator = ScheduledPredictionGenerationOrchestrator(cache=cache, markets=market_repo, sports=sports, fixtures=fixtures)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert len(outcomes) == 1
    assert outcomes[0].status == "skipped"
    assert outcomes[0].reason == str(error)


def test_one_pairs_unexpected_failure_never_blocks_the_sweep(market_repo, cache, sports_and_fixtures):
    sports, fixtures, football, fixture = sports_and_fixtures
    market_repo.store["football.match_winner"] = _market("football.match_winner")
    market_repo.store["football.both_teams_to_score"] = _market("football.both_teams_to_score")
    cache.raise_for[("football.match_winner", str(fixture.id))] = RuntimeError("unexpected boom")

    orchestrator = ScheduledPredictionGenerationOrchestrator(cache=cache, markets=market_repo, sports=sports, fixtures=fixtures)
    outcomes = asyncio.run(orchestrator.run(T0))

    by_market = {o.market_key: o for o in outcomes}
    assert by_market["football.match_winner"].status == "skipped"
    assert "unexpected boom" in by_market["football.match_winner"].reason
    assert by_market["football.both_teams_to_score"].status == "published"


def test_records_draft_status_when_the_confidence_gate_wasnt_met(market_repo, cache, sports_and_fixtures):
    sports, fixtures, _football, fixture = sports_and_fixtures
    market_repo.store["football.match_winner"] = _market("football.match_winner")
    cache.status_for[("football.match_winner", str(fixture.id))] = PredictionStatus.DRAFT

    orchestrator = ScheduledPredictionGenerationOrchestrator(cache=cache, markets=market_repo, sports=sports, fixtures=fixtures)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert outcomes[0].status == "draft"


def test_a_sport_with_no_production_markets_is_never_queried(market_repo, cache):
    """No PRODUCTION market exists for any sport — the orchestrator must not even attempt to
    resolve a sport or list its fixtures, since there's nothing it could generate."""
    sports = FakeSportRepository()
    fixtures = FakeFixtureRepository()

    orchestrator = ScheduledPredictionGenerationOrchestrator(cache=cache, markets=market_repo, sports=sports, fixtures=fixtures)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert outcomes == []
    assert cache.calls == []


def test_a_sport_the_registry_has_never_reconciled_is_skipped_not_a_failure(market_repo, cache):
    """A PRODUCTION market exists for a sport that `sports.get_by_code` can't resolve (never
    reconciled) — real gap `SyncOrchestrator._get_reconciled_sport` already guards against
    elsewhere; this orchestrator must skip it quietly rather than raising."""
    market_repo.store["basketball.moneyline"] = _market("basketball.moneyline", sport_code="basketball")
    sports = FakeSportRepository()  # basketball never registered
    fixtures = FakeFixtureRepository()

    orchestrator = ScheduledPredictionGenerationOrchestrator(cache=cache, markets=market_repo, sports=sports, fixtures=fixtures)
    outcomes = asyncio.run(orchestrator.run(T0))

    assert outcomes == []
    assert cache.calls == []
