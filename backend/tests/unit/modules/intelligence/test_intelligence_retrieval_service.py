from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.intelligence.application.intelligence_retrieval_service import (
    AIReportRetrieval,
    CommunityRetrieval,
    IntelligenceRetrievalService,
    KnowledgeGraphRetrievalAdapter,
    NewsRetrieval,
)
from modules.intelligence.domain.entities import CommunityPost, NewsEvent, Summary
from modules.intelligence.domain.value_objects import (
    ArticleStatus,
    CommunityPlatform,
    CommunityPostId,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
    SummaryId,
    SummaryType,
)
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyCommunityPostRepository,
    SqlAlchemyNewsEventRepository,
    SqlAlchemySummaryRepository,
)
from modules.intelligence.ports.retrieval import IntelligenceRetrievalQuery
from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)
from modules.knowledge_graph.infrastructure.retrieval.graph_native_retrieval import GraphNativeRetrieval

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


async def test_news_retrieval_finds_events_for_entity(combined_session):
    events_repo = SqlAlchemyNewsEventRepository(session=combined_session)
    await events_repo.record(
        NewsEvent(
            id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary="Player picked up a knock.",
            confidence=0.7, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0,
            detected_at=T0, affected_entity_refs=("player-1",),
        )
    )
    await combined_session.commit()

    retrieval = NewsRetrieval(events=events_repo)
    result = await retrieval.retrieve(IntelligenceRetrievalQuery(subject_ref="player-1"))

    assert len(result.documents) == 1
    assert result.documents[0].modality == "news"
    assert result.documents[0].text == "Player picked up a knock."


async def test_news_retrieval_empty_for_unrelated_entity(combined_session):
    events_repo = SqlAlchemyNewsEventRepository(session=combined_session)
    retrieval = NewsRetrieval(events=events_repo)

    result = await retrieval.retrieve(IntelligenceRetrievalQuery(subject_ref="player-999"))

    assert result.documents == ()


async def test_community_retrieval_matches_text_substring(combined_session):
    posts_repo = SqlAlchemyCommunityPostRepository(session=combined_session)
    await posts_repo.upsert(
        CommunityPost(
            id=CommunityPostId(uuid4()), platform=CommunityPlatform.REDDIT, external_id="p1", author_ref="fan1",
            text="Manchester City looked dominant tonight.", posted_at=T0, fetched_at=T0,
        )
    )
    await posts_repo.upsert(
        CommunityPost(
            id=CommunityPostId(uuid4()), platform=CommunityPlatform.REDDIT, external_id="p2", author_ref="fan2",
            text="Unrelated chatter about the weather.", posted_at=T0, fetched_at=T0,
        )
    )
    await combined_session.commit()

    retrieval = CommunityRetrieval(posts=posts_repo)
    result = await retrieval.retrieve(IntelligenceRetrievalQuery(subject_ref="Manchester City"))

    assert len(result.documents) == 1
    assert result.documents[0].modality == "community"


async def test_ai_report_retrieval_finds_latest_summary_per_type(combined_session):
    summaries_repo = SqlAlchemySummaryRepository(session=combined_session)
    await summaries_repo.record(
        Summary(
            id=SummaryId(uuid4()), summary_type=SummaryType.SHORT, subject_ref="team-1", text="Short recap.",
            generated_at=T0,
        )
    )
    await summaries_repo.record(
        Summary(
            id=SummaryId(uuid4()), summary_type=SummaryType.TEAM, subject_ref="team-1", text="Team recap.",
            generated_at=T0,
        )
    )
    await combined_session.commit()

    retrieval = AIReportRetrieval(summaries=summaries_repo)
    result = await retrieval.retrieve(IntelligenceRetrievalQuery(subject_ref="team-1"))

    assert result.documents[0].modality == "ai_reports"
    texts = {d.text for d in result.documents}
    assert texts == {"Short recap.", "Team recap."}


async def test_ai_report_retrieval_empty_for_unknown_subject(combined_session):
    summaries_repo = SqlAlchemySummaryRepository(session=combined_session)
    retrieval = AIReportRetrieval(summaries=summaries_repo)

    result = await retrieval.retrieve(IntelligenceRetrievalQuery(subject_ref="unknown"))

    assert result.documents == ()


async def test_knowledge_graph_retrieval_adapter_delegates_to_graph_native_retrieval(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    player = await population.upsert_node(NodeType.PLAYER, "p1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await population.upsert_edge(player, team, EdgeType.PLAYS_FOR, T0)
    await combined_session.commit()

    query_service = GraphQueryService(nodes=nodes, edges=edges)
    native = GraphNativeRetrieval(query=query_service)
    adapter = KnowledgeGraphRetrievalAdapter(graph_retrieval=native)

    result = await adapter.retrieve(IntelligenceRetrievalQuery(subject_ref=str(player.id)))

    assert len(result.documents) == 1
    assert result.documents[0].modality == "knowledge_graph"
    assert "plays_for" in result.documents[0].text


async def test_knowledge_graph_retrieval_adapter_returns_empty_for_non_uuid_ref(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    query_service = GraphQueryService(nodes=nodes, edges=edges)
    native = GraphNativeRetrieval(query=query_service)
    adapter = KnowledgeGraphRetrievalAdapter(graph_retrieval=native)

    result = await adapter.retrieve(IntelligenceRetrievalQuery(subject_ref="not-a-uuid"))

    assert result.documents == ()


async def test_intelligence_retrieval_service_fans_out_across_all_modalities(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    team = await population.upsert_node(NodeType.TEAM, "team-1", now=T0)
    await combined_session.commit()

    events_repo = SqlAlchemyNewsEventRepository(session=combined_session)
    await events_repo.record(
        NewsEvent(
            id=NewsEventId(uuid4()), event_type=NewsEventType.MANAGER_CHANGE, summary="Manager change announced.",
            confidence=0.6, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0,
            detected_at=T0, affected_entity_refs=(str(team.id),),
        )
    )
    posts_repo = SqlAlchemyCommunityPostRepository(session=combined_session)
    await posts_repo.upsert(
        CommunityPost(
            id=CommunityPostId(uuid4()), platform=CommunityPlatform.REDDIT, external_id="p1", author_ref="fan1",
            text=f"Discussing {team.id} today.", posted_at=T0, fetched_at=T0,
        )
    )
    summaries_repo = SqlAlchemySummaryRepository(session=combined_session)
    await summaries_repo.record(
        Summary(
            id=SummaryId(uuid4()), summary_type=SummaryType.TEAM, subject_ref=str(team.id), text="Team recap.",
            generated_at=T0,
        )
    )
    await combined_session.commit()

    query_service = GraphQueryService(nodes=nodes, edges=edges)
    service = IntelligenceRetrievalService(
        news=NewsRetrieval(events=events_repo),
        community=CommunityRetrieval(posts=posts_repo),
        knowledge_graph=KnowledgeGraphRetrievalAdapter(graph_retrieval=GraphNativeRetrieval(query=query_service)),
        ai_reports=AIReportRetrieval(summaries=summaries_repo),
    )

    documents = await service.retrieve_all(str(team.id))

    modalities = {d.modality for d in documents}
    assert modalities == {"news", "community", "ai_reports"}  # no KG edges for this node -> empty, not an error
