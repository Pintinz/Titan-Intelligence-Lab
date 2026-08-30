"""Intelligence Monitoring (Milestone 8 "MONITORING": "Implement monitoring for: Ingestion
Rate, Article Count, Duplicate Rate, Extraction Accuracy, Processing Time, Gemini Usage,
Provider Health, Source Reliability, Community Activity.").

Mirrors `modules.knowledge_graph.application.graph_monitoring_service`'s shape (Milestone 7):
an explicit opt-in `IntelligenceMetricsRecorder` for in-process timing/usage counters (nothing
wraps calls automatically — callers record explicitly, same posture as `GraphMetricsRecorder`),
composed with the repositories already built for a live snapshot. Provider Health is derived
from `IntelligenceSyncRun` history (recent success rate, consecutive-failure streak per channel)
rather than duplicating `modules.admin`'s `HealthIntelligenceEngine` for a second provider
category — the sync run already records everything needed to answer "is this source/platform
healthy right now."
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from modules.intelligence.domain.value_objects import IntelligenceChannelType, SyncStatus
from modules.intelligence.ports.repositories import (
    CommunityPostRepositoryPort,
    IntelligenceSyncRunRepositoryPort,
    NewsArticleRepositoryPort,
    SourceReliabilityRepositoryPort,
)


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass
class IntelligenceMetricsRecorder:
    ingestion_run_count: int = 0
    ingestion_total_seconds: float = 0.0
    gemini_call_count: int = 0
    # News Intelligence audit (2026-08-27) — a distinct counter for ClaudeAdapter's own real
    # calls, kept separate from gemini_call_count rather than folded into it: the two are
    # different providers with different cost/quota profiles, and merging them would make this
    # dashboard's one number silently mean "either provider," misleading whoever reads it during
    # exactly the kind of quota investigation that motivated adding a second provider at all.
    claude_call_count: int = 0
    # 2026-08-30 — OpenAI promoted to real_adapter (primary); same "distinct counter, never
    # folded into another provider's" reasoning as claude_call_count's own comment above, now
    # more load-bearing than ever: this number is exactly what would have shown the Gemini quota
    # exhaustion coming, had it existed before that incident.
    openai_call_count: int = 0
    extraction_correct_count: int = 0
    extraction_total_count: int = 0

    def record_ingestion(self, duration_seconds: float) -> None:
        self.ingestion_run_count += 1
        self.ingestion_total_seconds += duration_seconds

    def record_gemini_call(self, count: int = 1) -> None:
        self.gemini_call_count += count

    def record_claude_call(self, count: int = 1) -> None:
        self.claude_call_count += count

    def record_openai_call(self, count: int = 1) -> None:
        self.openai_call_count += count

    def record_extraction_outcome(self, was_correct: bool) -> None:
        self.extraction_total_count += 1
        if was_correct:
            self.extraction_correct_count += 1

    @contextmanager
    def time_ingestion(self):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record_ingestion(time.perf_counter() - started)

    @property
    def avg_processing_seconds(self) -> float:
        return self.ingestion_total_seconds / self.ingestion_run_count if self.ingestion_run_count else 0.0

    @property
    def extraction_accuracy(self) -> float | None:
        """Proxy metric: fraction of extractions later confirmed correct by whatever
        verification signal the caller has. ``None`` when nothing has been checked yet
        (undefined, not zero) — same posture as Milestone 7's Entity Resolution Accuracy proxy."""
        if not self.extraction_total_count:
            return None
        return self.extraction_correct_count / self.extraction_total_count


@dataclass(frozen=True)
class IntelligenceMetricsSnapshot:
    article_count: int
    news_ingestion_runs_recent: int
    news_duplicate_rate: float
    avg_processing_seconds: float
    gemini_call_count: int
    claude_call_count: int
    openai_call_count: int
    extraction_accuracy: float | None
    average_source_reliability: float | None
    community_post_count: int
    provider_health: dict


@dataclass
class IntelligenceMonitoringService:
    sync_runs: IntelligenceSyncRunRepositoryPort
    articles: NewsArticleRepositoryPort
    community_posts: CommunityPostRepositoryPort
    source_reliability: SourceReliabilityRepositoryPort
    recorder: IntelligenceMetricsRecorder = field(default_factory=IntelligenceMetricsRecorder)

    async def ingestion_rate(
        self, channel_type: IntelligenceChannelType, window: timedelta, now: datetime, limit: int = 200
    ) -> float:
        """Sync runs per hour over the recent window, for one channel type."""
        runs = await self.sync_runs.list_recent(channel_type=channel_type, limit=limit)
        cutoff = now - window
        recent = [r for r in runs if _ensure_aware(r.started_at, now) >= cutoff]
        hours = window.total_seconds() / 3600
        return len(recent) / hours if hours else 0.0

    async def duplicate_rate(self, channel_type: IntelligenceChannelType, limit: int = 200) -> float:
        runs = await self.sync_runs.list_recent(channel_type=channel_type, limit=limit)
        total_fetched = sum(r.items_fetched for r in runs)
        total_duplicate = sum(r.items_duplicate for r in runs)
        return total_duplicate / total_fetched if total_fetched else 0.0

    async def provider_health(self, channel_type: IntelligenceChannelType, limit: int = 200) -> dict:
        """Per-channel-key health: recent success rate and current consecutive-failure streak
        (counted from the most recent run backwards, stopping at the first non-failure)."""
        runs = await self.sync_runs.list_recent(channel_type=channel_type, limit=limit)
        by_channel: dict[str, list] = {}
        for run in runs:
            by_channel.setdefault(run.channel_key, []).append(run)

        health: dict[str, dict] = {}
        for channel_key, channel_runs in by_channel.items():
            ordered = sorted(channel_runs, key=lambda r: r.started_at, reverse=True)
            succeeded = sum(1 for r in ordered if r.status in (SyncStatus.SUCCEEDED, SyncStatus.PARTIAL))
            consecutive_failures = 0
            for run in ordered:
                if run.status is SyncStatus.FAILED:
                    consecutive_failures += 1
                else:
                    break
            health[channel_key] = {
                "success_rate": succeeded / len(ordered) if ordered else 0.0,
                "consecutive_failures": consecutive_failures,
            }
        return health

    async def average_source_reliability(self) -> float | None:
        scores = await self.source_reliability.list_all()
        if not scores:
            return None
        return sum(s.reliability_score for s in scores) / len(scores)

    async def snapshot(self, now: datetime) -> IntelligenceMetricsSnapshot:
        article_count = await self.articles.count_all()
        posts = await self.community_posts.list_recent(limit=5000)
        news_runs = await self.sync_runs.list_recent(channel_type=IntelligenceChannelType.NEWS, limit=200)
        return IntelligenceMetricsSnapshot(
            article_count=article_count,
            news_ingestion_runs_recent=len(news_runs),
            news_duplicate_rate=await self.duplicate_rate(IntelligenceChannelType.NEWS),
            avg_processing_seconds=self.recorder.avg_processing_seconds,
            gemini_call_count=self.recorder.gemini_call_count,
            claude_call_count=self.recorder.claude_call_count,
            openai_call_count=self.recorder.openai_call_count,
            extraction_accuracy=self.recorder.extraction_accuracy,
            average_source_reliability=await self.average_source_reliability(),
            community_post_count=len(posts),
            provider_health=await self.provider_health(IntelligenceChannelType.NEWS),
        )
