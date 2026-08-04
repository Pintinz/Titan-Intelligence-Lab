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
    MatchTeamNamesResolver,
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


async def test_news_retrieval_matches_via_additional_refs_not_just_subject_ref(combined_session):
    """Real `NewsEvent`s never name a fixture id in `affected_entity_refs` — only team/player
    names — so a match-level `subject_ref` query only ever finds anything via `additional_refs`
    (the resolved team names)."""
    events_repo = SqlAlchemyNewsEventRepository(session=combined_session)
    await events_repo.record(
        NewsEvent(
            id=NewsEventId(uuid4()), event_type=NewsEventType.MANAGER_CHANGE, summary="Manager change announced.",
            confidence=0.6, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0,
            detected_at=T0, affected_entity_refs=("Newcastle United",),
        )
    )
    await combined_session.commit()

    retrieval = NewsRetrieval(events=events_repo)

    empty = await retrieval.retrieve(IntelligenceRetrievalQuery(subject_ref="fixture-1"))
    assert empty.documents == ()

    found = await retrieval.retrieve(
        IntelligenceRetrievalQuery(subject_ref="fixture-1", additional_refs=("Newcastle United",))
    )
    assert len(found.documents) == 1
    assert found.documents[0].text == "Manager change announced."


async def test_news_retrieval_dedupes_events_matching_multiple_refs(combined_session):
    events_repo = SqlAlchemyNewsEventRepository(session=combined_session)
    await events_repo.record(
        NewsEvent(
            id=NewsEventId(uuid4()), event_type=NewsEventType.MANAGER_CHANGE, summary="Derby preview.",
            confidence=0.6, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0,
            detected_at=T0, affected_entity_refs=("Team A", "Team B"),
        )
    )
    await combined_session.commit()

    retrieval = NewsRetrieval(events=events_repo)
    result = await retrieval.retrieve(
        IntelligenceRetrievalQuery(subject_ref="fixture-1", additional_refs=("Team A", "Team B"))
    )

    assert len(result.documents) == 1


async def test_community_retrieval_matches_via_additional_refs(combined_session):
    posts_repo = SqlAlchemyCommunityPostRepository(session=combined_session)
    await posts_repo.upsert(
        CommunityPost(
            id=CommunityPostId(uuid4()), platform=CommunityPlatform.REDDIT, external_id="p1", author_ref="fan1",
            text="Manchester City looked dominant tonight.", posted_at=T0, fetched_at=T0,
        )
    )
    await combined_session.commit()

    retrieval = CommunityRetrieval(posts=posts_repo)

    empty = await retrieval.retrieve(IntelligenceRetrievalQuery(subject_ref="fixture-1"))
    assert empty.documents == ()

    found = await retrieval.retrieve(
        IntelligenceRetrievalQuery(subject_ref="fixture-1", additional_refs=("Manchester City",))
    )
    assert len(found.documents) == 1


