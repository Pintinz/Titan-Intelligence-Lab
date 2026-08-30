"""Milestone 15 — Historical Feature Backfill Into Training Data.

Test matrix (1-15) for the integration added to
`scripts/backfill_both_teams_to_score_training_data.py`. Split in two:

Part A (tests 1-11) exercises the BTTS-specific reconstruction boundary directly against
`HistoricalFeatureReconstructionService`/`NewsMarketImpactEngine`, reusing the exact in-memory
fixtures and helpers `tests/unit/modules/predictions/test_historical_feature_reconstruction_service.py`
(Milestone 14) already established — these scenarios (pre-kickoff eligible, post-kickoff,
unknown availability, later transfer, current-team-id conflict, unrelated-team leakage, unresolved
membership) are already exhaustively covered at the service level by Milestones 13/14; what's new
here is confirming *this* market's own rule (`football.both_teams_to_score` -> `btts_impact`) and
side isolation, not re-deriving the underlying provenance/leakage guarantees.

Part B (tests 12-15) is genuinely new: it runs the actual modified script's `main()` against an
isolated, file-based SQLite database (never `dev.db`) built from the real production schema and
seeded via the real `FootballMarketSeeder`, proving the one thing only the script itself can prove
— that reconstructed features actually land in `Prediction.feature_snapshot` (the exact path
`DatasetBuilder` reads), that the idempotency guards hold across repeated runs, and that a fixture
with no eligible news (today's real `dev.db` state, confirmed in the Milestone 15 audit) behaves
identically to the script's pre-Milestone-15 form.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

import apps.api.composition as composition
from modules.features.domain.value_objects import EntityType
from modules.intelligence.application.news_provenance import (
    NewsAvailabilityClassification,
    classify_news_availability,
)
from modules.intelligence.domain.entities import NewsEvent, ResolvedNewsEntity
from modules.intelligence.domain.value_objects import (
    EntityResolutionStatus,
    NewsArticleId,
    NewsEventConfidenceTier,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
    SyncTrigger,
)
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemyNewsEventRepository
from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.knowledge_graph.infrastructure.persistence.repositories import SqlAlchemyKGNodeRepository
from modules.predictions.infrastructure.persistence.models import Base as PredictionsBase
from modules.features.infrastructure.persistence.models import Base as FeaturesBase
from modules.sports.domain.entities import Player, Transfer
from modules.sports.domain.value_objects import EntityId, FixtureId, PlayerId, SportId, TeamId
from modules.sports.infrastructure.persistence.database import get_database_settings
from modules.sports.infrastructure.persistence.models import Base as SportsBase
from modules.sports.infrastructure.persistence.models import FixtureModel, TeamModel
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyPlayerRepository,
    SqlAlchemyTransferRepository,
)
from tests.unit.modules.predictions.test_historical_feature_reconstruction_service import (
    AWAY_TEAM,
    HOME_TEAM,
    KICKOFF,
    T0,
    UNRELATED_TEAM,
    InMemoryKGNodeRepository,
    InMemoryNewsEventRepository,
    InMemoryPlayerRepository,
    InMemoryTransferRepository,
    _event,
    _forward_player,
    _service,
    _team_node,
    registration,
    store,
)

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "backfill_both_teams_to_score_training_data.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("_m15_backfill_btts_script_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ================================================================================================
# Part A (tests 1-11) — BTTS-specific reconstruction boundary, in-memory, reusing Milestone 14's
# established fixtures/helpers.
# ================================================================================================


async def test_01_eligible_pre_kickoff_forward_injury_produces_home_btts_impact_key(registration, store):
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    events = InMemoryNewsEventRepository()
    events.add(str(node.id), _event(str(node.id)))
    service = _service(registration, store, kg_nodes, players, transfers, events=events)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    keys = {v.feature_key.value for v in written}
    assert "news.football.home_btts_impact" in keys
    assert "news.football.away_btts_impact" not in keys  # side isolation


async def test_02_eligible_pre_kickoff_forward_injury_away_side_produces_away_key_only(registration, store):
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=AWAY_TEAM, effective_date=T0 - timedelta(days=10)))
    events = InMemoryNewsEventRepository()
    events.add(str(node.id), _event(str(node.id)))
    service = _service(registration, store, kg_nodes, players, transfers, events=events)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    keys = {v.feature_key.value for v in written}
    assert "news.football.away_btts_impact" in keys
    assert "news.football.home_btts_impact" not in keys


async def test_03_post_kickoff_event_excluded_from_btts_reconstruction(registration, store):
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    events = InMemoryNewsEventRepository()
    events.add(str(node.id), _event(str(node.id), information_available_at=KICKOFF + timedelta(hours=1)))
    service = _service(registration, store, kg_nodes, players, transfers, events=events)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    assert written == []


async def test_04_unknown_availability_time_excluded_from_btts_reconstruction(registration, store):
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    events = InMemoryNewsEventRepository()
    events.add(str(node.id), _event(str(node.id), availability="UNKNOWN_AVAILABILITY_TIME"))
    service = _service(registration, store, kg_nodes, players, transfers, events=events)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    assert written == []


def test_05_backfill_trigger_never_classifies_verified_pre_match():
    result = classify_news_availability(
        trigger=SyncTrigger.BACKFILL, sync_succeeded=True, validated=True, sync_time=T0, published_at=T0 - timedelta(days=1),
    )
    assert result.classification is not NewsAvailabilityClassification.VERIFIED_PRE_MATCH


def test_06_admin_manual_trigger_never_classifies_verified_pre_match():
    result = classify_news_availability(
        trigger=SyncTrigger.ADMIN_MANUAL, sync_succeeded=True, validated=True, sync_time=T0, published_at=T0 - timedelta(days=1),
    )
    assert result.classification is not NewsAvailabilityClassification.VERIFIED_PRE_MATCH


async def test_07_later_transfer_does_not_retroactively_change_kickoff_time_membership(registration, store):
    """A player transferred away from HOME_TEAM *after* the target fixture's kickoff must still be
    resolved to HOME_TEAM as of that kickoff — the chronological Transfer chain, not "the most
    recent transfer on file", governs historical membership."""
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    third_team = TeamId(uuid4())
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=30)))
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=HOME_TEAM, to_team_id=third_team, effective_date=KICKOFF + timedelta(days=10)))
    events = InMemoryNewsEventRepository()
    events.add(str(node.id), _event(str(node.id)))
    service = _service(registration, store, kg_nodes, players, transfers, events=events)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    keys = {v.feature_key.value for v in written}
    assert "news.football.home_btts_impact" in keys


