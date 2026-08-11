"""Public, unauthenticated aggregate endpoints for the TitanIQ landing page — Milestone 10.4.

Every other route in this API requires `Depends(get_current_user)` at minimum; the only other
unauthenticated route in the whole service is `GET /api/v1/health`. Before this router, the
signed-out landing page had no real data to show at all, so it used a self-disclosed illustrative
placeholder (`frontend/src/pages/landing/sample-data.ts`, now deleted) with a visible "Illustrative"
badge on every card.

These four endpoints exist so the landing page can show real platform numbers/examples instead —
read-only, aggregate or curated-real (never a raw entity dump), and deliberately narrow: never a
draft/unpublished prediction, never raw community post text, never per-user/per-organization data.
Every handler REUSES an existing application service/repository already used by an authenticated
router — no new query logic beyond composing calls the same way `sports_router.list_sport_fixtures`
and `prediction_analytics_router.ai_picks` already do (audit → reuse → extend, never rewrite).

No response-caching/rate-limiting layer exists anywhere else in this API (audited before writing
this file) — since these are now the only endpoints in the service reachable without a session,
each handler is backed by a small in-process TTL cache scoped to this module only, so anonymous
traffic can't repeatedly trigger the N+1 fixture/competition walk below. This is new, minimal,
self-contained infrastructure (not a reuse of anything else) — flagged here rather than silently
added.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.composition import (
    build_event_extraction_service,
    build_graph_monitoring_service,
    build_graph_query_service,
    build_market_registry_service,
    build_monitoring_service,
    build_news_impact_engine,
    build_news_ingestion_service,
    build_prediction_cache_service,
    get_session,
    get_sport_plugin_registry,
)
from modules.ingestion.domain.value_objects import SyncStatus
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.predictions.domain.value_objects import PredictionStatus
from modules.sports.domain.value_objects import FixtureId, FixtureStatus
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyTeamRepository,
)

router = APIRouter(prefix="/api/v1/public", tags=["public"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# -- module-scoped TTL cache (see module docstring) ----------------------------------------------

_CACHE_TTL_SECONDS = 60
_cache: dict[str, tuple[float, dict]] = {}


def _cached(key: str) -> dict | None:
    entry = _cache.get(key)
    if entry is not None and time.monotonic() - entry[0] < _CACHE_TTL_SECONDS:
        return entry[1]
    return None


def _store(key: str, value):
    _cache[key] = (time.monotonic(), value)
    return value


def _is_same_day(scheduled_at: datetime, now: datetime) -> bool:
    aware = scheduled_at if scheduled_at.tzinfo is not None else scheduled_at.replace(tzinfo=now.tzinfo)
    return aware.astimezone(now.tzinfo).date() == now.date()


# -- Platform summary ------------------------------------------------------------------------------


@router.get("/platform-summary")
async def platform_summary(session: AsyncSession = Depends(get_session)):
    """Real aggregate coverage/activity counts — sports covered, competitions tracked, live/today/
    completed fixture totals, a sampled published-prediction count, real Knowledge Graph scale, and
    the real last-sync timestamp. Never a specific team, match, or prediction — see
    `featured-intelligence`/`news-intelligence` for those."""
    cached = _cached("platform-summary")
    if cached is not None:
        return envelope(cached)

    now = _now()
    registry = get_sport_plugin_registry()
    plugins = registry.all()

    sports_repo = SqlAlchemySportRepository(session=session)
    competitions_repo = SqlAlchemyCompetitionRepository(session=session)
    seasons_repo = SqlAlchemySeasonRepository(session=session)
    fixtures_repo = SqlAlchemyFixtureRepository(session=session)

    sports_data: list[dict] = []
    total_competitions = 0
    total_live = 0
    total_today = 0
    total_completed = 0

    for plugin in plugins:
        sport = await sports_repo.get_by_code(plugin.code)
        competitions = await competitions_repo.list_by_sport(sport.id) if sport is not None else []
        live_count = 0
        today_count = 0
        completed_count = 0
        for competition in competitions:
            seasons = await seasons_repo.list_by_competition(competition.id)
            for season in seasons:
                fixtures = await fixtures_repo.list_by_season(season.id)
                for fixture in fixtures:
                    if fixture.status is FixtureStatus.LIVE:
                        live_count += 1
                    elif fixture.status is FixtureStatus.COMPLETED:
                        completed_count += 1
                    if _is_same_day(fixture.scheduled_at, now):
                        today_count += 1
        sports_data.append(
            {
                "code": plugin.code.value,
                "display_name": plugin.display_name,
                "competitions": len(competitions),
                "live_fixtures": live_count,
                "today_fixtures": today_count,
            }
        )
        total_competitions += len(competitions)
        total_live += live_count
        total_today += today_count
        total_completed += completed_count

    prediction_service = build_prediction_cache_service(session)
    recent_predictions = await prediction_service.predictions.list_recent(limit=5000)
    published_count = sum(1 for p in recent_predictions if p.status is PredictionStatus.PUBLISHED)

    graph_snapshot = await build_graph_monitoring_service(session).snapshot()

    monitoring = build_monitoring_service(session)
    sync_runs = await monitoring.sync_status(limit=50)
    completed_runs = [r for r in sync_runs if r.status in (SyncStatus.SUCCEEDED.value, SyncStatus.PARTIAL.value)]
    last_synced_at = max((r.started_at for r in completed_runs), default=None)

    data = {
        "sports": sports_data,
        "sports_covered": len(plugins),
        "competitions_tracked": total_competitions,
        "live_fixtures": total_live,
        "today_fixtures": total_today,
        "completed_fixtures_recent": total_completed,
        # Bounded-sample count (over the most recent 5000 predictions) — no repository method
        # exists for a true unbounded COUNT(*), so this is honestly a sample, not a lifetime total.
        "published_predictions_sample": published_count,
        "published_predictions_sample_size": len(recent_predictions),
        "knowledge_graph": {"node_count": graph_snapshot.node_count, "edge_count": graph_snapshot.edge_count},
        "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
        "generated_at": now.isoformat(),
    }
    return envelope(_store("platform-summary", data))


# -- Featured Match Intelligence --------------------------------------------------------------------


@router.get("/featured-intelligence")
async def featured_intelligence(limit: int = Query(default=3, ge=1, le=6), session: AsyncSession = Depends(get_session)):
    """Real, currently-PUBLISHED predictions ranked by confidence — the same ranking basis as the
    authenticated `/predictions/picks`, but capped to one (the highest-confidence) pick per market
    so the carousel shows the platform's real market breadth rather than one dominant market
    repeated across fixtures — resolved down to real team names and a short evidence highlight
    (top positive/negative feature labels only, never raw SHAP weights or internal ids)."""
    cache_key = f"featured-intelligence:{limit}"
    cached = _cached(cache_key)
    if cached is not None:
        return envelope(cached)

    prediction_service = build_prediction_cache_service(session)
    market_service = build_market_registry_service(session)
    fixtures_repo = SqlAlchemyFixtureRepository(session=session)
    teams_repo = SqlAlchemyTeamRepository(session=session)
    seasons_repo = SqlAlchemySeasonRepository(session=session)
    competitions_repo = SqlAlchemyCompetitionRepository(session=session)

    recent = await prediction_service.predictions.list_recent(limit=500)
    published = [p for p in recent if p.status is PredictionStatus.PUBLISHED]

    market_cache: dict[str, object] = {}
    picks = []
    for prediction in published:
        market_key = str(prediction.market_id)
        if market_key not in market_cache:
            market_cache[market_key] = await market_service.markets.get(prediction.market_id)
        market = market_cache[market_key]
        if market is not None:
            picks.append((prediction, market))
    picks.sort(key=lambda pm: pm[0].confidence.composite, reverse=True)

    # Diversify by market — one systematically high-confidence market (e.g. a goals-over/under
    # line) would otherwise crowd out every slot with the same pick repeated across fixtures.
    # Keep only the single highest-confidence pick per market_key (picks is already sorted, so
    # the first occurrence per key is its best), then re-rank that diversified set by confidence.
    best_per_market: dict[str, tuple] = {}
    for prediction, market in picks:
        if market.market_key not in best_per_market:
            best_per_market[market.market_key] = (prediction, market)
    picks = sorted(best_per_market.values(), key=lambda pm: pm[0].confidence.composite, reverse=True)

    data: list[dict] = []
    for prediction, market in picks:
        if len(data) >= limit:
            break
        try:
            fixture = await fixtures_repo.get(FixtureId(uuid.UUID(prediction.subject_ref)))
        except ValueError:
            fixture = None
        if fixture is None:
            continue
        home = await teams_repo.get(fixture.home_team_id)
        away = await teams_repo.get(fixture.away_team_id)
        season = await seasons_repo.get(fixture.season_id)
        competition = await competitions_repo.get(season.competition_id) if season is not None else None

        data.append(
            {
                "prediction_id": str(prediction.id),
                "fixture_id": str(fixture.id),
                "sport_code": market.sport_code,
                "competition_name": competition.name if competition else None,
                "home_team": {"name": home.name, "short_name": home.short_name, "logo_url": home.logo_url} if home else None,
                "away_team": {"name": away.name, "short_name": away.short_name, "logo_url": away.logo_url} if away else None,
                "scheduled_at": fixture.scheduled_at.isoformat(),
                "status": fixture.status.value,
                "market_name": market.name,
                "market_key": market.market_key,
                "value": prediction.value,
                "probability": prediction.probability,
                "confidence_composite": prediction.confidence.composite,
                "evidence_highlights": {
                    "supporting": [name for name, _weight in prediction.explanation.top_positive_features[:2]],
                    "contradicting": [name for name, _weight in prediction.explanation.top_negative_features[:1]],
                },
                "generated_at": prediction.generated_at.isoformat() if prediction.generated_at else None,
            }
        )

    return envelope(_store(cache_key, data), meta={"count": len(data)})


# -- News Intelligence -------------------------------------------------------------------------------


@router.get("/news-intelligence")
async def news_intelligence(limit: int = Query(default=6, ge=1, le=12), session: AsyncSession = Depends(get_session)):
    """Real recently-scored news items — walks the most recent real ImpactScores back to their
    NewsEvent and source NewsArticle, so every headline shown already has a real, backend-computed
    impact score attached (never a frontend-inferred one)."""
    cache_key = f"news-intelligence:{limit}"
    cached = _cached(cache_key)
    if cached is not None:
        return envelope(cached)

    impact_engine = build_news_impact_engine(session)
    event_service = build_event_extraction_service(session)
    news_service = build_news_ingestion_service(session)

    recent_scores = await impact_engine.impact_scores.list_recent(limit=limit * 4)

    data: list[dict] = []
    seen_articles: set[str] = set()
    for score in recent_scores:
        if len(data) >= limit:
            break
        event = await event_service.events.get(score.news_event_id)
        if event is None or str(event.article_id) in seen_articles:
            continue
        article = await news_service.articles.get(event.article_id)
        if article is None:
            continue
        seen_articles.add(str(event.article_id))
        data.append(
            {
                "article_id": str(article.id),
                "headline": article.title,
                "url": article.url,
                "published_at": article.published_at.isoformat(),
                "event_summary": event.summary,
                "event_type": event.event_type.value,
                "impact_score": score.impact_score,
                "impact_confidence": score.confidence,
                "affected_teams": list(score.affected_teams),
                "affected_competitions": list(score.affected_competitions),
            }
        )

    return envelope(_store(cache_key, data), meta={"count": len(data)})


# -- Knowledge Graph preview --------------------------------------------------------------------------


@router.get("/knowledge-graph-preview")
async def knowledge_graph_preview(session: AsyncSession = Depends(get_session)):
    """Real graph scale (node/edge counts by type) plus a real neighborhood around one real,
    genuinely high-connectivity team node — never a fabricated relationship. Nodes are identified
    by `node_type`/`entity_ref` only; this router does not resolve `entity_ref` to a display name
    (no such resolver exists yet for every node type) — the frontend shows the real type/ref rather
    than a guessed label."""
    cached = _cached("kg-preview")
    if cached is not None:
        return envelope(cached)

    monitoring = build_graph_monitoring_service(session)
    snapshot = await monitoring.snapshot()

    query_service = build_graph_query_service(session)
    top_teams = await query_service.most_connected(node_type=NodeType.TEAM, edge_type=EdgeType.PLAYS_FOR, direction="in", limit=1)

    preview_entity = None
    if top_teams:
        node, degree = top_teams[0]
        subgraph = await query_service.neighborhood(node_id=node.id, depth=1, max_nodes=12)
        preview_entity = {
            "node": {"id": str(node.id), "type": node.node_type.value, "entity_ref": node.entity_ref},
            "connection_count": degree,
            "neighbors": [
                {"id": str(n.id), "type": n.node_type.value, "entity_ref": n.entity_ref}
                for n in subgraph.nodes
                if n.id != node.id
            ],
            "relationships": [
                {"from": str(e.from_node_id), "to": str(e.to_node_id), "type": e.edge_type.value} for e in subgraph.edges
            ],
        }

    data = {
        "node_count": snapshot.node_count,
        "edge_count": snapshot.edge_count,
        "nodes_by_type": {k.value: v for k, v in snapshot.nodes_by_type.items()},
        "edges_by_type": {k.value: v for k, v in snapshot.edges_by_type.items()},
        "preview_entity": preview_entity,
    }
    return envelope(_store("kg-preview", data))
