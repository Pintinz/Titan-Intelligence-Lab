from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.intelligence.application.news_ingestion_service import NewsIngestionService
from modules.intelligence.application.scheduled_news_sync_service import ScheduledNewsSyncService
from modules.intelligence.domain.entities import NewsSource
from modules.intelligence.domain.value_objects import NewsSourceId, NewsSourceType, SyncTrigger
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyIntelligenceSyncCheckpointRepository,
    SqlAlchemyIntelligenceSyncRunRepository,
    SqlAlchemyNewsArticleRepository,
    SqlAlchemyNewsSourceRepository,
)
from modules.intelligence.infrastructure.providers.mock_news_provider import MockNewsProvider
from modules.intelligence.ports.news_provider import RawArticleRecord
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.sports.domain.entities import Fixture, Player, Team
from modules.sports.domain.value_objects import FixtureId, FixtureStatus, PlayerId, SeasonId, SportId, TeamId

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)
SEASON_ID = SeasonId(uuid4())


@dataclass
class _FakeFixtureRepo:
    fixtures: list

    async def list_by_season(self, season_id):
        return self.fixtures


@dataclass
class _FakeTeamRepo:
    teams: dict

    async def get(self, team_id):
        return self.teams.get(team_id)


@dataclass
class _FakePlayerRepo:
    players_by_team: dict = field(default_factory=dict)

    async def list_by_team(self, team_id):
        return self.players_by_team.get(team_id, [])


@dataclass
class _FakeKGNodeRepo:
    nodes: dict = field(default_factory=dict)

    async def get_by_entity_ref(self, node_type, entity_ref):
        return self.nodes.get((node_type, entity_ref))


@dataclass
class _FakeEnrichmentOrchestrator:
    scores_by_title: dict = field(default_factory=dict)
    raise_for_titles: set = field(default_factory=set)
    calls: list = field(default_factory=list)

    async def enrich_article(self, article, now, *, trigger, sync_run_id=None):
        self.calls.append((article.title, trigger))
        if article.title in self.raise_for_titles:
            raise RuntimeError("gemini failure")
        return self.scores_by_title.get(article.title, [])


def _team(name: str) -> Team:
    return Team(id=TeamId(uuid4()), sport_id=SportId(uuid4()), name=name, short_name=name[:3], country="England")


def _fixture(home: Team, away: Team, scheduled_at: datetime, status=FixtureStatus.SCHEDULED) -> Fixture:
    return Fixture(
        id=FixtureId(uuid4()), season_id=SEASON_ID, home_team_id=home.id, away_team_id=away.id,
        venue_id=None, scheduled_at=scheduled_at, status=status,
    )


def _news_ingestion_service(sqlite_session, provider) -> tuple[NewsIngestionService, object]:
    sources = SqlAlchemyNewsSourceRepository(session=sqlite_session)
    service = NewsIngestionService(
        sources=sources,
        articles=SqlAlchemyNewsArticleRepository(session=sqlite_session),
        checkpoints=SqlAlchemyIntelligenceSyncCheckpointRepository(session=sqlite_session),
        sync_runs=SqlAlchemyIntelligenceSyncRunRepository(session=sqlite_session),
        providers={"rss_feed": provider},
    )
    return service, sources


async def _seed_source(sources, sqlite_session) -> NewsSource:
    source = NewsSource(
        id=NewsSourceId(uuid4()), source_type=NewsSourceType.RSS_FEED, name="Feed",
        url="https://example.com/feed.xml", created_at=T0,
    )
    await sources.upsert(source)
    await sqlite_session.commit()
    return source


def _service(sqlite_session, provider, enrichment, fixtures=(), teams=None, players=None, kg_nodes=None):
    news_ingestion, sources = _news_ingestion_service(sqlite_session, provider)
    service = ScheduledNewsSyncService(
        news_ingestion=news_ingestion,
        enrichment=enrichment,
        fixtures=_FakeFixtureRepo(fixtures=list(fixtures)),
        teams=_FakeTeamRepo(teams=teams or {}),
        players=_FakePlayerRepo(players_by_team=players or {}),
        kg_nodes=_FakeKGNodeRepo(nodes=kg_nodes or {}),
    )
    return service, sources


async def test_disabled_by_default_no_ops_entirely(sqlite_session, monkeypatch):
    import modules.intelligence.application.scheduled_news_sync_service as mod

    monkeypatch.setattr(mod, "NEWS_SYNC_ENABLED", False)
    provider = MockNewsProvider(
        fixed_articles=(RawArticleRecord(external_ref="1", title="Story", url="https://example.com/1", body="Body.", published_at=T0),)
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    await _seed_source(sources, sqlite_session)

    summary = await service.run("football", SEASON_ID, T0)

    assert summary.enabled is False
    assert summary.articles_seen == 0
    assert enrichment.calls == []


async def test_enabled_scheduled_run_always_uses_live_scheduled_trigger(sqlite_session, monkeypatch):
    import modules.intelligence.application.scheduled_news_sync_service as mod

    monkeypatch.setattr(mod, "NEWS_SYNC_ENABLED", True)
    home, away = _team("Arsenal"), _team("Chelsea")
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(
                external_ref="1", title="Arsenal injury update ahead of Chelsea clash",
                url="https://example.com/1", body="Full team news.", published_at=T0,
            ),
        )
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
    )
    await _seed_source(sources, sqlite_session)

    summary = await service.run("football", SEASON_ID, T0)

    assert enrichment.calls == [("Arsenal injury update ahead of Chelsea clash", SyncTrigger.LIVE_SCHEDULED)]
    assert summary.articles_relevant == 1
    assert summary.articles_sent_to_gemini == 1
    assert summary.articles_enriched == 1