async def test_08_stale_current_team_id_field_is_never_consulted(registration, store):
    """The player's own (deliberately wrong) `team_id` field disagrees with the Transfer chain —
    reconstruction must follow the Transfer chain only, never `Player.team_id`."""
    player, node = _forward_player()
    player.team_id = AWAY_TEAM  # deliberately stale/wrong current-state field
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    kg_nodes.add(node)
    players.by_id[player.id] = player
    transfers.add(Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=HOME_TEAM, effective_date=T0 - timedelta(days=10)))
    events = InMemoryNewsEventRepository()
    events.add(str(node.id), _event(str(node.id)))
    service = _service(registration, store, kg_nodes, players, transfers, events=events)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    keys = {v.feature_key.value for v in written}
    assert "news.football.home_btts_impact" in keys  # resolved via Transfer chain, not the stale field


async def test_09_unrelated_team_news_does_not_leak_into_fixture(registration, store):
    node = _team_node(UNRELATED_TEAM)
    kg_nodes = InMemoryKGNodeRepository()
    kg_nodes.add(node)
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()
    events = InMemoryNewsEventRepository()
    events.add(str(node.id), _event(str(node.id), node_type="team"))
    service = _service(registration, store, kg_nodes, players, transfers, events=events)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    assert written == []


async def test_10_unresolved_membership_excludes_player_from_reconstruction(registration, store):
    player, node = _forward_player()
    kg_nodes = InMemoryKGNodeRepository()
    players = InMemoryPlayerRepository()
    transfers = InMemoryTransferRepository()  # no transfer history at all -> HISTORICALLY_UNRESOLVED
    kg_nodes.add(node)
    players.by_id[player.id] = player
    events = InMemoryNewsEventRepository()
    events.add(str(node.id), _event(str(node.id)))
    service = _service(registration, store, kg_nodes, players, transfers, events=events)
    await service.news_market_impact.ensure_registered(T0)

    written = await service.publish_for_fixture(FixtureId(uuid4()), HOME_TEAM, AWAY_TEAM, KICKOFF)

    assert written == []