async def test_match_team_names_resolver_finds_team_display_names(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    match = await population.upsert_node(NodeType.MATCH, "fixture-1", now=T0)
    home = await population.upsert_node(NodeType.TEAM, "team-home", attributes={"name": "Man City"}, now=T0)
    away = await population.upsert_node(NodeType.TEAM, "team-away", attributes={"name": "Arsenal"}, now=T0)
    venue = await population.upsert_node(NodeType.VENUE, "venue-1", attributes={"name": "Etihad Stadium"}, now=T0)
    await population.upsert_edge(match, home, EdgeType.INVOLVED_IN, T0)
    await population.upsert_edge(match, away, EdgeType.INVOLVED_IN, T0)
    await population.upsert_edge(match, venue, EdgeType.LOCATED_IN, T0)
    await combined_session.commit()

    resolver = MatchTeamNamesResolver(nodes=nodes, query=GraphQueryService(nodes=nodes, edges=edges))
    names = await resolver.team_names_for_match("fixture-1")

    assert set(names) == {"Man City", "Arsenal"}


async def test_match_team_names_resolver_returns_empty_for_unknown_match(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    resolver = MatchTeamNamesResolver(nodes=nodes, query=GraphQueryService(nodes=nodes, edges=edges))

    names = await resolver.team_names_for_match("unknown-fixture")

    assert names == ()


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


async def test_knowledge_graph_retrieval_adapter_resolves_subject_ref_via_entity_ref(combined_session):
    """`subject_ref` is always an external entity_ref (e.g. a fixture id) in real callers
    (`PredictionEngine`/`ExplainabilityEngine`), never the KG node's own internal id — the
    adapter must resolve it through `get_by_entity_ref` rather than parsing it as a `KGNodeId`."""
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    match = await population.upsert_node(NodeType.MATCH, "fixture-1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "t1", now=T0)
    await population.upsert_edge(match, team, EdgeType.INVOLVED_IN, T0)
    await combined_session.commit()

    query_service = GraphQueryService(nodes=nodes, edges=edges)
    native = GraphNativeRetrieval(query=query_service)
    adapter = KnowledgeGraphRetrievalAdapter(graph_retrieval=native, nodes=nodes)

    result = await adapter.retrieve(IntelligenceRetrievalQuery(subject_ref="fixture-1"))

    assert len(result.documents) == 1
    assert result.documents[0].modality == "knowledge_graph"
    assert "involved_in" in result.documents[0].text


async def test_knowledge_graph_retrieval_adapter_returns_empty_for_unknown_entity_ref(combined_session):
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    query_service = GraphQueryService(nodes=nodes, edges=edges)
    native = GraphNativeRetrieval(query=query_service)
    adapter = KnowledgeGraphRetrievalAdapter(graph_retrieval=native, nodes=nodes)

    result = await adapter.retrieve(IntelligenceRetrievalQuery(subject_ref="unknown-fixture"))

    assert result.documents == ()


async def test_intelligence_retrieval_service_fans_out_across_all_modalities(combined_session):
    """News/community items are keyed by realistic content — a team display name in the news
    event's affected_entity_refs, the team name mentioned in a community post's text — never the
    fixture id itself, proving `retrieve_all` genuinely resolves and uses the match's team names
    rather than just passing `subject_ref` straight through."""
    nodes = SqlAlchemyKGNodeRepository(session=combined_session)
    edges = SqlAlchemyKGEdgeRepository(session=combined_session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    match = await population.upsert_node(NodeType.MATCH, "fixture-1", now=T0)
    team = await population.upsert_node(NodeType.TEAM, "team-1", attributes={"name": "Man City"}, now=T0)
    await population.upsert_edge(match, team, EdgeType.INVOLVED_IN, T0)
    await combined_session.commit()

    subject_ref = "fixture-1"
    events_repo = SqlAlchemyNewsEventRepository(session=combined_session)
    await events_repo.record(
        NewsEvent(
            id=NewsEventId(uuid4()), event_type=NewsEventType.MANAGER_CHANGE, summary="Manager change announced.",
            confidence=0.6, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0,
            detected_at=T0, affected_entity_refs=("Man City",),
        )
    )
    posts_repo = SqlAlchemyCommunityPostRepository(session=combined_session)
    await posts_repo.upsert(
        CommunityPost(
            id=CommunityPostId(uuid4()), platform=CommunityPlatform.REDDIT, external_id="p1", author_ref="fan1",
            text="Man City fans are excited for this one.", posted_at=T0, fetched_at=T0,
        )
    )
    summaries_repo = SqlAlchemySummaryRepository(session=combined_session)
    await summaries_repo.record(
        Summary(
            id=SummaryId(uuid4()), summary_type=SummaryType.TEAM, subject_ref=subject_ref, text="Team recap.",
            generated_at=T0,
        )
    )
    await combined_session.commit()

    query_service = GraphQueryService(nodes=nodes, edges=edges)
    service = IntelligenceRetrievalService(
        news=NewsRetrieval(events=events_repo),
        community=CommunityRetrieval(posts=posts_repo),
        knowledge_graph=KnowledgeGraphRetrievalAdapter(
            graph_retrieval=GraphNativeRetrieval(query=query_service), nodes=nodes
        ),
        ai_reports=AIReportRetrieval(summaries=summaries_repo),
        team_names=MatchTeamNamesResolver(nodes=nodes, query=query_service),
    )

    documents = await service.retrieve_all(subject_ref)

    modalities = {d.modality for d in documents}
    assert modalities == {"news", "community", "ai_reports", "knowledge_graph"}
