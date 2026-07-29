"""Community Intelligence ingestion — spam filtering, bot detection, duplicate filtering,
source credibility, noise reduction (Milestone 8 "COMMUNITY INTELLIGENCE"). Community signal is
always a supporting confidence signal, never overriding verified facts — this service only ever
produces `CommunityPost` rows; nothing here writes to the Knowledge Graph or Feature Store.

Duplicate filtering here is intentionally scoped differently from `NewsIngestionService`'s
cross-time content-hash dedup: within one sync batch, identical-text posts (copy-paste spam
reposted under different accounts) are deduped via an in-memory hash set, plus the platform's
own external id is checked against persisted history. A tweet saying "yes!!" a thousand times
across a season is not a meaningful cross-time duplicate the way a republished news article is
— persisting a permanent content-hash index for every short community post would be
disproportionate to the actual problem this milestone needs solved.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from modules.intelligence.domain.entities import CommunityPost, IntelligenceSyncCheckpoint, IntelligenceSyncRun
from modules.intelligence.domain.value_objects import (
    CommunityPlatform,
    CommunityPostId,
    IntelligenceChannelType,
    IntelligenceSyncRunId,
    SyncStatus,
    SyncTrigger,
)
from modules.intelligence.ports.community_provider import CommunityProviderPort, RawCommunityPostRecord
from modules.intelligence.ports.repositories import (
    CommunityPostRepositoryPort,
    IntelligenceSyncCheckpointRepositoryPort,
    IntelligenceSyncRunRepositoryPort,
)

_SPAM_MARKERS = ("click here", "buy now", "free followers", "subscribe now", "bit.ly", "dm me for")
_BOT_USERNAME_PATTERN = re.compile(r".+\d{5,}$")  # e.g. "footballfan1234567" — many trailing digits


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


def is_spam(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in _SPAM_MARKERS):
        return True
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return True  # shouting-caps spam pattern
    return text.count("!") >= 4


def is_bot_author(author_ref: str) -> bool:
    """Heuristic only — a real bot-detection model is future scope. Catches the common
    auto-generated-handle pattern (many trailing digits), not sophisticated evasion."""
    return bool(_BOT_USERNAME_PATTERN.match(author_ref))


def is_noise(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 5:
        return True
    return not any(c.isalnum() for c in stripped)


def post_content_hash(platform: CommunityPlatform, text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(f"{platform.value}:{normalized}".encode("utf-8")).hexdigest()


@dataclass
class CommunityIngestionService:
    posts: CommunityPostRepositoryPort
    checkpoints: IntelligenceSyncCheckpointRepositoryPort
    sync_runs: IntelligenceSyncRunRepositoryPort
    providers: dict[str, CommunityProviderPort] = field(default_factory=dict)  # platform.value -> adapter

    async def sync_topic(
        self, platform: CommunityPlatform, topic: str, now: datetime, trigger: SyncTrigger = SyncTrigger.SCHEDULED
    ) -> IntelligenceSyncRun:
        channel_key = f"{platform.value}:{topic}"
        checkpoint = await self.checkpoints.get(
            IntelligenceChannelType.COMMUNITY, channel_key
        ) or IntelligenceSyncCheckpoint(channel_type=IntelligenceChannelType.COMMUNITY, channel_key=channel_key)
        run = await self.sync_runs.record(
            IntelligenceSyncRun(
                id=IntelligenceSyncRunId(uuid4()),
                channel_type=IntelligenceChannelType.COMMUNITY,
                channel_key=channel_key,
                trigger=trigger,
                status=SyncStatus.RUNNING,
                started_at=now,
            )
        )

        provider = self.providers.get(platform.value)
        if provider is None:
            raise ValueError(f"No community provider registered for platform '{platform.value}'")

        since = checkpoint.last_synced_at
        if since is not None:
            since = _ensure_aware(since, now)
        try:
            records = await provider.fetch_posts(topic, since=since, cursor=checkpoint.cursor)
        except Exception as exc:  # provider fault — retry-eligible, not a crash
            checkpoint.consecutive_failures += 1
            await self.checkpoints.upsert(checkpoint)
            run.mark_failed(now, str(exc))
            return await self.sync_runs.update(run)

        seen_hashes: set[str] = set()
        run.items_fetched = len(records)
        for record in records:
            outcome = await self._ingest_record(platform, record, now, seen_hashes)
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

    async def _ingest_record(
        self, platform: CommunityPlatform, record: RawCommunityPostRecord, now: datetime, seen_hashes: set[str]
    ) -> str:
        if is_noise(record.text) or is_spam(record.text) or is_bot_author(record.author_ref):
            return "rejected"

        digest = post_content_hash(platform, record.text)
        if digest in seen_hashes:
            return "duplicate"
        seen_hashes.add(digest)

        if await self.posts.get_by_external_id(platform, record.external_id) is not None:
            return "duplicate"

        post = CommunityPost(
            id=CommunityPostId(uuid4()),
            platform=platform,
            external_id=record.external_id,
            author_ref=record.author_ref,
            text=record.text,
            posted_at=record.posted_at,
            fetched_at=now,
            credibility_score=self._credibility(record),
        )
        await self.posts.upsert(post)
        return "created"

    def _credibility(self, record: RawCommunityPostRecord) -> float:
        """Source credibility heuristic — engagement is a real signal but bounded to [0.3, 1.0]
        so a single low-engagement post from a real account is never scored as untrustworthy as
        a bot post (already filtered separately), and no single viral post can claim perfect
        credibility on engagement alone."""
        return min(1.0, 0.3 + record.engagement_score * 0.7)