def test_11_script_wires_news_keys_as_optional_never_required():
    """Structural: the two BTTS news feature keys the script reads (for its own reconstruction-
    trigger check, not the required/optional feature snapshot — see forensic audit finding #2,
    2026-08-30) must be exactly the ones `NewsMarketImpactEngine` actually writes for this
    market's `btts_impact` dimension.

    Required/optional now comes from the live `FeatureMarketMappingService` mapping rather than a
    static module constant the script used to hardcode (that duplication — a spec change in
    market_seeding.py never reaching this script — is exactly what finding #2 fixed), so the
    "these two keys must be optional, never required" invariant this test used to check directly
    against the script now lives in market_seeding.py's own spec instead — see
    test_football_market_seeding.py for that coverage."""
    script = _load_script()
    assert script.NEWS_BTTS_IMPACT_FEATURES == ("news.football.home_btts_impact", "news.football.away_btts_impact")

    from modules.predictions.football.market_seeding import MARKETS

    btts_spec = next(spec for spec in MARKETS if spec["market_key"] == "football.both_teams_to_score")
    market_optional_features = set(btts_spec.get("optional_features", ()))
    # Mirrors `FootballMarketSeeder._seed_market`'s own is_required computation: a feature_key
    # present in `optional_features` is never actually required, regardless of also appearing in
    # the raw `required_features` tuple (that tuple just lists every feature_key to map at all).
    actually_required = {fk for fk in btts_spec["required_features"] if fk not in market_optional_features}
    assert set(script.NEWS_BTTS_IMPACT_FEATURES).issubset(market_optional_features)
    assert not set(script.NEWS_BTTS_IMPACT_FEATURES) & actually_required


# ================================================================================================
# Part B (tests 12-15) — full script execution against an isolated, file-based SQLite database.
# ================================================================================================

_ALL_TEST_SCHEMAS = [SportsBase, PredictionsBase, IntelligenceBase, FeaturesBase, KnowledgeGraphBase]


@pytest.fixture
async def full_schema_db(tmp_path, monkeypatch):
    db_path = tmp_path / "m15_test.db"
    monkeypatch.setenv("TITANIQ_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    # Unreachable on purpose: FeatureStoreService degrades gracefully on RedisError (writes stay
    # durable via the offline store, reads fall back to it) — only the offline table matters here.
    monkeypatch.setenv("TITANIQ_REDIS_URL", "redis://127.0.0.1:1/0")
    get_database_settings.cache_clear()
    composition.get_engine.cache_clear()
    composition.get_redis_client.cache_clear()

    engine = composition.get_engine()
    async with engine.begin() as conn:
        for base in _ALL_TEST_SCHEMAS:
            await conn.run_sync(base.metadata.create_all)

    yield engine

    await engine.dispose()
    composition.get_engine.cache_clear()
    composition.get_redis_client.cache_clear()
    get_database_settings.cache_clear()


def _new_fixture_row(home_team_id: uuid.UUID, away_team_id: uuid.UUID, *, home_score: int, away_score: int, scheduled_at: datetime) -> FixtureModel:
    return FixtureModel(
        id=uuid4(), season_id=uuid4(), home_team_id=home_team_id, away_team_id=away_team_id,
        scheduled_at=scheduled_at, status="completed", home_score=home_score, away_score=away_score,
    )


async def _seed_team(session, team_id: uuid.UUID, short_name: str) -> None:
    session.add(TeamModel(id=team_id, sport_id=uuid4(), name=short_name, short_name=short_name))


async def _seed_forward_with_eligible_injury(session, kg_nodes_repo, players_repo, transfers_repo, events_repo, *, team_id: uuid.UUID, kickoff: datetime) -> None:
    player = Player(id=PlayerId(uuid4()), sport_id=SportId(uuid4()), name="Test Striker", date_of_birth=None, position="attacker")
    node = KGNode(id=KGNodeId(uuid4()), node_type=NodeType.PLAYER, entity_ref=str(player.id.value))
    await kg_nodes_repo.upsert(node)
    await players_repo.upsert(player)
    await transfers_repo.upsert(
        Transfer(id=EntityId(uuid4()), player_id=player.id, from_team_id=None, to_team_id=TeamId(team_id), effective_date=kickoff - timedelta(days=200))
    )
    await events_repo.record(
        NewsEvent(
            id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary="test forward injury", confidence=0.8,
            source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()),
            occurred_at=kickoff - timedelta(days=1), detected_at=kickoff - timedelta(days=1),
            affected_entity_refs=(str(node.id),),
            resolved_entities=(ResolvedNewsEntity(ref=str(node.id), node_type="player", status=EntityResolutionStatus.RESOLVED),),
            confidence_tier=NewsEventConfidenceTier.CONFIRMED, availability_classification="VERIFIED_PRE_MATCH",
            information_available_at=kickoff - timedelta(days=1),
        )
    )


