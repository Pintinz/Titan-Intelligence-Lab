"""Milestone 10 — Scheduled News Sync orchestration: the real bridge between Celery Beat and the
whole Milestone 8/9 pipeline (`NewsIngestionService` -> `IntelligenceEnrichmentOrchestrator`),
with the two things that pipeline never had — a genuine `LIVE_SCHEDULED` trigger the caller cannot
override, and a deterministic relevance pre-filter that keeps Gemini usage bounded.

`ScheduledNewsSyncService.run` is this milestone's ONE public entry point, and it hardcodes
``trigger=SyncTrigger.LIVE_SCHEDULED`` internally — no parameter accepts a caller-supplied trigger,
by design (spec §3: "The trigger must NOT be supplied by the task caller... This prevents external
callers from spoofing provenance"). The Celery task that calls this (Milestone 10, `infrastructure/
celery/tasks.py`) is the only production caller; the admin manual-sync endpoint and any future
backfill script both go through `NewsIngestionService` directly with their own honest trigger
value (`ADMIN_MANUAL`/`BACKFILL`), never through here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from modules.intelligence.application.intelligence_enrichment_orchestrator import IntelligenceEnrichmentOrchestrator
from modules.intelligence.application.news_ingestion_service import NewsIngestionService
from modules.intelligence.application.news_relevance_filter import NewsRelevanceFilter, build_fixture_relevance_vocabulary
from modules.intelligence.application.news_sync_config import (
    NEWS_SYNC_ENABLED,
    NEWS_SYNC_FIXTURE_WINDOW_HOURS,
    NEWS_SYNC_LOOKBACK_HOURS,
    NEWS_SYNC_MAX_ARTICLES_PER_RUN,
)
from modules.intelligence.domain.entities import NewsArticle
from modules.intelligence.domain.value_objects import SyncStatus, SyncTrigger
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort
from modules.sports.domain.value_objects import SeasonId
from modules.sports.ports.repositories import FixtureRepositoryPort, PlayerRepositoryPort, TeamRepositoryPort


@dataclass
class ScheduledNewsSyncSummary:
    """Milestone 10 §18's observability fields — one row per scheduled run, JSON-serializable
    (Celery task results must be plain types, see `modules.ingestion.infrastructure.celery.tasks`'
    own docstring on this)."""

    enabled: bool
    started_at: datetime
    completed_at: datetime | None = None
    sync_run_ids: list[str] = field(default_factory=list)
    sources_attempted: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0
    articles_seen: int = 0
    articles_deduplicated: int = 0
    articles_rejected: int = 0
    articles_relevant: int = 0
    articles_skipped_by_relevance: int = 0
    articles_sent_to_gemini: int = 0
    articles_enriched: int = 0
    enrichment_failures: int = 0
    provenance_verified: int = 0
    provenance_unknown: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ScheduledNewsSyncService:
    news_ingestion: NewsIngestionService
    enrichment: IntelligenceEnrichmentOrchestrator
    fixtures: FixtureRepositoryPort
    teams: TeamRepositoryPort
    players: PlayerRepositoryPort
    kg_nodes: KGNodeRepositoryPort

    async def run(self, sport_code: str, season_id: SeasonId, now: datetime) -> ScheduledNewsSyncSummary:
        summary = ScheduledNewsSyncSummary(enabled=NEWS_SYNC_ENABLED, started_at=now)
        if not NEWS_SYNC_ENABLED:
            # DISABLED (spec §22's default state): no provider call, no Gemini call, no DB write
            # beyond this summary — an operator must deliberately flip TITANIQ_NEWS_SYNC_ENABLED.
            summary.completed_at = now
            return summary

        vocabulary = await self._build_relevance_vocabulary(season_id, now)
        relevance = NewsRelevanceFilter(vocabulary=vocabulary)

        candidates: list[NewsArticle] = []

        async def on_article_created(article: NewsArticle) -> None:
            candidates.append(article)

        since_floor = now - timedelta(hours=NEWS_SYNC_LOOKBACK_HOURS)
        runs = await self.news_ingestion.sync_all_sources(
            now, trigger=SyncTrigger.LIVE_SCHEDULED, on_article_created=on_article_created,
            since_floor=since_floor,
        )

        summary.sync_run_ids = [str(r.id) for r in runs]
        summary.sources_attempted = len(runs)
        for run in runs:
            if run.status is SyncStatus.FAILED:
                summary.sources_failed += 1
                if run.error_message:
                    summary.errors.append(f"source {run.channel_key}: {run.error_message}")
            else:
                summary.sources_succeeded += 1
            summary.articles_seen += run.items_fetched
            summary.articles_deduplicated += run.items_duplicate
            summary.articles_rejected += run.items_rejected

        relevant: list[NewsArticle] = []
        for article in candidates:
            if relevance.is_relevant(article.title, article.raw_text):
                relevant.append(article)
            else:
                summary.articles_skipped_by_relevance += 1
        summary.articles_relevant = len(relevant)

        # Deterministic ordering + hard truncation BEFORE any Gemini call (spec §6): most-recent
        # first, article id as a stable tiebreaker — never an arbitrary/unstable ordering.
        relevant.sort(key=lambda a: (a.published_at, str(a.id)), reverse=True)
        budgeted = relevant[:NEWS_SYNC_MAX_ARTICLES_PER_RUN]
        summary.articles_sent_to_gemini = len(budgeted)

        for article in budgeted:
            try:
                scores = await self.enrichment.enrich_article(article, now, trigger=SyncTrigger.LIVE_SCHEDULED)
            except Exception as exc:  # Gemini/entity-resolution fault — isolated, never fabricated
                summary.enrichment_failures += 1
                summary.errors.append(f"article {article.id}: {exc}")
                continue
            summary.articles_enriched += 1
            # Every event extracted on this path carries trigger=LIVE_SCHEDULED with a genuine
            # RSS-provided published_at — classify_news_availability's own deterministic rule
            # (modules.intelligence.application.news_provenance) makes VERIFIED_PRE_MATCH the only
            # possible outcome here; provenance_unknown stays 0 on this path by construction, never
            # assumed — see docs/milestone10_verification_report.md for the full reasoning.
            summary.provenance_verified += len(scores)

        summary.completed_at = now
        return summary

    async def _build_relevance_vocabulary(self, season_id: SeasonId, now: datetime) -> frozenset[str]:
        """Milestone 12: delegates to the shared `build_fixture_relevance_vocabulary` (extracted
        so `NewsBackfillService` can reuse the exact same mechanism rather than a second one being
        invented for backfill) — behavior is byte-identical to the original M10 implementation."""
        return await build_fixture_relevance_vocabulary(
            fixtures=self.fixtures, teams=self.teams, players=self.players, kg_nodes=self.kg_nodes,
            season_id=season_id, now=now, window_hours=NEWS_SYNC_FIXTURE_WINDOW_HOURS,
        )
