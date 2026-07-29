"""Dead Letter Queue (docs/roadmap.md Milestone 5 "Background Processing: Dead Letter
Queue"). A failed task, once its Celery retries are exhausted, gets recorded here for
operator inspection rather than silently vanishing.

A Redis list rather than a real Celery queue: this is a record of *permanently failed* work for
humans to review (docs/roadmap.md "Job Monitoring"), not more work for a worker to consume —
using the same broker as a second queue would risk a worker picking it up and retrying
already-exhausted tasks.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from redis import Redis as SyncRedis

from modules.features.infrastructure.online.redis_feature_store import get_redis_settings

DEAD_LETTER_KEY = "dlq:sync_tasks"
DEAD_LETTER_MAX_LENGTH = 1000


def _client() -> SyncRedis:
    # Celery signal handlers run synchronously inside the worker process — a sync Redis client
    # is correct here, not `redis.asyncio` (used everywhere else in this codebase for FastAPI's
    # async request path).
    return SyncRedis.from_url(get_redis_settings().url, decode_responses=True)


def record_dead_letter(
    task_name: str, task_id: str, args: list, kwargs: dict, error: str,
    now: datetime | None = None, client: SyncRedis | None = None,
) -> None:
    entry = {
        "task_name": task_name, "task_id": task_id, "args": args, "kwargs": kwargs, "error": error,
        "failed_at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    redis_client = client or _client()
    redis_client.lpush(DEAD_LETTER_KEY, json.dumps(entry))
    redis_client.ltrim(DEAD_LETTER_KEY, 0, DEAD_LETTER_MAX_LENGTH - 1)


def list_dead_letters(limit: int = 50, client: SyncRedis | None = None) -> list[dict[str, Any]]:
    redis_client = client or _client()
    raw_entries = redis_client.lrange(DEAD_LETTER_KEY, 0, limit - 1)
    return [json.loads(raw) for raw in raw_entries]