async def test_irrelevant_article_never_reaches_enrichment(sqlite_session, monkeypatch):
    import modules.intelligence.application.scheduled_news_sync_service as mod

    monkeypatch.setattr(mod, "NEWS_SYNC_ENABLED", True)
    home, away = _team("Arsenal"), _team("Chelsea")
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(
                external_ref="1", title="Local bakery wins award", url="https://example.com/1",
                body="Nothing football related.", published_at=T0,
            ),
        )
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
    )
    await _seed_source(sources, sqlite_session)

    summary = await service.run("football", SEASON_ID, T0)

    assert enrichment.calls == []
    assert summary.articles_skipped_by_relevance == 1
    assert summary.articles_sent_to_gemini == 0


async def test_gemini_budget_is_never_exceeded(sqlite_session, monkeypatch):
    import modules.intelligence.application.scheduled_news_sync_service as mod

    monkeypatch.setattr(mod, "NEWS_SYNC_ENABLED", True)
    monkeypatch.setattr(mod, "NEWS_SYNC_MAX_ARTICLES_PER_RUN", 1)
    home, away = _team("Arsenal"), _team("Chelsea")
    articles = tuple(
        RawArticleRecord(
            external_ref=str(i), title=f"Arsenal team news {i}", url=f"https://example.com/{i}",
            body="Arsenal team news content.", published_at=T0 - timedelta(minutes=i),
        )
        for i in range(3)
    )
    provider = MockNewsProvider(fixed_articles=articles)
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
    )
    await _seed_source(sources, sqlite_session)

    summary = await service.run("football", SEASON_ID, T0)

    assert summary.articles_relevant == 3
    assert summary.articles_sent_to_gemini == 1
    assert len(enrichment.calls) == 1


async def test_gemini_failure_is_isolated_and_recorded(sqlite_session, monkeypatch):
    import modules.intelligence.application.scheduled_news_sync_service as mod

    monkeypatch.setattr(mod, "NEWS_SYNC_ENABLED", True)
    home, away = _team("Arsenal"), _team("Chelsea")
    articles = (
        RawArticleRecord(
            external_ref="1", title="Arsenal failing article", url="https://example.com/1",
            body="Arsenal news.", published_at=T0,
        ),
        RawArticleRecord(
            external_ref="2", title="Arsenal succeeding article", url="https://example.com/2",
            body="Arsenal news.", published_at=T0 - timedelta(minutes=1),
        ),
    )
    provider = MockNewsProvider(fixed_articles=articles)
    enrichment = _FakeEnrichmentOrchestrator(raise_for_titles={"Arsenal failing article"})
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
    )
    await _seed_source(sources, sqlite_session)

    summary = await service.run("football", SEASON_ID, T0)

    assert summary.enrichment_failures == 1
    assert summary.articles_enriched == 1
    assert len(summary.errors) == 1


async def test_relevance_vocabulary_includes_players_and_kg_aliases(sqlite_session, monkeypatch):
    import modules.intelligence.application.scheduled_news_sync_service as mod

    monkeypatch.setattr(mod, "NEWS_SYNC_ENABLED", True)
    home, away = _team("Arsenal FC"), _team("Chelsea FC")
    player = Player(
        id=PlayerId(uuid4()), sport_id=home.sport_id, name="Bukayo Saka", date_of_birth=None,
        position="forward", team_id=home.id,
    )
    kg_alias_node = type("Node", (), {"aliases": ["The Gunners"]})()
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(
                external_ref="1", title="The Gunners plan for Saka fitness",
                url="https://example.com/1", body="Full report.", published_at=T0,
            ),
        )
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
        players={home.id: [player]},
        kg_nodes={(NodeType.TEAM, str(home.id.value)): kg_alias_node},
    )
    await _seed_source(sources, sqlite_session)

    summary = await service.run("football", SEASON_ID, T0)

    assert summary.articles_relevant == 1
    assert enrichment.calls, "expected the alias-matched article to reach enrichment"


async def test_fixtures_outside_the_window_do_not_contribute_vocabulary(sqlite_session, monkeypatch):
    import modules.intelligence.application.scheduled_news_sync_service as mod

    monkeypatch.setattr(mod, "NEWS_SYNC_ENABLED", True)
    home, away = _team("Arsenal"), _team("Chelsea")
    far_future_fixture = _fixture(home, away, T0 + timedelta(days=60))
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(
                external_ref="1", title="Arsenal news today", url="https://example.com/1",
                body="Arsenal content.", published_at=T0,
            ),
        )
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[far_future_fixture], teams={home.id: home, away.id: away},
    )
    await _seed_source(sources, sqlite_session)

    summary = await service.run("football", SEASON_ID, T0)

    assert summary.articles_relevant == 0
    assert enrichment.calls == []
