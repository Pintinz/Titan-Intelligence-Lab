"""Community platform provider gateway port (Milestone 8, same Provider Adapter Pattern as
`news_provider.py`). ``engagement_score`` is a normalized (0-1) upvote/like/view signal the
provider itself computes from platform-native metrics — used by `CommunityIngestionService`'s
credibility heuristics, not a prediction input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from modules.intelligence.domain.value_objects import CommunityPlatform


@dataclass(frozen=True)
class RawCommunityPostRecord:
    external_id: str
    author_ref: str
    text: str
    posted_at: datetime
    engagement_score: float = 0.0


class CommunityProviderPort(Protocol):
    provider_key: str
    platform: CommunityPlatform

    async def fetch_posts(
        self, topic: str, since: datetime | None = None, cursor: str | None = None
    ) -> list[RawCommunityPostRecord]:
        """Every post/comment matching ``topic`` (a search term or community/subreddit key)
        posted since ``since``."""
        ...
