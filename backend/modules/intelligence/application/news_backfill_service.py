"""Milestone 12 — Controlled BACKFILL entry point for TitanIQ's real RSS news pipeline.

Purpose: allow a bounded, explicitly-approved catch-up sync of historical news for a single
source, reusing every existing piece of the real pipeline (`NewsIngestionService.sync_source`,
its `since_floor` semantics, deduplication, checkpointing, the Milestone 10 relevance pre-filter,
`IntelligenceEnrichmentOrchestrator.enrich_article`, and `news_provenance.classify_news_availability`)
— NOT a second ingestion pipeline.

**The provenance guarantee this service relies on, not reimplements**: `classify_news_availability`
(Milestone 9) already returns `UNKNOWN_AVAILABILITY_TIME` for any trigger other than
`SyncTrigger.LIVE_SCHEDULED` — this was true before this milestone and needed zero changes here.
`SyncTrigger.BACKFILL` (reserved since Milestone 5/10, never previously used by any real code
path) simply flows through `enrich_article(trigger=SyncTrigger.BACKFILL)` into that same existing
check. A BACKFILL-triggered sync can therefore *never* manufacture `VERIFIED_PRE_MATCH` — not
because this service adds a special case for it, but because only `LIVE_SCHEDULED` ever could,
and BACKFILL is not that. The trigger identifies *why* a sync happened, never *proof that
information was available before kickoff* — see `docs/milestone12_verification_report.md` for the
full reasoning and the tests that verify it.

Dry-run (spec §5) is the default and primary verification mode: `plan()` validates the request and
computes the bounded window with zero side effects (no provider call, no persistence, no
checkpoint mutation), and `run()` with `dry_run=True` returns that plan as a summary without going
any further. A real (non-dry-run) run additionally requires `NEWS_BACKFILL_ENABLED=true`
(`news_backfill_config.py`, defaults `False`) — refused otherwise, with the refusal itself
recorded, not silently downgraded to a dry-run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from modules.intelligence.application.intelligence_enrichment_orchestrator import IntelligenceEnrichmentOrchestrator
from modules.intelligence.application.news_backfill_config import (
    NEWS_BACKFILL_ENABLED,
    NEWS_BACKFILL_FIXTURE_WINDOW_HOURS,
    NEWS_BACKFILL_MAX_ARTICLES_PER_RUN,
    NEWS_BACKFILL_MAX_LOOKBACK_DAYS,
)
from modules.intelligence.application.news_ingestion_service import NewsIngestionService
from modules.intelligence.application.news_relevance_filter import NewsRelevanceFilter, build_fixture_relevance_vocabulary
from modules.intelligence.domain.entities import NewsArticle
from modules.intelligence.domain.value_objects import NewsSourceId, SyncStatus, SyncTrigger
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort
from modules.sports.domain.value_objects import SeasonId
from modules.sports.ports.repositories import FixtureRepositoryPort, PlayerRepositoryPort, TeamRepositoryPort


class BackfillValidationError(ValueError):
    """A malformed or unsafe backfill request — invalid range, future timestamp, unknown source.
    Raised before any provider call or persistence; the API layer maps this to HTTP 422."""


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — same duplicated
    helper used throughout this codebase's ingestion/intelligence modules."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass(frozen=True)
class BackfillRequest:
    """Every bound is explicit and, together with the service's own hard configuration ceilings,
    prevents the "unbounded historical ingestion" failure mode spec §4 forbids. ``dry_run``
    defaults ``True`` — a caller must deliberately opt into a real run, not the other way round."""

    source_id: NewsSourceId
    season_id: SeasonId
    since: datetime
    until: datetime | None = None
    max_articles: int | None = None
    dry_run: bool = True


@dataclass(frozen=True)
class BackfillPlan:
    """Side-effect-free description of what a request would do — computed identically for a
    dry-run and a real run, so dry-run's report is never a different code path from what a real
    run actually uses (spec §5: "if the existing architecture does not support dry-run directly,
    implement the minimum safe mechanism required" — this is that mechanism: the same planning
    step, with the real run simply choosing to act on it)."""

    source_id: NewsSourceId
    source_name: str
    requested_since: datetime
    requested_until: datetime | None
    effective_since: datetime
    effective_until: datetime
    max_articles: int
    window_clamped: bool


@dataclass
class BackfillSummary:
    """JSON-serializable observability, same posture as `ScheduledNewsSyncSummary` (Milestone 10)
    — one row per backfill attempt, dry-run or real."""

    dry_run: bool
    plan: BackfillPlan
    sync_run_id: str | None = None
    articles_seen: int = 0
    articles_deduplicated: int = 0
    articles_rejected: int = 0
    articles_within_window: int = 0
    articles_outside_window: int = 0
    articles_relevant: int = 0
    articles_skipped_by_relevance: int = 0
    articles_sent_to_gemini: int = 0
    articles_enriched: int = 0
    enrichment_failures: int = 0
    # BACKFILL can never produce VERIFIED_PRE_MATCH (news_provenance.classify_news_availability's
    # own trigger check) — this stays 0 by construction on every real path through this service,
    # asserted directly in tests rather than merely assumed.
    provenance_verified: int = 0
    provenance_unknown: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class NewsBackfillService:
    news_ingestion: NewsIngestionService
    enrichment: IntelligenceEnrichmentOrchestrator
    fixtures: FixtureRepositoryPort
    teams: TeamRepositoryPort
    players: PlayerRepositoryPort
    kg_nodes: KGNodeRepositoryPort

    async def plan(self, request: BackfillRequest, now: datetime) -> BackfillPlan:
        """Validates the request and computes its bounded window — no provider call, no
        persistence. Callable standalone (e.g. an admin form's live preview) as well as
        internally by `run`."""
        source = await self.news_ingestion.sources.get(request.source_id)
        if source is None:
            raise BackfillValidationError(f"Unknown news source: {request.source_id}")

        since = _ensure_aware(request.since, now)
        until = _ensure_aware(request.until, now) if request.until is not None else None

        if until is not None and until < since:
            raise BackfillValidationError("`until` cannot be earlier than `since`")
        if since > now:
            raise BackfillValidationError("`since` cannot be in the future")
        if until is not None and until > now:
            raise BackfillValidationError("`until` cannot be in the future")

        hard_floor = now - timedelta(days=NEWS_BACKFILL_MAX_LOOKBACK_DAYS)
        effective_since = max(since, hard_floor)
        window_clamped = effective_since > since
        effective_until = until if until is not None else now

        requested_max = (
            request.max_articles if request.max_articles is not None else NEWS_BACKFILL_MAX_ARTICLES_PER_RUN
        )
        max_articles = max(0, min(requested_max, NEWS_BACKFILL_MAX_ARTICLES_PER_RUN))

        return BackfillPlan(
            source_id=request.source_id, source_name=source.name,
            requested_since=since, requested_until=until,
            effective_since=effective_since, effective_until=effective_until,
            max_articles=max_articles, window_clamped=window_clamped,
        )

    async def run(self, request: BackfillRequest, now: datetime) -> BackfillSummary:
        computed_plan = await self.plan(request, now)
        summary = BackfillSummary(dry_run=request.dry_run, plan=computed_plan)

        if request.dry_run:
            # Dry-run (spec §5, the primary verification mode): validated + planned above,
            # nothing else runs — no provider call, no persistence, no checkpoint mutation, no
            # Gemini call.
            return summary

        if not NEWS_BACKFILL_ENABLED:
            summary.errors.append(
                "NEWS_BACKFILL_ENABLED is false — a real (non-dry-run) backfill was requested but "
                "refused. Set TITANIQ_NEWS_BACKFILL_ENABLED=true to allow real execution."
            )
            return summary

        vocabulary = await build_fixture_relevance_vocabulary(
            fixtures=self.fixtures, teams=self.teams, players=self.players, kg_nodes=self.kg_nodes,
            season_id=request.season_id, now=now, window_hours=NEWS_BACKFILL_FIXTURE_WINDOW_HOURS,
        )
        relevance = NewsRelevanceFilter(vocabulary=vocabulary)

        candidates: list[NewsArticle] = []

        async def on_article_created(article: NewsArticle) -> None:
            candidates.append(article)

        sync_run = await self.news_ingestion.sync_source(
            request.source_id, now, trigger=SyncTrigger.BACKFILL,
            on_article_created=on_article_created, since_floor=computed_plan.effective_since,
        )
        summary.sync_run_id = str(sync_run.id)
        if sync_run.status is SyncStatus.FAILED and sync_run.error_message:
            summary.errors.append(f"source {sync_run.channel_key}: {sync_run.error_message}")
        summary.articles_seen = sync_run.items_fetched
        summary.articles_deduplicated = sync_run.items_duplicate
        summary.articles_rejected = sync_run.items_rejected

        # `sync_source`'s `since_floor` already bounds the provider's *fetch* request from below;
        # RSS feeds have no query-time upper bound to ask for (a feed simply returns whatever it
        # currently has), so `until` is enforced here, post-fetch, before any downstream
        # processing — an article outside the requested window is never relevance-checked, never
        # sent to Gemini, never reaches provenance/Feature Store processing, even though
        # `sync_source` (reused as-is, never duplicated) has already persisted the raw row, same
        # as every other trigger's ingestion behavior.
        within_window: list[NewsArticle] = []
        for article in candidates:
            published = _ensure_aware(article.published_at, now)
            if published < computed_plan.effective_since or published > computed_plan.effective_until:
                summary.articles_outside_window += 1
                continue
            within_window.append(article)
        summary.articles_within_window = len(within_window)

        relevant: list[NewsArticle] = []
        for article in within_window:
            if relevance.is_relevant(article.title, article.raw_text):
                relevant.append(article)
            else:
                summary.articles_skipped_by_relevance += 1
        summary.articles_relevant = len(relevant)

        # Deterministic ordering + hard truncation BEFORE any Gemini call (same discipline as
        # Milestone 10's scheduled sync, spec §6/§12): most-recent first, article id as a stable
        # tiebreaker.
        relevant.sort(key=lambda a: (a.published_at, str(a.id)), reverse=True)
        budgeted = relevant[: computed_plan.max_articles]
        summary.articles_sent_to_gemini = len(budgeted)

        for article in budgeted:
            try:
                scores = await self.enrichment.enrich_article(
                    article, now, trigger=SyncTrigger.BACKFILL, sync_run_id=summary.sync_run_id,
                )
            except Exception as exc:  # Gemini/entity-resolution fault — isolated, never fabricated
                summary.enrichment_failures += 1
                summary.errors.append(f"article {article.id}: {exc}")
                continue
            summary.articles_enriched += 1
            # Every event extracted on this path carries trigger=BACKFILL —
            # classify_news_availability's own trigger check (unchanged by this milestone) makes
            # UNKNOWN_AVAILABILITY_TIME the only possible outcome; provenance_verified stays 0 by
            # construction, never assumed.
            summary.provenance_unknown += len(scores)

        return summary
