"""Feature flag evaluation — gates incomplete sports/markets/subsystems from general
availability (docs/admin_center.md §1, docs/roadmap.md Milestone 4). Percentage rollout is
deterministic (hash of flag key + context id), not randomized, so the same context always gets
the same answer for a given flag/percentage — no flapping between requests, and it's reproducible
in tests without mocking randomness."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.admin.domain.entities import FeatureFlag
from modules.admin.domain.value_objects import FlagId
from modules.admin.ports.repositories import FeatureFlagRepositoryPort


class FlagAlreadyExistsError(ValueError):
    pass


class FlagNotFoundError(KeyError):
    pass


def _bucket(key: str, context_id: str) -> int:
    digest = hashlib.sha256(f"{key}:{context_id}".encode()).hexdigest()
    return int(digest, 16) % 100


@dataclass
class FeatureFlagService:
    flags: FeatureFlagRepositoryPort

    async def create_flag(
        self,
        key: str,
        name: str,
        description: str,
        *,
        enabled: bool = False,
        rollout_percentage: int = 100,
    ) -> FeatureFlag:
        if await self.flags.get_by_key(key) is not None:
            raise FlagAlreadyExistsError(f"flag '{key}' already exists")
        flag = FeatureFlag(
            id=FlagId(uuid4()), key=key, name=name, description=description,
            enabled=enabled, rollout_percentage=rollout_percentage,
        )
        return await self.flags.upsert(flag)

    async def _require(self, key: str) -> FeatureFlag:
        flag = await self.flags.get_by_key(key)
        if flag is None:
            raise FlagNotFoundError(key)
        return flag

    async def enable(self, key: str, now: datetime) -> FeatureFlag:
        flag = await self._require(key)
        flag.enabled = True
        flag.updated_at = now
        return await self.flags.upsert(flag)

    async def disable(self, key: str, now: datetime) -> FeatureFlag:
        flag = await self._require(key)
        flag.enabled = False
        flag.updated_at = now
        return await self.flags.upsert(flag)

    async def set_rollout(self, key: str, percentage: int, now: datetime) -> FeatureFlag:
        if not 0 <= percentage <= 100:
            raise ValueError("rollout_percentage must be between 0 and 100")
        flag = await self._require(key)
        flag.rollout_percentage = percentage
        flag.updated_at = now
        return await self.flags.upsert(flag)

    async def is_enabled(self, key: str, context_id: str | None = None) -> bool:
        """Unknown flag -> False (safe default: an unconfigured gate stays closed, never opens
        by accident). ``context_id`` is required for a percentage < 100 — without one to bucket
        against there's no deterministic way to decide, so it's treated as not enabled rather
        than falling back to randomness."""
        flag = await self.flags.get_by_key(key)
        if flag is None or not flag.enabled:
            return False
        if flag.rollout_percentage >= 100:
            return True
        if flag.rollout_percentage <= 0:
            return False
        if context_id is None:
            return False
        return _bucket(flag.key, context_id) < flag.rollout_percentage

    async def list_all(self) -> list[FeatureFlag]:
        return await self.flags.list_all()
