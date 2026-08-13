"""News Ingestion — multi-source, incremental, deduplicated ingestion of news articles
(Milestone 8 "NEWS INGESTION": Incremental synchronization, Deduplication, Retry, Versioning,
Scheduling, Caching, Monitoring, Provider abstraction).

Mirrors the shape of `modules.ingestion.application.sync_orchestrator` (incremental sync via a
checkpoint, one `IntelligenceSyncRun` record per execution, retry via consecutive-failure
tracking rather than an internal retry loop — a Celery task or caller re-invokes `sync_source`
with `trigger=RETRY`) without importing it: News Ingestion is its own pipeline, not sports data,
per Milestone 8's "maintain complete separation" instruction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from modules.intelligence.domain.entities import IntelligenceSyncCheckpoint, IntelligenceSyncRun, NewsArticle, NewsSource
from modules.intelligence.domain.value_objects import (
    IntelligenceChannelType,
    IntelligenceSyncRunId,
    NewsArticleId,
    NewsSourceId,
    SyncStatus,
    SyncTrigger,
)
from modules.intelligence.ports.news_provider import NewsProviderPort, RawArticleRecord
from modules.intelligence.ports.repositories import (
    IntelligenceSyncCheckpointRepositoryPort,
    IntelligenceSyncRunRepositoryPort,
    NewsArticleRepositoryPort,
    NewsSourceRepositoryPort,
)


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — the checkpoint's
    ``last_synced_at`` needs this before being handed to a provider adapter alongside an
    aware ``published_at`` for comparison."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


def content_hash(title: str, body: str) -> str:
    """Deduplication key: same normalized story, regardless of source or re-fetch, hashes
    identically. Whitespace-collapsed + lowercased so trivial formatting differences between a
    republished wire story and its original don't produce distinct hashes."""
    normalized = " ".join(f"{title} {body}".lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class NewsIngestionService:
    sources: NewsSourceRepositoryPort
    articles: NewsArticleRepositoryPort
    checkpoints: IntelligenceSyncCheckpointRepositoryPort
    sync_runs: IntelligenceSyncRunRepositoryPort
    providers: dict[str, NewsProviderPort] = field(default_factory=dict)  # source_type.value -> adapter

    async def sync_source(
        self,
        source_id: NewsSourceId,
        now: datetime,
        trigger: SyncTrigger = SyncTrigger.SCHEDULED,
        on_article_created: Callable[[NewsArticle], Awaitable[object]] | None = None,
        since_floor: datetime | None = None,
    ) -> IntelligenceSyncRun:
        """``on_article_created`` (optional, additive) fires once per genuinely new article —
        never for a duplicate/rejected record — so a caller can chain real downstream work (event
        extraction, impact scoring, Feature Store enrichment) without this service needing to
        know anything about what happens after ingestion. Same shape as
        `TrainingPipelineService.train`'s ``on_checkpoint`` hook.

        ``since_floor`` (Milestone 10, optional, additive — default ``None`` preserves every
        existing caller's exact prior behavior): a lower bound on how far back a fetch may look,
        even on a fresh/empty checkpoint. Without it, a source with no prior checkpoint asks its
        provider for *everything* the feed currently returns, no time bound at all — fine for a
        one-off admin sync, but exactly the "scheduled ingestion becomes an unbounded historical
        backfill" failure mode Milestone 10 §9 forbids. When both a checkpoint and a floor are
        present, the later (more restrictive) of the two wins."""
        source = await self.sources.get(source_id)
        if source is None:
            raise ValueError(f"Unknown news source: {source_id}")

        channel_key = str(source_id)
        checkpoint = await self.checkpoints.get(
            IntelligenceChannelType.NEWS, channel_key
        ) or IntelligenceSyncCheckpoint(channel_type=IntelligenceChannelType.NEWS, channel_key=channel_key)
        run = await self.sync_runs.record(
            IntelligenceSyncRun(
                id=IntelligenceSyncRunId(uuid4()),
                channel_type=IntelligenceChannelType.NEWS,
                channel_key=channel_key,
                trigger=trigger,
                status=SyncStatus.RUNNING,
                started_at=now,
            )
        )

        provider = self._resolve_provider(source)
        since = checkpoint.last_synced_at
        if since is not None:
            since = _ensure_aware(since, now)
        if since_floor is not None:
            since = max(since, since_floor) if since is not None else since_floor
        try:
            records = await provider.fetch_articles(source.url, since=since, cursor=checkpoint.cursor)
        except Exception as exc:  # provider fault — retry-eligible, not a crash
            checkpoint.consecutive_failures += 1
            await self.checkpoints.upsert(checkpoint)
            run.mark_failed(now, str(exc))
            return await self.sync_runs.update(run)

        run.items_fetched = len(records)
        for record in records:
            outcome, article = await self._ingest_record(source.id, record, now)
            if outcome == "created":
                run.items_created += 1
                if on_article_created is not None and article is not None:
                    await on_article_created(article)
            elif outcome == "duplicate":
                run.items_duplicate += 1
            else:
                run.items_rejected += 1

        checkpoint.last_synced_at = now
        checkpoint.consecutive_failures = 0
        await self.checkpoints.upsert(checkpoint)
        run.mark_succeeded(now)
        return await self.sync_runs.update(run)

    async def sync_all_sources(
        self,
        now: datetime,
        trigger: SyncTrigger = SyncTrigger.SCHEDULED,
        on_article_created: Callable[[NewsArticle], Awaitable[object]] | None = None,
        since_floor: datetime | None = None,
    ) -> list[IntelligenceSyncRun]:
        """Milestone 10 — the missing "sync every registered source" entry point
        `sync_upcoming_structured_intelligence` already has for structured intelligence. Thin
        orchestration only: one `sync_source` call per source, in registration order. One
        source's failure is already isolated by `sync_source` itself (it catches the provider
        fault and returns a FAILED run rather than raising), so this loop never aborts partway
        through — every registered source gets its own attempt regardless of any other source's
        outcome."""
        runs: list[IntelligenceSyncRun] = []
        for source in await self.sources.list_all():
            runs.append(
                await self.sync_source(
                    source.id, now, trigger=trigger, on_article_created=on_article_created,
                    since_floor=since_floor,
                )
            )
        return runs

    async def _ingest_record(
        self, source_id: NewsSourceId, record: RawArticleRecord, now: datetime
    ) -> tuple[str, NewsArticle | None]:
        if not record.title.strip() or not record.body.strip():
            return "rejected", None

        digest = content_hash(record.title, record.body)
        if await self.articles.get_by_content_hash(digest) is not None:
            return "duplicate", None

        existing = await self.articles.get_by_url(record.url)
        article = NewsArticle(
            id=existing.id if existing else NewsArticleId(uuid4()),
            source_id=source_id,
            title=record.title,
            url=record.url,
            content_hash=digest,
            raw_text=record.body,
            published_at=record.published_at,
            fetched_at=now,
            version=(existing.version + 1) if existing else 1,
        )
        saved = await self.articles.upsert(article)
        return "created", saved

    def _resolve_provider(self, source: NewsSource) -> NewsProviderPort:
        provider = self.providers.get(source.source_type.value) or self.providers.get("default")
        if provider is None:
            raise ValueError(f"No news provider registered for source type '{source.source_type.value}'")
        return provider
