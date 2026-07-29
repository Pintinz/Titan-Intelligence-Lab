from __future__ import annotations

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
    ArticleStatus,
    CommunityPlatform,
    CommunityPostId,
    CommunityTopicId,
    ImpactScoreId,
    IntelligenceChannelType,
    IntelligenceSyncRunId,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
    NewsSourceType,
    SentimentLabel,
    SentimentResultId,
    SourceReliabilityId,
    SummaryId,
    SummaryType,
    SyncStatus,
    SyncTrigger,
    TrustLevel,
    VerificationStatus,
)
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


def source_to_domain(model: NewsSourceModel) -> NewsSource:
    return NewsSource(
        id=NewsSourceId(model.id), source_type=NewsSourceType(model.source_type), name=model.name, url=model.url,
        is_official=model.is_official, publisher_metadata=dict(model.publisher_metadata or {}),
        created_at=model.created_at,
    )


def source_to_model(entity: NewsSource, model: NewsSourceModel | None = None) -> NewsSourceModel:
    model = model or NewsSourceModel(id=entity.id.value)
    model.source_type = entity.source_type.value
    model.name = entity.name
    model.url = entity.url
    model.is_official = entity.is_official
    model.publisher_metadata = entity.publisher_metadata
    model.created_at = entity.created_at
    return model


def article_to_domain(model: NewsArticleModel) -> NewsArticle:
    return NewsArticle(
        id=NewsArticleId(model.id), source_id=NewsSourceId(model.source_id), title=model.title, url=model.url,
        content_hash=model.content_hash, raw_text=model.raw_text, published_at=model.published_at,
        fetched_at=model.fetched_at, language=model.language, version=model.version,
        status=ArticleStatus(model.status),
    )


def article_to_model(entity: NewsArticle, model: NewsArticleModel | None = None) -> NewsArticleModel:
    model = model or NewsArticleModel(id=entity.id.value)
    model.source_id = entity.source_id.value
    model.title = entity.title
    model.url = entity.url
    model.content_hash = entity.content_hash
    model.raw_text = entity.raw_text
    model.published_at = entity.published_at
    model.fetched_at = entity.fetched_at
    model.language = entity.language
    model.version = entity.version
    model.status = entity.status.value
    return model


def event_to_domain(model: NewsEventModel) -> NewsEvent:
    return NewsEvent(
        id=NewsEventId(model.id), event_type=NewsEventType(model.event_type), summary=model.summary,
        confidence=model.confidence, source_id=NewsSourceId(model.source_id),
        article_id=NewsArticleId(model.article_id), occurred_at=model.occurred_at, detected_at=model.detected_at,
        affected_entity_refs=tuple(model.affected_entity_refs or []), kg_edge_ids=tuple(model.kg_edge_ids or []),
    )


def event_to_model(entity: NewsEvent, model: NewsEventModel | None = None) -> NewsEventModel:
    model = model or NewsEventModel(id=entity.id.value)
    model.event_type = entity.event_type.value
    model.summary = entity.summary
    model.confidence = entity.confidence
    model.source_id = entity.source_id.value
    model.article_id = entity.article_id.value
    model.occurred_at = entity.occurred_at
    model.detected_at = entity.detected_at
    model.affected_entity_refs = list(entity.affected_entity_refs)
    model.kg_edge_ids = list(entity.kg_edge_ids)
    return model


def reliability_to_domain(model: SourceReliabilityScoreModel) -> SourceReliabilityScore:
    return SourceReliabilityScore(
        id=SourceReliabilityId(model.id), source_id=NewsSourceId(model.source_id),
        reliability_score=model.reliability_score, historical_accuracy=model.historical_accuracy,
        bias_rating=model.bias_rating, verification_status=VerificationStatus(model.verification_status),
        trust_level=TrustLevel(model.trust_level), updated_at=model.updated_at,
    )


def reliability_to_model(
    entity: SourceReliabilityScore, model: SourceReliabilityScoreModel | None = None
) -> SourceReliabilityScoreModel:
    model = model or SourceReliabilityScoreModel(id=entity.id.value)
    model.source_id = entity.source_id.value
    model.reliability_score = entity.reliability_score
    model.historical_accuracy = entity.historical_accuracy
    model.bias_rating = entity.bias_rating
    model.verification_status = entity.verification_status.value
    model.trust_level = entity.trust_level.value
    model.updated_at = entity.updated_at
    return model


def sentiment_to_domain(model: SentimentResultModel) -> SentimentResult:
    return SentimentResult(
        id=SentimentResultId(model.id), target_entity_ref=model.target_entity_ref,
        target_entity_type=model.target_entity_type, label=SentimentLabel(model.label), momentum=model.momentum,
        confidence=model.confidence, source_ref=model.source_ref, computed_at=model.computed_at,
    )


def sentiment_to_model(entity: SentimentResult, model: SentimentResultModel | None = None) -> SentimentResultModel:
    model = model or SentimentResultModel(id=entity.id.value)
    model.target_entity_ref = entity.target_entity_ref
    model.target_entity_type = entity.target_entity_type
    model.label = entity.label.value
    model.momentum = entity.momentum
    model.confidence = entity.confidence
    model.source_ref = entity.source_ref
    model.computed_at = entity.computed_at
    return model


