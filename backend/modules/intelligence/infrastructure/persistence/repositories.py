from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.intelligence.domain.entities import (
    CommunityPost,
    CommunityTopic,
    ImpactScore,
    IntelligenceSyncCheckpoint,
    IntelligenceSyncRun,
    NewsArticle,
    NewsEvent,
    NewsSource,
    SentimentResult,
    SourceReliabilityScore,
    Summary,
)
from modules.intelligence.domain.value_objects import (
    CommunityPlatform,
    CommunityPostId,
    CommunityTopicId,
    ImpactScoreId,
    IntelligenceChannelType,
    IntelligenceSyncRunId,
    NewsArticleId,
    NewsEventId,
    NewsSourceId,
    NewsSourceType,
    SummaryId,
    SummaryType,
)
from modules.intelligence.infrastructure.persistence import mappers
from modules.intelligence.infrastructure.persistence.models import (
    CommunityPostModel,
    CommunityTopicModel,
    ImpactScoreModel,
    IntelligenceSyncCheckpointModel,
    IntelligenceSyncRunModel,
    NewsArticleModel,
    NewsEventModel,
    NewsSourceModel,
    SentimentResultModel,
    SourceReliabilityScoreModel,
    SummaryModel,
)


@dataclass
class SqlAlchemyNewsSourceRepository:
    session: AsyncSession

    async def get(self, source_id: NewsSourceId) -> NewsSource | None:
        model = await self.session.get(NewsSourceModel, source_id.value)
        return mappers.source_to_domain(model) if model else None

    async def get_by_url(self, url: str) -> NewsSource | None:
        stmt = select(NewsSourceModel).where(NewsSourceModel.url == url)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.source_to_domain(model) if model else None

    async def list_by_type(self, source_type: NewsSourceType) -> list[NewsSource]:
        stmt = select(NewsSourceModel).where(NewsSourceModel.source_type == source_type.value)
        result = await self.session.execute(stmt)
        return [mappers.source_to_domain(row) for row in result.scalars().all()]

    async def list_all(self) -> list[NewsSource]:
        result = await self.session.execute(select(NewsSourceModel))
        return [mappers.source_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, source: NewsSource) -> NewsSource:
        existing = await self.session.get(NewsSourceModel, source.id.value)
        model = mappers.source_to_model(source, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.source_to_domain(model)


@dataclass
class SqlAlchemyNewsArticleRepository:
    session: AsyncSession

    async def get(self, article_id: NewsArticleId) -> NewsArticle | None:
        model = await self.session.get(NewsArticleModel, article_id.value)
        return mappers.article_to_domain(model) if model else None

    async def get_by_content_hash(self, content_hash: str) -> NewsArticle | None:
        stmt = select(NewsArticleModel).where(NewsArticleModel.content_hash == content_hash)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.article_to_domain(model) if model else None

    async def get_by_url(self, url: str) -> NewsArticle | None:
        stmt = select(NewsArticleModel).where(NewsArticleModel.url == url)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.article_to_domain(model) if model else None

    async def upsert(self, article: NewsArticle) -> NewsArticle:
        existing = await self.session.get(NewsArticleModel, article.id.value)
        model = mappers.article_to_model(article, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.article_to_domain(model)

    async def search(
        self, query: str | None = None, source_id: NewsSourceId | None = None, limit: int = 50
    ) -> list[NewsArticle]:
        stmt = select(NewsArticleModel)
        if source_id is not None:
            stmt = stmt.where(NewsArticleModel.source_id == source_id.value)
        if query:
            stmt = stmt.where(NewsArticleModel.title.ilike(f"%{query}%"))
        stmt = stmt.order_by(NewsArticleModel.published_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.article_to_domain(row) for row in result.scalars().all()]

    async def list_since(self, since: datetime, limit: int = 200) -> list[NewsArticle]:
        stmt = (
            select(NewsArticleModel)
            .where(NewsArticleModel.published_at >= since)
            .order_by(NewsArticleModel.published_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.article_to_domain(row) for row in result.scalars().all()]

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(NewsArticleModel))
        return result.scalar_one()


@dataclass
class SqlAlchemyNewsEventRepository:
    session: AsyncSession

    async def get(self, event_id: NewsEventId) -> NewsEvent | None:
        model = await self.session.get(NewsEventModel, event_id.value)
        return mappers.event_to_domain(model) if model else None

    async def record(self, event: NewsEvent) -> NewsEvent:
        existing = await self.session.get(NewsEventModel, event.id.value)
        model = mappers.event_to_model(event, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.event_to_domain(model)

    async def list_for_entity(self, entity_ref: str, limit: int = 50) -> list[NewsEvent]:
        result = await self.session.execute(select(NewsEventModel).order_by(NewsEventModel.detected_at.desc()))
        matches = [
            mappers.event_to_domain(row)
            for row in result.scalars().all()
            if entity_ref in (row.affected_entity_refs or [])
        ]
        return matches[:limit]

    async def list_for_article(self, article_id: NewsArticleId) -> list[NewsEvent]:
        stmt = select(NewsEventModel).where(NewsEventModel.article_id == article_id.value)
        result = await self.session.execute(stmt)
        return [mappers.event_to_domain(row) for row in result.scalars().all()]

    async def list_timeline(
        self, since: datetime | None = None, until: datetime | None = None, limit: int = 100
    ) -> list[NewsEvent]:
        stmt = select(NewsEventModel)
        if since is not None:
            stmt = stmt.where(NewsEventModel.occurred_at >= since)
        if until is not None:
            stmt = stmt.where(NewsEventModel.occurred_at <= until)
        stmt = stmt.order_by(NewsEventModel.occurred_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.event_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemySourceReliabilityRepository:
    session: AsyncSession

    async def get_for_source(self, source_id: NewsSourceId) -> SourceReliabilityScore | None:
        stmt = select(SourceReliabilityScoreModel).where(SourceReliabilityScoreModel.source_id == source_id.value)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.reliability_to_domain(model) if model else None

    async def upsert(self, score: SourceReliabilityScore) -> SourceReliabilityScore:
        existing = await self.get_for_source(score.source_id)
        existing_model = await self.session.get(SourceReliabilityScoreModel, existing.id.value) if existing else None
        model = mappers.reliability_to_model(score, existing_model)
        self.session.add(model)
        await self.session.flush()
        return mappers.reliability_to_domain(model)

    async def list_all(self) -> list[SourceReliabilityScore]:
        result = await self.session.execute(select(SourceReliabilityScoreModel))
        return [mappers.reliability_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemySentimentResultRepository:
    session: AsyncSession

    async def record(self, result: SentimentResult) -> SentimentResult:
        existing = await self.session.get(SentimentResultModel, result.id.value)
        model = mappers.sentiment_to_model(result, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.sentiment_to_domain(model)

    async def list_for_entity(self, entity_ref: str, limit: int = 50) -> list[SentimentResult]:
        stmt = (
            select(SentimentResultModel)
            .where(SentimentResultModel.target_entity_ref == entity_ref)
            .order_by(SentimentResultModel.computed_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.sentiment_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyImpactScoreRepository:
    session: AsyncSession

    async def get(self, impact_id: ImpactScoreId) -> ImpactScore | None:
        model = await self.session.get(ImpactScoreModel, impact_id.value)
        return mappers.impact_to_domain(model) if model else None

    async def record(self, score: ImpactScore) -> ImpactScore:
        existing = await self.session.get(ImpactScoreModel, score.id.value)
        model = mappers.impact_to_model(score, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.impact_to_domain(model)

    async def get_for_event(self, news_event_id: NewsEventId) -> ImpactScore | None:
        stmt = select(ImpactScoreModel).where(ImpactScoreModel.news_event_id == news_event_id.value)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.impact_to_domain(model) if model else None

    async def list_recent(self, limit: int = 50) -> list[ImpactScore]:
        stmt = select(ImpactScoreModel).order_by(ImpactScoreModel.computed_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.impact_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemySummaryRepository:
    session: AsyncSession

    async def get(self, summary_id: SummaryId) -> Summary | None:
        model = await self.session.get(SummaryModel, summary_id.value)
        return mappers.summary_to_domain(model) if model else None

    async def record(self, summary: Summary) -> Summary:
        existing = await self.session.get(SummaryModel, summary.id.value)
        model = mappers.summary_to_model(summary, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.summary_to_domain(model)

    async def get_latest(self, subject_ref: str, summary_type: SummaryType) -> Summary | None:
        stmt = (
            select(SummaryModel)
            .where(SummaryModel.subject_ref == subject_ref, SummaryModel.summary_type == summary_type.value)
            .order_by(SummaryModel.generated_at.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.summary_to_domain(model) if model else None


@dataclass
class SqlAlchemyCommunityPostRepository:
    session: AsyncSession

    async def get_by_external_id(self, platform: CommunityPlatform, external_id: str) -> CommunityPost | None:
        stmt = select(CommunityPostModel).where(
            CommunityPostModel.platform == platform.value, CommunityPostModel.external_id == external_id
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.post_to_domain(model) if model else None

    async def upsert(self, post: CommunityPost) -> CommunityPost:
        existing = await self.session.get(CommunityPostModel, post.id.value)
        model = mappers.post_to_model(post, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.post_to_domain(model)

    async def list_recent(self, platform: CommunityPlatform | None = None, limit: int = 100) -> list[CommunityPost]:
        stmt = select(CommunityPostModel)
        if platform is not None:
            stmt = stmt.where(CommunityPostModel.platform == platform.value)
        stmt = stmt.order_by(CommunityPostModel.posted_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.post_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyCommunityTopicRepository:
    session: AsyncSession

    async def get(self, topic_id: CommunityTopicId) -> CommunityTopic | None:
        model = await self.session.get(CommunityTopicModel, topic_id.value)
        return mappers.topic_to_domain(model) if model else None

    async def get_by_label(self, platform: CommunityPlatform, topic_label: str) -> CommunityTopic | None:
        stmt = select(CommunityTopicModel).where(
            CommunityTopicModel.platform == platform.value, CommunityTopicModel.topic_label == topic_label
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.topic_to_domain(model) if model else None

    async def upsert(self, topic: CommunityTopic) -> CommunityTopic:
        existing = await self.session.get(CommunityTopicModel, topic.id.value)
        model = mappers.topic_to_model(topic, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.topic_to_domain(model)

    async def list_all(self, platform: CommunityPlatform | None = None) -> list[CommunityTopic]:
        stmt = select(CommunityTopicModel)
        if platform is not None:
            stmt = stmt.where(CommunityTopicModel.platform == platform.value)
        result = await self.session.execute(stmt)
        return [mappers.topic_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyIntelligenceSyncRunRepository:
    session: AsyncSession

    async def record(self, run: IntelligenceSyncRun) -> IntelligenceSyncRun:
        model = mappers.sync_run_to_model(run)
        self.session.add(model)
        await self.session.flush()
        return mappers.sync_run_to_domain(model)

    async def update(self, run: IntelligenceSyncRun) -> IntelligenceSyncRun:
        existing = await self.session.get(IntelligenceSyncRunModel, run.id.value)
        model = mappers.sync_run_to_model(run, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.sync_run_to_domain(model)

    async def get(self, run_id: IntelligenceSyncRunId) -> IntelligenceSyncRun | None:
        model = await self.session.get(IntelligenceSyncRunModel, run_id.value)
        return mappers.sync_run_to_domain(model) if model else None

    async def list_recent(
        self, channel_type: IntelligenceChannelType | None = None, limit: int = 50
    ) -> list[IntelligenceSyncRun]:
        stmt = select(IntelligenceSyncRunModel)
        if channel_type is not None:
            stmt = stmt.where(IntelligenceSyncRunModel.channel_type == channel_type.value)
        stmt = stmt.order_by(IntelligenceSyncRunModel.started_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.sync_run_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyIntelligenceSyncCheckpointRepository:
    session: AsyncSession

    async def get(
        self, channel_type: IntelligenceChannelType, channel_key: str
    ) -> IntelligenceSyncCheckpoint | None:
        stmt = select(IntelligenceSyncCheckpointModel).where(
            IntelligenceSyncCheckpointModel.channel_type == channel_type.value,
            IntelligenceSyncCheckpointModel.channel_key == channel_key,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.checkpoint_to_domain(model) if model else None

    async def upsert(self, checkpoint: IntelligenceSyncCheckpoint) -> IntelligenceSyncCheckpoint:
        stmt = select(IntelligenceSyncCheckpointModel).where(
            IntelligenceSyncCheckpointModel.channel_type == checkpoint.channel_type.value,
            IntelligenceSyncCheckpointModel.channel_key == checkpoint.channel_key,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        model = mappers.checkpoint_to_model(checkpoint, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.checkpoint_to_domain(model)