async def _seed_required_features(feature_store, dashed_fixture_id: str, as_of: datetime, *, include_overround: bool = True) -> None:
    if include_overround:
        await feature_store.write("football.market.overround", EntityType.FIXTURE, dashed_fixture_id, 1.05, as_of)
    await feature_store.write("football.fixture.form_shots_on_target_diff_last5", EntityType.FIXTURE, dashed_fixture_id, 0.5, as_of)


async def _feature_row_count(session, feature_key: str, dashed_fixture_id: str) -> int:
    rows = (
        await session.execute(
            text("SELECT COUNT(*) FROM feature_values_offline WHERE feature_key = :fk AND entity_id = :eid"),
            {"fk": feature_key, "eid": dashed_fixture_id},
        )
    ).scalar_one()
    return rows


async def test_12_snapshot_path_contains_news_features_when_eligible(full_schema_db):
    kickoff = datetime(2024, 6, 1, tzinfo=timezone.utc)
    session_factory = async_sessionmaker(full_schema_db, expire_on_commit=False)

    async with session_factory() as session:
        await composition.build_football_market_seeder(session).seed(kickoff - timedelta(days=1000))
        home_id, away_id = uuid4(), uuid4()
        await _seed_team(session, home_id, "HOME")
        await _seed_team(session, away_id, "AWAY")
        fixture = _new_fixture_row(home_id, away_id, home_score=2, away_score=1, scheduled_at=kickoff)
        session.add(fixture)
        await session.flush()

        kg_nodes_repo = SqlAlchemyKGNodeRepository(session=session)
        players_repo = SqlAlchemyPlayerRepository(session=session)
        transfers_repo = SqlAlchemyTransferRepository(session=session)
        events_repo = SqlAlchemyNewsEventRepository(session=session)
        await _seed_forward_with_eligible_injury(session, kg_nodes_repo, players_repo, transfers_repo, events_repo, team_id=home_id, kickoff=kickoff)

        feature_store = composition.build_feature_store_service(session)
        dashed = str(fixture.id)
        await _seed_required_features(feature_store, dashed, kickoff)
        await session.commit()

    script = _load_script()
    await script.main()

    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT feature_snapshot FROM predictions WHERE subject_ref = :ref"), {"ref": dashed},
            )
        ).fetchone()
        assert row is not None
        snapshot = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert "news.football.home_btts_impact" in snapshot
        assert "news.football.away_btts_impact" not in snapshot  # only the home side had eligible news


async def test_13_idempotency_across_two_full_runs_with_existing_prediction(full_schema_db):
    kickoff = datetime(2024, 6, 2, tzinfo=timezone.utc)
    session_factory = async_sessionmaker(full_schema_db, expire_on_commit=False)

    async with session_factory() as session:
        await composition.build_football_market_seeder(session).seed(kickoff - timedelta(days=1000))
        home_id, away_id = uuid4(), uuid4()
        await _seed_team(session, home_id, "HOME")
        await _seed_team(session, away_id, "AWAY")
        fixture = _new_fixture_row(home_id, away_id, home_score=1, away_score=1, scheduled_at=kickoff)
        session.add(fixture)
        await session.flush()

        kg_nodes_repo = SqlAlchemyKGNodeRepository(session=session)
        players_repo = SqlAlchemyPlayerRepository(session=session)
        transfers_repo = SqlAlchemyTransferRepository(session=session)
        events_repo = SqlAlchemyNewsEventRepository(session=session)
        await _seed_forward_with_eligible_injury(session, kg_nodes_repo, players_repo, transfers_repo, events_repo, team_id=home_id, kickoff=kickoff)

        feature_store = composition.build_feature_store_service(session)
        dashed = str(fixture.id)
        await _seed_required_features(feature_store, dashed, kickoff)
        await session.commit()

    script = _load_script()
    await script.main()
    await script.main()  # second run: predictions.list_by_subject skip-check should short-circuit before reconstruction

    async with session_factory() as session:
        prediction_count = (
            await session.execute(text("SELECT COUNT(*) FROM predictions WHERE subject_ref = :ref"), {"ref": dashed})
        ).scalar_one()
        assert prediction_count == 1  # no duplicate Prediction rows

        offline_count = await _feature_row_count(session, "news.football.home_btts_impact", dashed)
        assert offline_count == 1  # no duplicate offline feature rows