def impact_to_domain(model: ImpactScoreModel) -> ImpactScore:
    return ImpactScore(
        id=ImpactScoreId(model.id), news_event_id=NewsEventId(model.news_event_id),
        impact_score=model.impact_score, confidence=model.confidence, factors=dict(model.factors or {}),
        affected_teams=tuple(model.affected_teams or []), affected_players=tuple(model.affected_players or []),
        affected_competitions=tuple(model.affected_competitions or []), computed_at=model.computed_at,
    )


def impact_to_model(entity: ImpactScore, model: ImpactScoreModel | None = None) -> ImpactScoreModel:
    model = model or ImpactScoreModel(id=entity.id.value)
    model.news_event_id = entity.news_event_id.value
    model.impact_score = entity.impact_score
    model.confidence = entity.confidence
    model.factors = entity.factors
    model.affected_teams = list(entity.affected_teams)
    model.affected_players = list(entity.affected_players)
    model.affected_competitions = list(entity.affected_competitions)
    model.computed_at = entity.computed_at
    return model


def summary_to_domain(model: SummaryModel) -> Summary:
    return Summary(
        id=SummaryId(model.id), summary_type=SummaryType(model.summary_type), subject_ref=model.subject_ref,
        text=model.text, generated_at=model.generated_at, source_article_ids=tuple(model.source_article_ids or []),
    )


def summary_to_model(entity: Summary, model: SummaryModel | None = None) -> SummaryModel:
    model = model or SummaryModel(id=entity.id.value)
    model.summary_type = entity.summary_type.value
    model.subject_ref = entity.subject_ref
    model.text = entity.text
    model.generated_at = entity.generated_at
    model.source_article_ids = list(entity.source_article_ids)
    return model


def post_to_domain(model: CommunityPostModel) -> CommunityPost:
    return CommunityPost(
        id=CommunityPostId(model.id), platform=CommunityPlatform(model.platform), external_id=model.external_id,
        author_ref=model.author_ref, text=model.text, posted_at=model.posted_at, fetched_at=model.fetched_at,
        credibility_score=model.credibility_score,
    )


def post_to_model(entity: CommunityPost, model: CommunityPostModel | None = None) -> CommunityPostModel:
    model = model or CommunityPostModel(id=entity.id.value)
    model.platform = entity.platform.value
    model.external_id = entity.external_id
    model.author_ref = entity.author_ref
    model.text = entity.text
    model.posted_at = entity.posted_at
    model.fetched_at = entity.fetched_at
    model.credibility_score = entity.credibility_score
    return model


def topic_to_domain(model: CommunityTopicModel) -> CommunityTopic:
    return CommunityTopic(
        id=CommunityTopicId(model.id), platform=CommunityPlatform(model.platform), topic_label=model.topic_label,
        related_entity_refs=tuple(model.related_entity_refs or []), post_count=model.post_count,
        momentum=model.momentum, created_at=model.created_at,
    )


def topic_to_model(entity: CommunityTopic, model: CommunityTopicModel | None = None) -> CommunityTopicModel:
    model = model or CommunityTopicModel(id=entity.id.value)
    model.platform = entity.platform.value
    model.topic_label = entity.topic_label
    model.related_entity_refs = list(entity.related_entity_refs)
    model.post_count = entity.post_count
    model.momentum = entity.momentum
    model.created_at = entity.created_at
    return model


def sync_run_to_domain(model: IntelligenceSyncRunModel) -> IntelligenceSyncRun:
    return IntelligenceSyncRun(
        id=IntelligenceSyncRunId(model.id), channel_type=IntelligenceChannelType(model.channel_type),
        channel_key=model.channel_key, trigger=SyncTrigger(model.trigger), status=SyncStatus(model.status),
        started_at=model.started_at, finished_at=model.finished_at, items_fetched=model.items_fetched,
        items_created=model.items_created, items_duplicate=model.items_duplicate,
        items_rejected=model.items_rejected, error_message=model.error_message,
    )


def sync_run_to_model(entity: IntelligenceSyncRun, model: IntelligenceSyncRunModel | None = None) -> IntelligenceSyncRunModel:
    model = model or IntelligenceSyncRunModel(id=entity.id.value)
    model.channel_type = entity.channel_type.value
    model.channel_key = entity.channel_key
    model.trigger = entity.trigger.value
    model.status = entity.status.value
    model.started_at = entity.started_at
    model.finished_at = entity.finished_at
    model.items_fetched = entity.items_fetched
    model.items_created = entity.items_created
    model.items_duplicate = entity.items_duplicate
    model.items_rejected = entity.items_rejected
    model.error_message = entity.error_message
    return model


def checkpoint_to_domain(model: IntelligenceSyncCheckpointModel) -> IntelligenceSyncCheckpoint:
    return IntelligenceSyncCheckpoint(
        channel_type=IntelligenceChannelType(model.channel_type), channel_key=model.channel_key,
        last_synced_at=model.last_synced_at, cursor=model.cursor, consecutive_failures=model.consecutive_failures,
    )


def checkpoint_to_model(
    entity: IntelligenceSyncCheckpoint, model: IntelligenceSyncCheckpointModel | None = None
) -> IntelligenceSyncCheckpointModel:
    model = model or IntelligenceSyncCheckpointModel()
    model.channel_type = entity.channel_type.value
    model.channel_key = entity.channel_key
    model.last_synced_at = entity.last_synced_at
    model.cursor = entity.cursor
    model.consecutive_failures = entity.consecutive_failures
    return model
