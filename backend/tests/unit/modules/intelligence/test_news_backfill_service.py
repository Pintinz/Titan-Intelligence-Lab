from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.intelligence.application.news_backfill_service import (
    BackfillPlan,
    BackfillRequest,
    BackfillValidationError,
    NewsBackfillService,
)
from modules.intelligence.application.news_ingestion_service import NewsIngestionService
from modules.intelligence.domain.entities import NewsSource
from modules.intelligence.domain.value_objects import IntelligenceSyncRunId, NewsSourceId, NewsSourceType, SyncTrigger
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
    service = NewsBackfillService(
        news_ingestion=news_ingestion,
        enrichment=enrichment,
        fixtures=_FakeFixtureRepo(fixtures=list(fixtures)),
        teams=_FakeTeamRepo(teams=teams or {}),
        players=_FakePlayerRepo(players_by_team=players or {}),
        kg_nodes=_FakeKGNodeRepo(nodes=kg_nodes or {}),
    )
    return service, sources


# --- Validation / planning ----------------------------------------------------------------------

async def test_plan_rejects_unknown_source(sqlite_session):
    provider = MockNewsProvider()
    enrichment = _FakeEnrichmentOrchestrator()
    service, _sources = _service(sqlite_session, provider, enrichment)

    request = BackfillRequest(source_id=NewsSourceId(uuid4()), season_id=SEASON_ID, since=T0 - timedelta(days=1))

    with pytest.raises(BackfillValidationError, match="Unknown news source"):
        await service.plan(request, T0)


async def test_plan_rejects_until_before_since(sqlite_session):
    provider = MockNewsProvider()
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(
        source_id=source.id, season_id=SEASON_ID, since=T0, until=T0 - timedelta(hours=1),
    )

    with pytest.raises(BackfillValidationError, match="`until` cannot be earlier than `since`"):
        await service.plan(request, T0)


async def test_plan_rejects_future_since(sqlite_session):
    provider = MockNewsProvider()
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 + timedelta(days=1))

    with pytest.raises(BackfillValidationError, match="cannot be in the future"):
        await service.plan(request, T0)


async def test_plan_rejects_future_until(sqlite_session):
    provider = MockNewsProvider()
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(
        source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1), until=T0 + timedelta(days=1),
    )

    with pytest.raises(BackfillValidationError, match="cannot be in the future"):
        await service.plan(request, T0)


async def test_plan_clamps_a_since_beyond_the_hard_lookback_ceiling(sqlite_session, monkeypatch):
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_MAX_LOOKBACK_DAYS", 10)
    provider = MockNewsProvider()
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=365))

    plan = await service.plan(request, T0)

    assert plan.window_clamped is True
    assert plan.effective_since == T0 - timedelta(days=10)


async def test_plan_never_clamps_a_since_within_the_ceiling(sqlite_session, monkeypatch):
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_MAX_LOOKBACK_DAYS", 90)
    provider = MockNewsProvider()
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    since = T0 - timedelta(days=5)
    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=since)

    plan = await service.plan(request, T0)

    assert plan.window_clamped is False
    assert plan.effective_since == since


async def test_plan_clamps_max_articles_up_to_the_hard_ceiling_never_above(sqlite_session, monkeypatch):
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_MAX_ARTICLES_PER_RUN", 5)
    provider = MockNewsProvider()
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(
        source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1), max_articles=1000,
    )
    plan = await service.plan(request, T0)
    assert plan.max_articles == 5

    request_lower = BackfillRequest(
        source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1), max_articles=2,
    )
    plan_lower = await service.plan(request_lower, T0)
    assert plan_lower.max_articles == 2


async def test_plan_defaults_until_to_now_when_not_supplied(sqlite_session):
    provider = MockNewsProvider()
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1))
    plan = await service.plan(request, T0)

    assert plan.effective_until == T0


# --- Dry run ---------------------------------------------------------------------------------

async def test_dry_run_never_calls_the_provider_or_enrichment(sqlite_session):
    provider = MockNewsProvider(
        fixed_articles=(RawArticleRecord(external_ref="1", title="Story", url="https://example.com/1", body="Body.", published_at=T0),)
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1), dry_run=True)
    summary = await service.run(request, T0)

    assert summary.dry_run is True
    assert isinstance(summary.plan, BackfillPlan)
    assert summary.sync_run_id is None
    assert summary.articles_seen == 0
    assert enrichment.calls == []

    runs = await service.news_ingestion.sync_runs.list_recent()
    assert runs == []


