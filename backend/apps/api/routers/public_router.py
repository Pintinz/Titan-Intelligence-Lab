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
from datetime import datetime, timedelta, timezone

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
from apps.api.rate_limit import rate_limit_by_ip
from modules.ingestion.domain.value_objects import SyncStatus
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.predictions.domain.value_objects import PredictionStatus
from modules.sports.domain.value_objects import (
    CompetitionId,
    CountryId,
    FixtureId,
    PlayerId,
    SportId,
    TeamId,
    VenueId,
)
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyCountryRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyVenueRepository,
)

router = APIRouter(
    prefix="/api/v1/public",
    tags=["public"],
    # These are the only endpoints in the service reachable without a session (see module
    # docstring) — the in-process TTL cache above softens repeated *identical* requests, but does
    # nothing against a scripted client varying `limit` or simply hammering the endpoint. IP-based
    # throttling is the only identity available pre-auth (Production Readiness Audit §6: this
    # router previously had no rate limiting of any kind).
    dependencies=[Depends(rate_limit_by_ip("public_api", limit=120, window_seconds=60))],
)


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
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    registry = get_sport_plugin_registry()
    plugins = registry.all()

    sports_repo = SqlAlchemySportRepository(session=session)
    competitions_repo = SqlAlchemyCompetitionRepository(session=session)
    fixtures_repo = SqlAlchemyFixtureRepository(session=session)

    sports_data: list[dict] = []
    total_competitions = 0
    total_live = 0
    total_today = 0
    total_completed = 0

    for plugin in plugins:
        sport = await sports_repo.get_by_code(plugin.code)
        competitions = await competitions_repo.list_by_sport(sport.id) if sport is not None else []
        # One grouped aggregate query for this sport's fixture counts, not a season-by-season
        # walk that fetches every fixture row just to count them in Python (see
        # FixtureRepositoryPort.count_by_sport docstring) — this was the dominant cost of this
        # endpoint on a real-scale, networked-Postgres dataset (~20s → sub-second).
        counts = await fixtures_repo.count_by_sport(sport.id, day_start, day_end) if sport is not None else {
            "live": 0,
            "completed": 0,
            "today": 0,
        }
        live_count = counts["live"]
        today_count = counts["today"]
        completed_count = counts["completed"]
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
    (top positive/negative feature labels only, never raw SHAP weights or internal ids). Correct
    Score is excluded from this carousel specifically (see `_HERO_EXCLUDED_MARKETS`) — it still
    generates and displays normally everywhere else in the product."""
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

    # Correct Score is real evidence-based intelligence, not a weaker prediction — but an exact
    # scoreline's own probability reads low next to a Match Winner/Over-Under pick even at real
    # high confidence (e.g. a genuine 57% confidence read at ~10% probability), which lands as "the
    # platform isn't sure" to a first-time visitor skimming the hero. Excluded from this carousel
    # only — Correct Score still generates and displays normally everywhere else (Prediction
    # Laboratory, Match Review, Team/Competition Intelligence).
    _HERO_EXCLUDED_MARKETS = {"football.correct_score"}

    market_cache: dict[str, object] = {}
    picks = []
    for prediction in published:
        market_key = str(prediction.market_id)
        if market_key not in market_cache:
            market_cache[market_key] = await market_service.markets.get(prediction.market_id)
        market = market_cache[market_key]
        if market is not None and market.market_key not in _HERO_EXCLUDED_MARKETS:
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

    # A landing-page hero showcasing a prediction for a match that already finished last week reads
    # as stale, not "sports intelligence in action" — resolve every diversified candidate's fixture
    # up front and prefer LIVE, then a genuinely-upcoming SCHEDULED fixture, over anything else
    # (completed/postponed/cancelled), confidence only breaking ties within the same tier. Never
    # fabricates a live/upcoming match that doesn't exist: if no published prediction covers one,
    # the ranking falls back to the real highest-confidence pick regardless of timing, same as
    # before this change.
    #
    # A fixture's own `status` field is not fully trustworthy on its own — the sync job that
    # flips SCHEDULED -> COMPLETED after real kickoff can lag or gap (verified live: 9 of 380
    # locally-seeded "scheduled" fixtures already have a past `scheduled_at`, HUL vs MUN among
    # them, 2026-08-22 with "now" at 2026-08-23). A "scheduled" fixture whose kickoff has already
    # passed is trusted for neither tier — it might be live, finished, or genuinely delayed, and
    # showing it as "upcoming" would misrepresent something that may already be over.
    now = _now()

    def _is_reliably_upcoming(fixture) -> bool:
        scheduled_at = fixture.scheduled_at
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        return scheduled_at > now

    def _timing_tier(fixture) -> int:
        if fixture.status.value == "live":
            return 0
        if fixture.status.value == "scheduled" and _is_reliably_upcoming(fixture):
            return 1
        return 2

    with_fixtures: list[tuple] = []
    for prediction, market in picks:
        try:
            fixture = await fixtures_repo.get(FixtureId(uuid.UUID(prediction.subject_ref)))
        except ValueError:
            fixture = None
        if fixture is None:
            continue
        with_fixtures.append((prediction, market, fixture))
    with_fixtures.sort(key=lambda pmf: (_timing_tier(pmf[2]), -pmf[0].confidence.composite))

    data: list[dict] = []
    for prediction, market, fixture in with_fixtures:
        if len(data) >= limit:
            break
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
                "probability_distribution": dict(prediction.probability_distribution or {}),
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


async def _resolve_node_label(session: AsyncSession, node_type: str, entity_ref: str) -> str | None:
    """Best-effort real display name for a KG node, resolved from the same relational tables
    entity_reconciliation writes — `KGNode.entity_ref` is that row's own id, never a slug, so
    there's nothing to resolve without this lookup. Returns None (never a guess) for a ref that
    doesn't parse as a UUID or a row that no longer exists; the caller falls back to the honest
    `node_type` label in that case, same as before this resolver existed."""
    try:
        ref_id = uuid.UUID(entity_ref)
    except ValueError:
        return None

    try:
        if node_type == "team":
            team = await SqlAlchemyTeamRepository(session=session).get(TeamId(ref_id))
            return team.short_name if team else None
        if node_type == "player":
            player = await SqlAlchemyPlayerRepository(session=session).get(PlayerId(ref_id))
            return player.name if player else None
        if node_type == "sport":
            sport = await SqlAlchemySportRepository(session=session).get(SportId(ref_id))
            return sport.name if sport else None
        if node_type == "competition":
            competition = await SqlAlchemyCompetitionRepository(session=session).get(CompetitionId(ref_id))
            return competition.name if competition else None
        if node_type == "country":
            country = await SqlAlchemyCountryRepository(session=session).get(CountryId(ref_id))
            return country.name if country else None
        if node_type == "venue":
            venue = await SqlAlchemyVenueRepository(session=session).get(VenueId(ref_id))
            return venue.name if venue else None
        if node_type == "match":
            fixture = await SqlAlchemyFixtureRepository(session=session).get(FixtureId(ref_id))
            if fixture is None:
                return None
            teams_repo = SqlAlchemyTeamRepository(session=session)
            home, away = await teams_repo.get(fixture.home_team_id), await teams_repo.get(fixture.away_team_id)
            home_name = home.short_name if home else "TBD"
            away_name = away.short_name if away else "TBD"
            return f"{home_name} vs {away_name}"
    except Exception:
        # A lookup failing (bad data, unexpected id shape) degrades to the honest node_type
        # label — it must never surface as a 500 on a public, cached, best-effort preview.
        return None
    return None


@router.get("/knowledge-graph-preview")
async def knowledge_graph_preview(session: AsyncSession = Depends(get_session)):
    """Real graph scale (node/edge counts by type) plus a real neighborhood around one real,
    genuinely high-connectivity team node — never a fabricated relationship. Each node also
    carries a best-effort real `label` resolved from the relational table its `entity_ref`
    points at (team short name, "Home vs Away" for a match, etc.) — `label` is None, never a
    guess, for a node type/ref this resolver can't look up; the frontend falls back to the
    honest node_type in that case."""
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
        neighbor_nodes = [n for n in subgraph.nodes if n.id != node.id]

        center_label = await _resolve_node_label(session, node.node_type.value, node.entity_ref)
        neighbor_labels = [await _resolve_node_label(session, n.node_type.value, n.entity_ref) for n in neighbor_nodes]

        preview_entity = {
            "node": {"id": str(node.id), "type": node.node_type.value, "entity_ref": node.entity_ref, "label": center_label},
            "connection_count": degree,
            "neighbors": [
                {"id": str(n.id), "type": n.node_type.value, "entity_ref": n.entity_ref, "label": label}
                for n, label in zip(neighbor_nodes, neighbor_labels)
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
