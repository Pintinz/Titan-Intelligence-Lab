"""Deterministic mock for `CommunityProviderPort` — one adapter class serves any platform
(Reddit, X, YouTube, official fan communities), since the mock's job is fixed test data, not
platform-specific behavior. A real adapter per platform (each with its own auth/rate-limit
shape) is future work once live credentials exist (docs/decisions.md ADR-008)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.intelligence.domain.value_objects import CommunityPlatform
from modules.intelligence.ports.community_provider import RawCommunityPostRecord


@dataclass
class MockCommunityProvider:
    platform: CommunityPlatform
    provider_key: str = "mock_community"
    fixed_posts: tuple[RawCommunityPostRecord, ...] = field(default_factory=tuple)

    async def fetch_posts(
        self, topic: str, since: datetime | None = None, cursor: str | None = None
    ) -> list[RawCommunityPostRecord]:
        if not self.fixed_posts:
            return []
        if since is None:
            return list(self.fixed_posts)
        return [p for p in self.fixed_posts if p.posted_at > since]
