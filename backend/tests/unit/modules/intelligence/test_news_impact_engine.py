from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.intelligence.application.news_impact_engine import NewsImpactEngine
from modules.intelligence.domain.entities import NewsEvent, SentimentResult
from modules.intelligence.domain.value_objects import (
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
    SentimentLabel,
    SentimentResultId,
)
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyImpactScoreRepository,
    SqlAlchemySentimentResultRepository,
)
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def combined_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"knowledge_graph": None, "intelligence": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(KnowledgeGraphBase.metadata.create_all)
        await conn.run_sync(IntelligenceBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _event(**overrides) -> NewsEvent:
    defaults = dict(
        id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary="Player suffers minor knock in training.",
        confidence=0.7, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()),
        occurred_at=T0, detected_at=T0, affected_entity_refs=(),
    )
    defaults.update(overrides)
    return NewsEvent(**defaults)


def _engine(session, kg_nodes=None):
    return NewsImpactEngine(
        impact_scores=SqlAlchemyImpactScoreRepository(session=session),
        sentiment_results=SqlAlchemySentimentResultRepository(session=session),
        kg_nodes=kg_nodes,
    )


async def test_injury_severity_scores_severe_terms_high(combined_session):
    engine = _engine(combined_session)
    event = _event(summary="Player suffers ACL rupture, requires surgery.")

    assert engine._injury_severity(event) == 0.9


async def test_injury_severity_scores_minor_terms_low(combined_session):
    engine = _engine(combined_session)
    event = _event(summary="Player is a minor doubt with a knock.")

    assert engine._injury_severity(event) == 0.3


async def test_injury_severity_zero_for_non_injury_event(combined_session):
    engine = _engine(combined_session)
    event = _event(event_type=NewsEventType.TRANSFER, summary="Club confirms new signing.")

    assert engine._injury_severity(event) == 0.0


async def test_injury_severity_defaults_to_moderate_without_severity_keywords(combined_session):
    engine = _engine(combined_session)
    event = _event(summary="Player was substituted after picking up an issue.")

    assert engine._injury_severity(event) == 0.5


async def test_timing_normalizes_naive_occurred_at(combined_session):
    engine = _engine(combined_session)
    event = _event(occurred_at=T0.replace(tzinfo=None))

    assert engine._timing(event, T0 + timedelta(hours=2)) == 1.0


