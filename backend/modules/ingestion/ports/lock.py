"""Distributed lock port — prevents two sync runs for the same (sport, entity_kind, scope)
from racing each other (docs/roadmap.md Milestone 5 "Redis Integration: Distributed Locks").
"""

from __future__ import annotations

from typing import Protocol


class DistributedLockPort(Protocol):
    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        """Returns True if the lock was acquired, False if already held by someone else."""
        ...

    async def release(self, key: str) -> None: ...