async def test_dry_run_is_the_default_when_not_specified(sqlite_session):
    provider = MockNewsProvider(
        fixed_articles=(RawArticleRecord(external_ref="1", title="Story", url="https://example.com/1", body="Body.", published_at=T0),)
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1))
    assert request.dry_run is True

    summary = await service.run(request, T0)
    assert summary.dry_run is True
    assert enrichment.calls == []


# --- Real run: disabled by default -----------------------------------------------------------

async def test_real_run_is_refused_while_backfill_enabled_is_false(sqlite_session, monkeypatch):
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_ENABLED", False)
    provider = MockNewsProvider(
        fixed_articles=(RawArticleRecord(external_ref="1", title="Story", url="https://example.com/1", body="Body.", published_at=T0),)
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(sqlite_session, provider, enrichment)
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1), dry_run=False)
    summary = await service.run(request, T0)

    assert summary.dry_run is False
    assert summary.sync_run_id is None
    assert summary.articles_seen == 0
    assert enrichment.calls == []
    assert any("NEWS_BACKFILL_ENABLED" in e for e in summary.errors)


# --- Real run: enabled, full pipeline ---------------------------------------------------------

async def test_real_run_persists_via_sync_source_with_backfill_trigger_and_since_floor(sqlite_session, monkeypatch):
    """Proves `sync_source` (not a second ingestion pipeline) is what actually runs, with
    `trigger=BACKFILL` and `since_floor` set to the plan's effective_since."""
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_ENABLED", True)
    home, away = _team("Arsenal"), _team("Chelsea")
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(
                external_ref="1", title="Arsenal team news ahead of Chelsea clash",
                url="https://example.com/1", body="Full report.", published_at=T0 - timedelta(hours=1),
            ),
        )
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
    )
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(
        source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=2), dry_run=False,
    )
    summary = await service.run(request, T0)

    assert summary.sync_run_id is not None
    run = await service.news_ingestion.sync_runs.get(IntelligenceSyncRunId(uuid.UUID(summary.sync_run_id)))
    assert run.trigger is SyncTrigger.BACKFILL
    assert enrichment.calls == [("Arsenal team news ahead of Chelsea clash", SyncTrigger.BACKFILL)]
    assert summary.articles_relevant == 1
    assert summary.articles_sent_to_gemini == 1
    assert summary.provenance_verified == 0  # BACKFILL never produces VERIFIED_PRE_MATCH


async def test_real_run_excludes_articles_outside_the_requested_window(sqlite_session, monkeypatch):
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_ENABLED", True)
    home, away = _team("Arsenal"), _team("Chelsea")
    # `since_floor` already keeps anything before `since` from ever being fetched at all (that's
    # the lower bound's enforcement point); to exercise the *upper* bound, `until`, this article
    # is deliberately published AFTER `until` but still after `since`, so it reaches the fetch
    # (and would be seen/deduplicated-checked) but must be excluded before relevance/Gemini.
    requested_until = T0 - timedelta(days=1)
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(
                external_ref="1", title="Arsenal news within window", url="https://example.com/1",
                body="Arsenal content.", published_at=T0 - timedelta(days=5),
            ),
            RawArticleRecord(
                external_ref="2", title="Arsenal news after the requested until",
                url="https://example.com/2", body="Arsenal content.",
                published_at=requested_until + timedelta(hours=1),
            ),
        )
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
    )
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(
        source_id=source.id, season_id=SEASON_ID,
        since=T0 - timedelta(days=10), until=requested_until, dry_run=False,
    )
    summary = await service.run(request, T0)

    assert summary.articles_seen == 2  # both fetched — since_floor only bounds the lower edge
    assert summary.articles_within_window == 1
    assert summary.articles_outside_window == 1
    assert enrichment.calls == [("Arsenal news within window", SyncTrigger.BACKFILL)]


async def test_real_run_never_calls_enrichment_for_irrelevant_articles(sqlite_session, monkeypatch):
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_ENABLED", True)
    home, away = _team("Arsenal"), _team("Chelsea")
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(
                external_ref="1", title="Local bakery wins award", url="https://example.com/1",
                body="Nothing football related.", published_at=T0 - timedelta(hours=1),
            ),
        )
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
    )
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1), dry_run=False)
    summary = await service.run(request, T0)

    assert summary.articles_skipped_by_relevance == 1
    assert summary.articles_sent_to_gemini == 0
    assert enrichment.calls == []