async def test_categorize_affected_skips_non_uuid_and_unresolvable_refs(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    engine = _engine(combined_session, kg_nodes=nodes)
    event = _event(affected_entity_refs=("not-a-uuid", str(uuid4())))

    teams, players, competitions = await engine._categorize_affected(event)

    assert teams == () and players == () and competitions == ()


async def test_categorize_affected_includes_competition_nodes(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    competition = await population.upsert_node(NodeType.COMPETITION, "comp-1", now=T0)
    await combined_session.commit()

    engine = _engine(combined_session, kg_nodes=nodes)
    event = _event(affected_entity_refs=(str(competition.id),))

    teams, players, competitions = await engine._categorize_affected(event)

    assert competitions == (str(competition.id),)


async def test_transfer_importance_scales_with_affected_entity_count(combined_session):
    engine = _engine(combined_session)
    small_deal = _event(event_type=NewsEventType.TRANSFER, affected_entity_refs=("p1",))
    big_deal = _event(event_type=NewsEventType.TRANSFER, affected_entity_refs=("p1", "p2", "p3", "p4", "p5"))

    assert engine._transfer_importance(small_deal) < engine._transfer_importance(big_deal)
    assert engine._transfer_importance(big_deal) == 1.0


async def test_manager_influence_only_for_manager_change_events(combined_session):
    engine = _engine(combined_session)

    manager_event = _event(event_type=NewsEventType.MANAGER_CHANGE)
    other_event = _event(event_type=NewsEventType.INJURY)

    factors_manager = await engine.score(manager_event, T0)
    factors_other = await engine.score(other_event, T0)
    await combined_session.commit()

    assert factors_manager.factors["manager_influence"] == 0.8
    assert factors_other.factors["manager_influence"] == 0.0


async def test_player_importance_reflects_resolved_ref_ratio(combined_session):
    engine = _engine(combined_session)
    resolved_ref = str(uuid4())
    event = _event(affected_entity_refs=(resolved_ref, "raw_mention_text"))

    assert engine._player_importance(event) == 0.5


async def test_player_importance_zero_with_no_affected_entities(combined_session):
    engine = _engine(combined_session)
    event = _event(affected_entity_refs=())

    assert engine._player_importance(event) == 0.0


async def test_timing_is_full_for_recent_event(combined_session):
    engine = _engine(combined_session)
    event = _event(occurred_at=T0)

    assert engine._timing(event, T0 + timedelta(hours=2)) == 1.0


async def test_timing_decays_for_older_event(combined_session):
    engine = _engine(combined_session)
    event = _event(occurred_at=T0)

    recent_score = engine._timing(event, T0 + timedelta(hours=2))
    old_score = engine._timing(event, T0 + timedelta(days=5))

    assert old_score < recent_score
    assert old_score >= 0.1  # floored


async def test_historical_impact_defaults_when_no_prior_scores(combined_session):
    engine = _engine(combined_session)

    assert await engine._historical_impact() == 0.5


async def test_historical_impact_averages_recent_scores(combined_session):
    engine = _engine(combined_session)
    for score_value in (0.2, 0.8):
        await engine.score(_event(affected_entity_refs=(), event_type=NewsEventType.TRAINING_UPDATE), T0)
    await combined_session.commit()

    baseline = await engine._historical_impact()

    assert 0.0 <= baseline <= 1.0


async def test_community_momentum_uses_prior_sentiment_reading(combined_session):
    sentiment_repo = SqlAlchemySentimentResultRepository(session=combined_session)
    await sentiment_repo.record(
        SentimentResult(
            id=SentimentResultId(uuid4()), target_entity_ref="team-1", target_entity_type="team",
            label=SentimentLabel.NEGATIVE, momentum=-1.5, confidence=0.8, source_ref="article-1", computed_at=T0,
        )
    )
    await combined_session.commit()
    engine = _engine(combined_session)
    event = _event(affected_entity_refs=("team-1",))

    momentum_factor = await engine._community_momentum(event)

    assert momentum_factor == 0.75  # abs(-1.5) / 2.0


async def test_community_momentum_zero_with_no_readings(combined_session):
    engine = _engine(combined_session)
    event = _event(affected_entity_refs=("team-1",))

    assert await engine._community_momentum(event) == 0.0


async def test_categorize_affected_returns_empty_without_kg_nodes(combined_session):
    engine = _engine(combined_session, kg_nodes=None)
    event = _event(affected_entity_refs=(str(uuid4()),))

    teams, players, competitions = await engine._categorize_affected(event)

    assert teams == () and players == () and competitions == ()


async def test_categorize_affected_splits_by_node_type(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0)
    player = await population.upsert_node(NodeType.PLAYER, "player-1", now=T0)
    await combined_session.commit()

    engine = _engine(combined_session, kg_nodes=nodes)
    event = _event(affected_entity_refs=(str(team.id), str(player.id)))

    teams, players, competitions = await engine._categorize_affected(event)

    assert teams == (str(team.id),)
    assert players == (str(player.id),)
    assert competitions == ()


async def test_score_produces_composite_impact_score_within_bounds(combined_session):
    engine = _engine(combined_session)
    event = _event(event_type=NewsEventType.MANAGER_CHANGE, summary="Manager sacked after poor run.")

    result = await engine.score(event, T0)
    await combined_session.commit()

    assert 0.0 <= result.impact_score <= 1.0
    assert result.confidence == event.confidence
    assert result.news_event_id == event.id