async def test_14_idempotency_guard_prevents_duplicate_reconstruction_when_prediction_never_created(full_schema_db):
    """A fixture reconstructed on a prior run but skipped for an unrelated reason (missing
    `football.market.overround`) must never be reconstructed a second time — the standalone guard
    added in Milestone 15 (independent of the `list_by_subject` skip-check, since no Prediction
    was ever created for this fixture)."""
    kickoff = datetime(2024, 6, 3, tzinfo=timezone.utc)
    session_factory = async_sessionmaker(full_schema_db, expire_on_commit=False)

    async with session_factory() as session:
        await composition.build_football_market_seeder(session).seed(kickoff - timedelta(days=1000))
        home_id, away_id = uuid4(), uuid4()
        await _seed_team(session, home_id, "HOME")
        await _seed_team(session, away_id, "AWAY")
        fixture = _new_fixture_row(home_id, away_id, home_score=0, away_score=0, scheduled_at=kickoff)
        session.add(fixture)
        await session.flush()

        kg_nodes_repo = SqlAlchemyKGNodeRepository(session=session)
        players_repo = SqlAlchemyPlayerRepository(session=session)
        transfers_repo = SqlAlchemyTransferRepository(session=session)
        events_repo = SqlAlchemyNewsEventRepository(session=session)
        await _seed_forward_with_eligible_injury(session, kg_nodes_repo, players_repo, transfers_repo, events_repo, team_id=home_id, kickoff=kickoff)

        feature_store = composition.build_feature_store_service(session)
        dashed = str(fixture.id)
        await _seed_required_features(feature_store, dashed, kickoff, include_overround=False)  # deliberately missing
        await session.commit()

    script = _load_script()
    await script.main()
    await script.main()

    async with session_factory() as session:
        prediction_count = (
            await session.execute(text("SELECT COUNT(*) FROM predictions WHERE subject_ref = :ref"), {"ref": dashed})
        ).scalar_one()
        assert prediction_count == 0  # still missing football.market.overround, so still skipped both runs

        offline_count = await _feature_row_count(session, "news.football.home_btts_impact", dashed)
        assert offline_count == 1  # reconstructed once on the first run, never re-appended on the second


async def test_15_regression_with_no_eligible_news_matches_pre_milestone15_behavior(full_schema_db):
    kickoff = datetime(2024, 6, 4, tzinfo=timezone.utc)
    session_factory = async_sessionmaker(full_schema_db, expire_on_commit=False)

    async with session_factory() as session:
        await composition.build_football_market_seeder(session).seed(kickoff - timedelta(days=1000))
        home_id, away_id = uuid4(), uuid4()
        await _seed_team(session, home_id, "HOME")
        await _seed_team(session, away_id, "AWAY")
        fixture = _new_fixture_row(home_id, away_id, home_score=3, away_score=0, scheduled_at=kickoff)
        session.add(fixture)
        await session.flush()

        feature_store = composition.build_feature_store_service(session)
        dashed = str(fixture.id)
        await _seed_required_features(feature_store, dashed, kickoff)  # no news events seeded at all
        await session.commit()

    script = _load_script()
    await script.main()

    async with session_factory() as session:
        row = (
            await session.execute(text("SELECT feature_snapshot FROM predictions WHERE subject_ref = :ref"), {"ref": dashed})
        ).fetchone()
        assert row is not None
        snapshot = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert "football.market.overround" in snapshot  # required features still populate exactly as before
        assert "news.football.home_btts_impact" not in snapshot  # zero eligible news -> no news keys, same as pre-M15
        assert "news.football.away_btts_impact" not in snapshot


