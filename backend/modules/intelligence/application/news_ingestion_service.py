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
        self, source_id: NewsSourceId, now: datetime, trigger: SyncTrigger = SyncTrigger.SCHEDULED
    ) -> IntelligenceSyncRun:
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
        try:
            records = await provider.fetch_articles(source.url, since=since, cursor=checkpoint.cursor)
        except Exception as exc:  # provider fault — retry-eligible, not a crash
            checkpoint.consecutive_failures += 1
            await self.checkpoints.upsert(checkpoint)
            run.mark_failed(now, str(exc))
            return await self.sync_runs.update(run)

        run.items_fetched = len(records)
        for record in records:
            outcome = await self._ingest_record(source.id, record, now)
            if outcome == "created":
                run.items_created += 1
            elif outcome == "duplicate":
                run.items_duplicate += 1
            else:
                run.items_rejected += 1

        checkpoint.last_synced_at = now
        checkpoint.consecutive_failures = 0
        await self.checkpoints.upsert(checkpoint)
        run.mark_succeeded(now)
        return await self.sync_runs.update(run)

    async def _ingest_record(self, source_id: NewsSourceId, record: RawArticleRecord, now: datetime) -> str:
        if not record.title.strip() or not record.body.strip():
            return "rejected"

        digest = content_hash(record.title, record.body)
        if await self.articles.get_by_content_hash(digest) is not None:
            return "duplicate"

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
        await self.articles.upsert(article)
        return "created"

    def _resolve_provider(self, source: NewsSource) -> NewsProviderPort:
        provider = self.providers.get(source.source_type.value) or self.providers.get("default")
        if provider is None:
            raise ValueError(f"No news provider registered for source type '{source.source_type.value}'")
        return provider
