"""Value objects for the News Intelligence & Community Intelligence Platform (Milestone 8,
docs/news_intelligence.md, docs/community_intelligence.md).

No framework imports — same domain-purity rule as every other module (docs/architecture.md
§2). Every enum here is additive-only once real data exists against it, same convention as
`modules.knowledge_graph.domain.value_objects.NodeType`/`EdgeType`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class NewsSourceType(str, Enum):
    """Every source category named in the Milestone 8 spec's "NEWS INGESTION" section."""

    OFFICIAL_CLUB_WEBSITE = "official_club_website"
    LEAGUE_WEBSITE = "league_website"
    COMPETITION_WEBSITE = "competition_website"
    SPORTS_NEWS_API = "sports_news_api"
    RSS_FEED = "rss_feed"
    APPROVED_PUBLISHER = "approved_publisher"
    PRESS_RELEASE = "press_release"
    FEDERATION_ANNOUNCEMENT = "federation_announcement"


class CommunityPlatform(str, Enum):
    REDDIT = "reddit"
    TWITTER = "twitter"
    YOUTUBE = "youtube"
    OFFICIAL_FAN_COMMUNITY = "official_fan_community"


class NewsEventType(str, Enum):
    """Every event category named in the Milestone 8 spec's "EVENT EXTRACTION" section."""

    TRANSFER = "transfer"
    INJURY = "injury"
    RECOVERY = "recovery"
    SUSPENSION = "suspension"
    MANAGER_CHANGE = "manager_change"
    FORMATION_CHANGE = "formation_change"
    TACTICAL_CHANGE = "tactical_change"
    TRAINING_UPDATE = "training_update"
    WEATHER_REPORT = "weather_report"
    TRAVEL_DELAY = "travel_delay"
    STADIUM_CHANGE = "stadium_change"
    MATCH_POSTPONEMENT = "match_postponement"
    PLAYER_AVAILABILITY = "player_availability"
    LINEUP_EXPECTATION = "lineup_expectation"


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"


class TrustLevel(str, Enum):
    """Ordinal ladder (`level` mirrors the shape of `modules.identity.domain.value_objects.Role`
    — ordinal comparison, not enum-identity comparison, is what the Source Reliability Engine
    and any future consumer should compare on)."""

    UNRELIABLE = "unreliable"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    OFFICIAL = "official"

    @property
    def level(self) -> int:
        return list(TrustLevel).index(self)


class SummaryType(str, Enum):
    SHORT = "short"
    EXECUTIVE = "executive"
    AI_MATCH_BRIEFING = "ai_match_briefing"
    TIMELINE = "timeline"
    PLAYER = "player"
    TEAM = "team"
    COMPETITION = "competition"


class IntelligenceChannelType(str, Enum):
    """Distinguishes a News source channel from a Community platform+topic channel for the
    shared sync-tracking entities (`IntelligenceSyncRun`/`IntelligenceSyncCheckpoint`) — News
    Ingestion and Community Intelligence have structurally identical incremental-sync needs
    (dedup, retry, versioning, scheduling) but are functionally distinct pipelines."""

    NEWS = "news"
    COMMUNITY = "community"


class SyncStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class SyncTrigger(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    RETRY = "retry"


class ArticleStatus(str, Enum):
    ACTIVE = "active"
    DUPLICATE = "duplicate"
    RETRACTED = "retracted"


@dataclass(frozen=True)
class NewsSourceId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class NewsArticleId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class NewsEventId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SourceReliabilityId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SentimentResultId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ImpactScoreId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SummaryId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class CommunityPostId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class CommunityTopicId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class IntelligenceSyncRunId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