# ================================================================================================
# Part C (tests 16-17) — forensic audit Critical Fix #1 regression: `_latest_feature_value` (which
# read "latest ever written" with no cutoff) was renamed to `_feature_value_as_of` and given an
# `as_of <= cutoff` bound. These prove the fixed script can no longer see a feature value written
# after the fixture's own kickoff — the exact leakage the audit found live in dev.db (a 2023
# fixture's features recomputed, and changing, as late as 2026).
# ================================================================================================


async def test_16_feature_written_only_after_kickoff_is_treated_as_missing_not_leaked(full_schema_db):
    """A required feature that exists ONLY as a post-kickoff row (simulating a later, out-of-band
    recompute of an already-completed historical fixture — the real bug this fix closes) must be
    invisible to the backfill, not silently used as 'the latest value on file'."""
    kickoff = datetime(2024, 6, 5, tzinfo=timezone.utc)
    session_factory = async_sessionmaker(full_schema_db, expire_on_commit=False)

    async with session_factory() as session:
        await composition.build_football_market_seeder(session).seed(kickoff - timedelta(days=1000))
        home_id, away_id = uuid4(), uuid4()
        await _seed_team(session, home_id, "HOME")
        await _seed_team(session, away_id, "AWAY")
        fixture = _new_fixture_row(home_id, away_id, home_score=1, away_score=0, scheduled_at=kickoff)
        session.add(fixture)
        await session.flush()

        feature_store = composition.build_feature_store_service(session)
        dashed = str(fixture.id)
        # Deliberately contaminated: the required feature is written well AFTER kickoff, as if a
        # live re-sync recomputed this already-completed fixture without a fixture-specific
        # cutoff — no pre-kickoff row exists for it at all.
        await feature_store.write(
            "football.fixture.form_shots_on_target_diff_last5", EntityType.FIXTURE, dashed, 0.9,
            kickoff + timedelta(days=500),
        )
        await feature_store.write("football.market.overround", EntityType.FIXTURE, dashed, 1.05, kickoff)
        await session.commit()

    script = _load_script()
    await script.main()

    async with session_factory() as session:
        row = (
            await session.execute(text("SELECT feature_snapshot FROM predictions WHERE subject_ref = :ref"), {"ref": dashed})
        ).fetchone()
        # The fixture is skipped entirely (missing_required), never a Prediction built from the
        # leaked value — matching every other "genuinely missing" required feature in this suite.
        assert row is None


async def test_17_pre_and_post_kickoff_values_coexist_script_reads_the_pre_kickoff_one(full_schema_db):
    """When a feature has BOTH a legitimate pre-kickoff value and a later, out-of-band
    post-kickoff recompute, the script must resolve the pre-kickoff one — proving this is a real
    `as_of <= cutoff` bound, not merely "skip if the latest row happens to be post-kickoff"."""
    kickoff = datetime(2024, 6, 6, tzinfo=timezone.utc)
    session_factory = async_sessionmaker(full_schema_db, expire_on_commit=False)

    async with session_factory() as session:
        await composition.build_football_market_seeder(session).seed(kickoff - timedelta(days=1000))
        home_id, away_id = uuid4(), uuid4()
        await _seed_team(session, home_id, "HOME")
        await _seed_team(session, away_id, "AWAY")
        fixture = _new_fixture_row(home_id, away_id, home_score=2, away_score=2, scheduled_at=kickoff)
        session.add(fixture)
        await session.flush()

        feature_store = composition.build_feature_store_service(session)
        dashed = str(fixture.id)
        # The real, legitimate pre-kickoff value.
        await feature_store.write(
            "football.fixture.form_shots_on_target_diff_last5", EntityType.FIXTURE, dashed, 0.25,
            kickoff - timedelta(days=3),
        )
        # A later out-of-band recompute that must NOT shadow the value above.
        await feature_store.write(
            "football.fixture.form_shots_on_target_diff_last5", EntityType.FIXTURE, dashed, 0.99,
            kickoff + timedelta(days=200),
        )
        await feature_store.write("football.market.overround", EntityType.FIXTURE, dashed, 1.05, kickoff)
        await session.commit()

    script = _load_script()
    await script.main()

    async with session_factory() as session:
        row = (
            await session.execute(text("SELECT feature_snapshot FROM predictions WHERE subject_ref = :ref"), {"ref": dashed})
        ).fetchone()
        assert row is not None
        snapshot = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert snapshot["football.fixture.form_shots_on_target_diff_last5"] == 0.25