async def test_real_run_gemini_budget_is_never_exceeded(sqlite_session, monkeypatch):
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_ENABLED", True)
    monkeypatch.setattr(mod, "NEWS_BACKFILL_MAX_ARTICLES_PER_RUN", 1)
    home, away = _team("Arsenal"), _team("Chelsea")
    articles = tuple(
        RawArticleRecord(
            external_ref=str(i), title=f"Arsenal team news {i}", url=f"https://example.com/{i}",
            body="Arsenal team news content.", published_at=T0 - timedelta(hours=1, minutes=i),
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
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1), dry_run=False)
    summary = await service.run(request, T0)

    assert summary.articles_relevant == 3
    assert summary.articles_sent_to_gemini == 1
    assert len(enrichment.calls) == 1


async def test_real_run_gemini_failure_is_isolated_and_recorded(sqlite_session, monkeypatch):
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_ENABLED", True)
    home, away = _team("Arsenal"), _team("Chelsea")
    articles = (
        RawArticleRecord(
            external_ref="1", title="Arsenal failing article", url="https://example.com/1",
            body="Arsenal news.", published_at=T0 - timedelta(hours=1),
        ),
        RawArticleRecord(
            external_ref="2", title="Arsenal succeeding article", url="https://example.com/2",
            body="Arsenal news.", published_at=T0 - timedelta(hours=2),
        ),
    )
    provider = MockNewsProvider(fixed_articles=articles)
    enrichment = _FakeEnrichmentOrchestrator(raise_for_titles={"Arsenal failing article"})
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
    )
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1), dry_run=False)
    summary = await service.run(request, T0)

    assert summary.enrichment_failures == 1
    assert summary.articles_enriched == 1
    assert len(summary.errors) == 1


async def test_real_run_reuses_deduplication_a_second_call_never_reingests(sqlite_session, monkeypatch):
    """Proves this service reuses `NewsIngestionService`'s existing dedup rather than inventing a
    second one — the same article fetched across two separate backfill calls is only ever
    ingested (and only ever enriched) once."""
    import modules.intelligence.application.news_backfill_service as mod

    monkeypatch.setattr(mod, "NEWS_BACKFILL_ENABLED", True)
    home, away = _team("Arsenal"), _team("Chelsea")
    provider = MockNewsProvider(
        fixed_articles=(
            RawArticleRecord(
                external_ref="1", title="Arsenal repeated story", url="https://example.com/1",
                body="Arsenal content.", published_at=T0 - timedelta(hours=1),
            ),
        )
    )
    enrichment = _FakeEnrichmentOrchestrator()
    service, sources = _service(
        sqlite_session, provider, enrichment,
        fixtures=[_fixture(home, away, T0 + timedelta(hours=2))],
        teams={home.id: home, away.id: away},
    )
    source = await _seed_source(sources, sqlite_session)

    request = BackfillRequest(source_id=source.id, season_id=SEASON_ID, since=T0 - timedelta(days=1), dry_run=False)
    first = await service.run(request, T0)
    assert first.articles_seen == 1

    # `sync_source`'s own checkpoint already prevents a *second* identical request from ever
    # re-fetching an article past the checkpoint (a stronger, different guarantee than
    # content-hash dedup on re-fetch) — to exercise dedup itself (the same story arriving again,
    # e.g. an operator deliberately re-running a wider backfill after a checkpoint reset), reset
    # the checkpoint back before the article's publish time, same scenario `sync_source`'s own
    # docstring names ("even on a fresh/empty checkpoint").
    from modules.intelligence.domain.value_objects import IntelligenceChannelType

    checkpoint = await service.news_ingestion.checkpoints.get(IntelligenceChannelType.NEWS, str(source.id))
    checkpoint.last_synced_at = T0 - timedelta(days=2)
    await service.news_ingestion.checkpoints.upsert(checkpoint)
    await sqlite_session.commit()

    second = await service.run(request, T0 + timedelta(minutes=5))

    assert second.articles_seen == 1
    assert second.articles_deduplicated == 1
    assert second.articles_within_window == 0
    assert len(enrichment.calls) == 1  # only the first run's article was ever enriched
