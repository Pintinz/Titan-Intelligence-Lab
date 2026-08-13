"""SQLAlchemy models for the `intelligence` schema (Milestone 8, docs/news_intelligence.md,
docs/community_intelligence.md). Client-side Python defaults (``default=``, not
``server_default=``) throughout — the async-refresh-after-flush pitfall documented in
docs/decisions.md, avoided from the start the same way `modules.knowledge_graph` and
`modules.identity` already do.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, MetaData, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="intelligence")


class Base(DeclarativeBase):
    metadata = metadata


class NewsSourceModel(Base):
    __tablename__ = "news_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    publisher_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NewsArticleModel(Base):
    __tablename__ = "news_articles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("news_sources.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    language: Mapped[str] = mapped_column(String(8), default="en")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    # Milestone 4 item 9 — groundwork only, deliberately unpopulated by this milestone (no
    # historical join is fabricated). Distinct from `published_at` (when the source claims the
    # event occurred) and `fetched_at` (when TitanIQ's ingestion ran, confirmed by Milestone 3's
    # audit to lag `published_at` by anywhere from ~2 hours to 234 days for real articles) — this
    # is meant to eventually hold the genuine "when this became actionable information" moment
    # once a real point-in-time-aware ingestion pipeline exists (Milestone 5+).
    information_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NewsEventModel(Base):
    __tablename__ = "news_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("news_sources.id"), index=True)
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("news_articles.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    affected_entity_refs: Mapped[list] = mapped_column(JSON, default=list)
    kg_edge_ids: Mapped[list] = mapped_column(JSON, default=list)
    # Milestone 9 — resolved_entities: list[{"ref": str, "node_type": str|None, "status": str}].
    resolved_entities: Mapped[list] = mapped_column(JSON, default=list)
    confidence_tier: Mapped[str] = mapped_column(String(16), default="uncertain")
    information_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    availability_classification: Mapped[str] = mapped_column(String(32), default="UNKNOWN_AVAILABILITY_TIME")
    validity_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validity_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class SourceReliabilityScoreModel(Base):
    __tablename__ = "source_reliability_scores"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("news_sources.id"), unique=True, index=True)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.5)
    historical_accuracy: Mapped[float] = mapped_column(Float, default=0.5)
    bias_rating: Mapped[float] = mapped_column(Float, default=0.0)
    verification_status: Mapped[str] = mapped_column(String(16), default="unverified")
    trust_level: Mapped[str] = mapped_column(String(16), default="unverified")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SentimentResultModel(Base):
    __tablename__ = "sentiment_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    target_entity_ref: Mapped[str] = mapped_column(String(128), index=True)
    target_entity_type: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(16))
    momentum: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_ref: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImpactScoreModel(Base):
    __tablename__ = "impact_scores"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    news_event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("news_events.id"), unique=True, index=True)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    factors: Mapped[dict] = mapped_column(JSON, default=dict)
    affected_teams: Mapped[list] = mapped_column(JSON, default=list)
    affected_players: Mapped[list] = mapped_column(JSON, default=list)
    affected_competitions: Mapped[list] = mapped_column(JSON, default=list)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SummaryModel(Base):
    __tablename__ = "summaries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    summary_type: Mapped[str] = mapped_column(String(32), index=True)
    subject_ref: Mapped[str] = mapped_column(String(128), index=True)
    text: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_article_ids: Mapped[list] = mapped_column(JSON, default=list)


class CommunityPostModel(Base):
    __tablename__ = "community_posts"
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uq_community_post_platform_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    author_ref: Mapped[str] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    credibility_score: Mapped[float] = mapped_column(Float, default=0.5)


class CommunityTopicModel(Base):
    __tablename__ = "community_topics"
    __table_args__ = (UniqueConstraint("platform", "topic_label", name="uq_community_topic_platform_label"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    topic_label: Mapped[str] = mapped_column(String(200))
    related_entity_refs: Mapped[list] = mapped_column(JSON, default=list)
    post_count: Mapped[int] = mapped_column(Integer, default=0)
    momentum: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntelligenceSyncRunModel(Base):
    __tablename__ = "intelligence_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel_type: Mapped[str] = mapped_column(String(16), index=True)
    channel_key: Mapped[str] = mapped_column(String(200), index=True)
    trigger: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items_fetched: Mapped[int] = mapped_column(Integer, default=0)
    items_created: Mapped[int] = mapped_column(Integer, default=0)
    items_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    items_rejected: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntelligenceSyncCheckpointModel(Base):
    __tablename__ = "intelligence_sync_checkpoints"
    __table_args__ = (UniqueConstraint("channel_type", "channel_key", name="uq_intelligence_checkpoint_channel"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel_type: Mapped[str] = mapped_column(String(16), index=True)
    channel_key: Mapped[str] = mapped_column(String(200), index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
