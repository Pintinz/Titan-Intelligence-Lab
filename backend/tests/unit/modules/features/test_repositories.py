from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.features.domain.entities import (
    FeatureDefinition,
    FeatureDefinitionVersionSnapshot,
    FeatureDriftReport,
    FeatureLineageEdge,
    FeatureValue,
)
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
    FeatureValueId,
    QualityFlag,
)
from modules.features.infrastructure.persistence.repositories import (
    SqlAlchemyFeatureDefinitionRepository,
    SqlAlchemyFeatureDriftReportRepository,
    SqlAlchemyFeatureLineageRepository,
    SqlAlchemyFeatureValueRepository,
    SqlAlchemyFeatureVersionRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _definition(key="football.team.form_index_last5", **overrides) -> FeatureDefinition:
    kwargs = dict(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey(key),
        name="Form index",
        description="d",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="f(x)",
        data_type=FeatureDataType.FLOAT,
        owner="data-team",
        entity_type=EntityType.TEAM,
        expected_range=(0.0, 1.0),
        dependencies=(FeatureKey("football.team.base_stat"),),
    )
    kwargs.update(overrides)
    return FeatureDefinition(**kwargs)


@pytest.mark.asyncio
async def test_feature_definition_round_trip_preserves_all_fields(sqlite_session):
    repo = SqlAlchemyFeatureDefinitionRepository(session=sqlite_session)
    definition = _definition(status=FeatureStatus.ACTIVE, leakage_reviewed=True, reviewed_by="alice", reviewed_at=T0)

    await repo.upsert(definition)
    await sqlite_session.commit()

    fetched = await repo.get(FeatureKey("football.team.form_index_last5"))

    assert fetched is not None
    assert fetched.status is FeatureStatus.ACTIVE
    assert fetched.leakage_reviewed is True
    assert fetched.reviewed_by == "alice"
    assert fetched.expected_range == (0.0, 1.0)
    assert fetched.dependencies == (FeatureKey("football.team.base_stat"),)


@pytest.mark.asyncio
async def test_feature_definition_list_by_sport(sqlite_session):
    repo = SqlAlchemyFeatureDefinitionRepository(session=sqlite_session)
    await repo.upsert(_definition("football.a", dependencies=()))
    await repo.upsert(_definition("basketball.b", sport_code="basketball", dependencies=()))
    await sqlite_session.commit()

    football_features = await repo.list_by_sport("football")

    assert len(football_features) == 1
    assert football_features[0].feature_key.value == "football.a"


@pytest.mark.asyncio
async def test_feature_version_history_round_trip(sqlite_session):
    definition_repo = SqlAlchemyFeatureDefinitionRepository(session=sqlite_session)
    version_repo = SqlAlchemyFeatureVersionRepository(session=sqlite_session)
    definition = _definition(dependencies=())
    await definition_repo.upsert(definition)

    await version_repo.record(
        FeatureDefinitionVersionSnapshot(
            feature_key=definition.feature_key, version=1, snapshot=definition, recorded_at=T0
        )
    )
    await sqlite_session.commit()

    history = await version_repo.list_by_feature(definition.feature_key)

    assert len(history) == 1
    assert history[0].snapshot.feature_key == definition.feature_key
    assert history[0].snapshot.formula == definition.formula


@pytest.mark.asyncio
async def test_feature_value_get_latest_returns_most_recent(sqlite_session):
    definition_repo = SqlAlchemyFeatureDefinitionRepository(session=sqlite_session)
    value_repo = SqlAlchemyFeatureValueRepository(session=sqlite_session)
    definition = _definition(dependencies=())
    await definition_repo.upsert(definition)

    older = FeatureValue(
        id=FeatureValueId(uuid4()), feature_key=definition.feature_key, entity_type=EntityType.TEAM,
        entity_id="team-1", as_of=T0, value=0.4,
    )
    newer = FeatureValue(
        id=FeatureValueId(uuid4()), feature_key=definition.feature_key, entity_type=EntityType.TEAM,
        entity_id="team-1", as_of=datetime(2026, 7, 26, tzinfo=timezone.utc), value=0.6,
    )
    await value_repo.record(older)
    await value_repo.record(newer)
    await sqlite_session.commit()

    latest = await value_repo.get_latest(definition.feature_key, EntityType.TEAM, "team-1")
    history = await value_repo.list_history(definition.feature_key, EntityType.TEAM, "team-1")

    assert latest.value == pytest.approx(0.6)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_feature_value_get_as_of_returns_value_true_at_cutoff_not_the_latest(sqlite_session):
    """Milestone 4 point-in-time retrieval, tested against the real SQLAlchemy-backed repository
    (not the in-memory test double in conftest.py) — the mapper/SQL `WHERE as_of <= cutoff ORDER
    BY as_of DESC LIMIT 1` behavior is exactly the kind of thing that can silently diverge from a
    hand-written fake, so it needs its own real-database assertion, not just service-layer
    coverage against the fake."""
    definition_repo = SqlAlchemyFeatureDefinitionRepository(session=sqlite_session)
    value_repo = SqlAlchemyFeatureValueRepository(session=sqlite_session)
    definition = _definition(dependencies=())
    await definition_repo.upsert(definition)

    early = FeatureValue(
        id=FeatureValueId(uuid4()), feature_key=definition.feature_key, entity_type=EntityType.TEAM,
        entity_id="team-1", as_of=T0, value=0.4,
    )
    mid = FeatureValue(
        id=FeatureValueId(uuid4()), feature_key=definition.feature_key, entity_type=EntityType.TEAM,
        entity_id="team-1", as_of=datetime(2026, 7, 26, tzinfo=timezone.utc), value=0.5,
    )
    late = FeatureValue(
        id=FeatureValueId(uuid4()), feature_key=definition.feature_key, entity_type=EntityType.TEAM,
        entity_id="team-1", as_of=datetime(2026, 7, 28, tzinfo=timezone.utc), value=0.9,
    )
    await value_repo.record(early)
    await value_repo.record(late)
    await value_repo.record(mid)  # inserted last but chronologically the middle value
    await sqlite_session.commit()

    as_of_cutoff = datetime(2026, 7, 27, tzinfo=timezone.utc)
    result = await value_repo.get_as_of(definition.feature_key, EntityType.TEAM, "team-1", as_of_cutoff)

    assert result is not None
    assert result.value == pytest.approx(0.5)  # "mid", not "late" (future) or "early" (stale)


@pytest.mark.asyncio
async def test_feature_value_get_as_of_returns_none_before_any_value_existed(sqlite_session):
    definition_repo = SqlAlchemyFeatureDefinitionRepository(session=sqlite_session)
    value_repo = SqlAlchemyFeatureValueRepository(session=sqlite_session)
    definition = _definition(dependencies=())
    await definition_repo.upsert(definition)
    await value_repo.record(
        FeatureValue(
            id=FeatureValueId(uuid4()), feature_key=definition.feature_key, entity_type=EntityType.TEAM,
            entity_id="team-1", as_of=T0, value=0.4,
        )
    )
    await sqlite_session.commit()

    result = await value_repo.get_as_of(
        definition.feature_key, EntityType.TEAM, "team-1", T0 - timedelta(days=1)
    )

    assert result is None


@pytest.mark.asyncio
async def test_feature_value_preserves_type_and_quality_flags(sqlite_session):
    definition_repo = SqlAlchemyFeatureDefinitionRepository(session=sqlite_session)
    value_repo = SqlAlchemyFeatureValueRepository(session=sqlite_session)
    definition = _definition(dependencies=(), data_type=FeatureDataType.INT)
    await definition_repo.upsert(definition)

    await value_repo.record(
        FeatureValue(
            id=FeatureValueId(uuid4()), feature_key=definition.feature_key, entity_type=EntityType.PLAYER,
            entity_id="player-1", as_of=T0, value=17, quality_flags=(QualityFlag.OUT_OF_RANGE,),
        )
    )
    await sqlite_session.commit()

    fetched = await value_repo.get_latest(definition.feature_key, EntityType.PLAYER, "player-1")

    assert fetched.value == 17
    assert isinstance(fetched.value, int)
    assert fetched.quality_flags == (QualityFlag.OUT_OF_RANGE,)


@pytest.mark.asyncio
async def test_feature_lineage_repository_round_trip(sqlite_session):
    repo = SqlAlchemyFeatureLineageRepository(session=sqlite_session)

    await repo.add_edge(FeatureLineageEdge(feature_key=FeatureKey("a"), depends_on_feature_key=FeatureKey("b")))
    await repo.add_edge(FeatureLineageEdge(feature_key=FeatureKey("c"), depends_on_feature_key=FeatureKey("b")))
    await sqlite_session.commit()

    deps_of_a = await repo.list_dependencies(FeatureKey("a"))
    dependents_of_b = await repo.list_dependents(FeatureKey("b"))

    assert deps_of_a == [FeatureKey("b")]
    assert set(dependents_of_b) == {FeatureKey("a"), FeatureKey("c")}


@pytest.mark.asyncio
async def test_feature_lineage_add_edge_is_idempotent(sqlite_session):
    repo = SqlAlchemyFeatureLineageRepository(session=sqlite_session)
    edge = FeatureLineageEdge(feature_key=FeatureKey("a"), depends_on_feature_key=FeatureKey("b"))

    await repo.add_edge(edge)
    await repo.add_edge(edge)
    await sqlite_session.commit()

    deps = await repo.list_dependencies(FeatureKey("a"))
    assert deps == [FeatureKey("b")]


@pytest.mark.asyncio
async def test_feature_drift_report_round_trip(sqlite_session):
    repo = SqlAlchemyFeatureDriftReportRepository(session=sqlite_session)

    await repo.record(
        FeatureDriftReport(
            feature_key=FeatureKey("football.team.form_index_last5"), window="7d", drift_score=0.12,
            method="population_stability_index", detected_at=T0,
        )
    )
    await sqlite_session.commit()

    reports = await repo.list_by_feature(FeatureKey("football.team.form_index_last5"))

    assert len(reports) == 1
    assert reports[0].drift_score == pytest.approx(0.12)
