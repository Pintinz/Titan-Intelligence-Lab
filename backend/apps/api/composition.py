"""Composition root for apps/api — the one place that wires ports to concrete infrastructure
implementations (docs/architecture.md §3). Route handlers depend on this module's factories via
FastAPI's ``Depends``, never on infrastructure classes directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from modules.admin.application.circuit_breaker import CircuitBreaker
from modules.admin.application.feature_flag_service import FeatureFlagService
from modules.admin.application.health_intelligence_engine import HealthIntelligenceEngine
from modules.admin.application.provider_management_service import ProviderManagementService, normalize_credential_label
from modules.admin.application.quota_intelligence_engine import QuotaIntelligenceEngine
from modules.admin.infrastructure.persistence.repositories import (
    SqlAlchemyCredentialRepository,
    SqlAlchemyFeatureFlagRepository,
    SqlAlchemyHealthRepository,
    SqlAlchemyHealthStateRepository,
    SqlAlchemyIncidentRepository,
    SqlAlchemyProviderRepository,
    SqlAlchemyUsageRepository,
)
from modules.admin.infrastructure.vault import FernetCredentialVault
from modules.billing.application.billing_service import BillingService
from modules.billing.application.checkout_service import CheckoutService
from modules.billing.infrastructure.flutterwave.flutterwave_provider import FlutterwavePaymentProvider
from modules.billing.infrastructure.persistence.repositories import (
    SqlAlchemyEntitlementRepository,
    SqlAlchemyPendingCheckoutRepository,
    SqlAlchemyPlanRepository,
    SqlAlchemyProcessedPaymentEventRepository,
    SqlAlchemySubscriptionRepository,
    SqlAlchemyUsageCounterRepository,
)
from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_quality_engine import FeatureQualityEngine
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.features.infrastructure.online.redis_feature_store import RedisFeatureStore, build_redis_client
from modules.features.infrastructure.persistence.repositories import (
    SqlAlchemyFeatureComputationLogRepository,
    SqlAlchemyFeatureConsumerRepository,
    SqlAlchemyFeatureDefinitionRepository,
    SqlAlchemyFeatureLineageRepository,
    SqlAlchemyFeatureUsageRepository,
    SqlAlchemyFeatureValidationReportRepository,
    SqlAlchemyFeatureValueRepository,
    SqlAlchemyFeatureVersionRepository,
)
from modules.identity.application.identity_service import IdentityService
from modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyAccountLockRepository,
    SqlAlchemyAuditLogRepository,
    SqlAlchemyFederatedIdentityRepository,
    SqlAlchemyPersonalAccessTokenRepository,
    SqlAlchemySecurityEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from modules.identity.infrastructure.security import (
    BcryptPasswordHasher,
    Sha256TokenHasher,
    SupabaseJWKSValidator,
)
from modules.identity.ports.security import JWTValidatorPort
from modules.ingestion.application.data_quality_engine import IngestionQualityEngine
from modules.ingestion.application.data_validation_engine import DataValidationEngine
from modules.ingestion.application.cross_provider_team_mapping_service import CrossProviderTeamMappingService
from modules.ingestion.application.entity_reconciliation_service import EntityReconciliationService
from modules.ingestion.application.historical_import_service import HistoricalImportService
from modules.ingestion.application.monitoring_service import MonitoringService
from modules.ingestion.application.sync_orchestrator import SyncOrchestrator
from modules.ingestion.infrastructure.cache.redis_lock import RedisDistributedLock
from modules.ingestion.infrastructure.cache.redis_sync_cache import RedisSyncCache
from modules.ingestion.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionFixtureSourceRepository,
    SqlAlchemyDataQualityReportRepository,
    SqlAlchemyProviderRefIndexRepository,
    SqlAlchemySyncCheckpointRepository,
    SqlAlchemySyncRunRepository,
    SqlAlchemyTimelineEventRepository,
)
from modules.knowledge_graph.application.context_engine import ContextEngine
from modules.knowledge_graph.application.entity_resolution_service import EntityResolutionService
from modules.knowledge_graph.application.graph_monitoring_service import GraphMonitoringService
from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.application.semantic_search_service import SemanticSearchService
from modules.knowledge_graph.application.similarity_service import SimilarityService
from modules.knowledge_graph.application.temporal_graph_service import TemporalGraphService
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)
from modules.knowledge_graph.infrastructure.similarity.graph_structural import GraphStructuralSimilarity
from modules.knowledge_graph.infrastructure.retrieval.graph_native_retrieval import GraphNativeRetrieval
from modules.intelligence.application.community_ingestion_service import CommunityIngestionService
from modules.intelligence.application.entity_extraction_service import EntityExtractionService
from modules.intelligence.application.event_extraction_service import EventExtractionService
from modules.intelligence.application.feature_store_enrichment_service import FeatureStoreEnrichmentService
from modules.intelligence.application.intelligence_enrichment_orchestrator import IntelligenceEnrichmentOrchestrator
from modules.intelligence.application.intelligence_monitoring_service import (
    IntelligenceMetricsRecorder,
    IntelligenceMonitoringService,
)
from modules.intelligence.application.intelligence_retrieval_service import (
    AIReportRetrieval,
    CommunityRetrieval,
    IntelligenceRetrievalService,
    KnowledgeGraphRetrievalAdapter,
    MatchTeamNamesResolver,
    NewsRetrieval,
)
from modules.intelligence.application.knowledge_graph_enrichment_service import KnowledgeGraphEnrichmentService
from modules.intelligence.application.news_impact_engine import NewsImpactEngine
from modules.intelligence.application.news_ingestion_service import NewsIngestionService
from modules.intelligence.application.historical_entity_resolution_service import HistoricalEntityResolutionService
from modules.intelligence.application.historical_news_relevance_engine import HistoricalNewsRelevanceEngine
from modules.intelligence.application.news_backfill_service import NewsBackfillService
from modules.intelligence.application.scheduled_news_sync_service import ScheduledNewsSyncService
from modules.intelligence.application.sentiment_service import SentimentService
from modules.intelligence.application.source_reliability_service import SourceReliabilityService
from modules.intelligence.application.summarization_service import SummarizationService
from modules.intelligence.infrastructure.gemini_adapter import GeminiAdapter
from modules.intelligence.infrastructure.mock_gemini_adapter import MockGeminiAdapter
from modules.intelligence.infrastructure.providers.rss_news_provider import RssNewsProvider
from modules.intelligence.infrastructure.text_intelligence_router import TextIntelligenceRouter
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyCommunityPostRepository,
    SqlAlchemyCommunityTopicRepository,
    SqlAlchemyImpactScoreRepository,
    SqlAlchemyIntelligenceSyncCheckpointRepository,
    SqlAlchemyIntelligenceSyncRunRepository,
    SqlAlchemyNewsArticleRepository,
    SqlAlchemyNewsEventRepository,
    SqlAlchemyNewsSourceRepository,
    SqlAlchemySentimentResultRepository,
    SqlAlchemySourceReliabilityRepository,
    SqlAlchemySummaryRepository,
)
from modules.intelligence.ports.text_intelligence_provider import TextIntelligenceProviderPort
from modules.predictions.application.calibration_reporting_service import CalibrationReportBuilder
from modules.predictions.application.confidence_engine import ConfidenceEngine
from modules.predictions.application.contextual_reasoning_service import ContextualReasoningService
from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.dataset_registry_service import DatasetRegistryService
from modules.predictions.application.live_evidence_gatherer import LiveEvidenceGatherer
from modules.predictions.application.statistical_baseline_provider import StatisticalBaselineProvider
from modules.predictions.application.training_preflight_service import TrainingPreflightService
from modules.predictions.application.predictive_signal_audit_service import PredictiveSignalAuditService
from modules.predictions.application.experiment_tracking_service import ExperimentTrackingService
from modules.predictions.application.goal_generative_comparison_service import GoalGenerativeComparisonService
from modules.predictions.application.explainability_engine import ExplainabilityEngine
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.application.market_registry_service import MarketRegistryService
from modules.predictions.application.model_monitoring_service import ModelMonitoringService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.model_selection_service import AutomaticModelSelectionService
from modules.predictions.application.model_version_resolver import ModelVersionResolver
from modules.predictions.application.outcome_resolution_service import OutcomeResolutionService
from modules.predictions.application.prediction_admin_service import PredictionAdminService
from modules.predictions.application.prediction_cache_service import PredictionCacheService
from modules.predictions.application.prediction_consistency_gate import PredictionConsistencyGate
from modules.predictions.application.prediction_context_builder import PredictionContextBuilder
from modules.predictions.application.prediction_engine import PredictionEngine
from modules.predictions.application.prediction_serving_service import AsyncPredictionQueueService, BatchPredictionService
from modules.predictions.application.calibration_fitting_service import CalibrationFittingService
from modules.predictions.application.predictor_registry import PredictorRegistry
from modules.predictions.application.backtest_service import BacktestService
from modules.predictions.application.challenger_evaluation_service import ChallengerEvaluationService
from modules.predictions.application.error_memory_service import ErrorMemoryService
from modules.predictions.application.scheduled_retraining_orchestrator import ScheduledRetrainingOrchestrator
from modules.predictions.application.training_pipeline_service import RetrainingScheduler, TrainingPipelineService
from modules.predictions.application.historical_feature_reconstruction_service import (
    HistoricalFeatureReconstructionService,
)
from modules.predictions.application.news_market_impact_engine import NewsMarketImpactEngine
from modules.predictions.application.windowed_feature_engineering_service import (
    FixtureExpectedGoalsCalculator,
    FixtureFormDifferentialCalculator,
    LineupContinuityCalculator,
    TransferActivityCalculator,
    baseball_fixture_form_differential_calculator,
    baseball_form_calculator,
    basketball_fixture_form_differential_calculator,
    basketball_form_calculator,
    football_fixture_expected_goals_calculator,
    football_fixture_stat_differential_calculators,
    football_form_calculator,
    football_lineup_continuity_calculators,
    football_transfer_activity_calculators,
    table_tennis_form_calculator,
)
from modules.predictions.baseball.market_seeding import BaseballMarketSeeder
from modules.predictions.basketball.market_seeding import BasketballMarketSeeder
from modules.predictions.football.market_seeding import FootballMarketSeeder
from modules.predictions.football.odds_feature_writer import FootballOddsFeatureWriter, football_odds_feature_writer
from modules.predictions.infrastructure.calibration.isotonic_regression_calibrator import (
    IsotonicRegressionCalibrator,
)
from modules.predictions.infrastructure.calibration.platt_scaling_calibrator import PlattScalingCalibrator
from modules.predictions.infrastructure.calibration.temperature_scaling_calibrator import (
    TemperatureScalingCalibrator,
)
from modules.predictions.infrastructure.ml.local_artifact_store import LocalFilesystemArtifactStore
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.infrastructure.ml.shap_explainer_service import SHAPExplainerService
from modules.predictions.infrastructure.monitoring.in_memory_latency_repository import (
    InMemoryLatencySampleRepository,
)
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyCalibrationParametersRepository,
    SqlAlchemyCalibrationReportRepository,
    SqlAlchemyContextReviewRepository,
    SqlAlchemyModelComparisonRepository,
    SqlAlchemyDatasetRepository,
    SqlAlchemyExperimentRepository,
    SqlAlchemyFeatureMarketMappingRepository,
    SqlAlchemyFootballExplanationRepository,
    SqlAlchemyMarketRepository,
    SqlAlchemyModelEvaluationRepository,
    SqlAlchemyModelRepository,
    SqlAlchemyPredictionAuditRepository,
    SqlAlchemyPredictionOutcomeRepository,
    SqlAlchemyPredictionRepository,
    SqlAlchemyTrainingRunRepository,
)
from modules.predictions.application.calibration_validation_service import CalibrationValidationService
from modules.predictions.application.model_attribution_service import ModelAttributionService
from modules.predictions.application.football_explanation_service import FootballExplanationService
from modules.predictions.infrastructure.predictors.weighted_scoring import (
    WeightedLinearPredictor,
    WeightedLogisticPredictor,
    WeightedOrdinalPredictor,
)
from modules.predictions.ports.calibrator import CalibratorPort
from modules.predictions.ports.dataset_repository import DatasetRepositoryPort
from modules.predictions.ports.repositories import ModelComparisonRepositoryPort
from modules.predictions.ports.ml_model import ModelArtifactStorePort
from modules.predictions.ports.monitoring import LatencySampleRepositoryPort
from modules.predictions.table_tennis.market_seeding import TableTennisMarketSeeder
from modules.sports.bootstrap import build_sport_plugin_registry
from modules.tenancy.application.tenancy_service import TenancyService
from modules.tenancy.infrastructure.persistence.repositories import (
    SqlAlchemyInvitationRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyTeamRepository as SqlAlchemyTenancyTeamRepository,
)
from modules.webhooks.application.webhook_service import WebhookService
from modules.webhooks.infrastructure.persistence.repositories import (
    SqlAlchemyWebhookDeliveryRepository,
    SqlAlchemyWebhookEndpointRepository,
)
from modules.watchlist.application.watchlist_service import WatchlistService
from modules.watchlist.infrastructure.persistence.repositories import SqlAlchemyWatchlistRepository
from modules.alerts.application.alert_service import AlertService
from modules.alerts.infrastructure.persistence.repositories import SqlAlchemyAlertEventRepository
from modules.sports.infrastructure.persistence.database import build_engine, build_session_factory
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCoachingStaffRepository,
    SqlAlchemyCompetitionRepository,
    SqlAlchemyCountryRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyInjuryRepository,
    SqlAlchemyLineupRepository,
    SqlAlchemyMarketLineRepository,
    SqlAlchemyMatchRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyTeamStatisticsRepository,
    SqlAlchemyTransferRepository,
    SqlAlchemyVenueRepository,
)
from modules.sports.infrastructure.providers.api_sports_adapter import (
    ApiBaseballAdapter,
    ApiBasketballAdapter,
    ApiFootballAdapter,
)
from modules.sports.infrastructure.providers.football_data_org_adapter import FootballDataOrgAdapter
from modules.sports.infrastructure.providers.thesportsdb_adapter import TheSportsDbAdapter
from modules.sports.infrastructure.providers.mock_provider import MockSportsDataProvider
from modules.sports.infrastructure.providers.provider_router import SportsProviderRouter
from modules.sports.application.capability_resolver import CapabilityResolver
from modules.sports.application.source_selection_service import SourceSelectionService

_circuit_breaker = CircuitBreaker()
_intelligence_metrics_recorder = IntelligenceMetricsRecorder()


@lru_cache
def get_sport_plugin_registry():
    return build_sport_plugin_registry()


@lru_cache
def get_engine():
    return build_engine()


@lru_cache
def get_session_factory():
    return build_session_factory(get_engine())


def get_circuit_breaker() -> CircuitBreaker:
    return _circuit_breaker


def get_intelligence_metrics_recorder() -> IntelligenceMetricsRecorder:
    """POST-M24 Phase 2: process-wide singleton so `gemini_call_count` reflects reality — every
    `build_*` factory in this module builds a fresh service instance per call, so without this,
    `GeminiAdapter` (which increments the counter) and `IntelligenceMonitoringService` (which
    reads it) previously never shared the same `IntelligenceMetricsRecorder`, and the metric read
    zero forever regardless of real Gemini usage."""
    return _intelligence_metrics_recorder


async def get_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
        await session.commit()


def build_provider_management_service(session: AsyncSession) -> ProviderManagementService:
    return ProviderManagementService(
        providers=SqlAlchemyProviderRepository(session=session),
        credentials=SqlAlchemyCredentialRepository(session=session),
        vault=FernetCredentialVault(),
    )


def build_quota_intelligence_engine(session: AsyncSession) -> QuotaIntelligenceEngine:
    return QuotaIntelligenceEngine(
        providers=SqlAlchemyProviderRepository(session=session),
        usage=SqlAlchemyUsageRepository(session=session),
    )


def build_health_intelligence_engine(session: AsyncSession) -> HealthIntelligenceEngine:
    return HealthIntelligenceEngine(
        health=SqlAlchemyHealthRepository(session=session),
        health_state=SqlAlchemyHealthStateRepository(session=session),
        incidents=SqlAlchemyIncidentRepository(session=session),
        usage=SqlAlchemyUsageRepository(session=session),
    )


def build_feature_flag_service(session: AsyncSession) -> FeatureFlagService:
    return FeatureFlagService(flags=SqlAlchemyFeatureFlagRepository(session=session))


def build_feature_lineage_service(session: AsyncSession) -> FeatureLineageService:
    return FeatureLineageService(
        lineage=SqlAlchemyFeatureLineageRepository(session=session),
        definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
    )


def build_feature_registration_service(session: AsyncSession) -> FeatureRegistrationService:
    return FeatureRegistrationService(
        definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
        versions=SqlAlchemyFeatureVersionRepository(session=session),
        lineage=build_feature_lineage_service(session),
    )


@lru_cache
def get_redis_client():
    return build_redis_client()


def build_feature_store_service(session: AsyncSession) -> FeatureStoreService:
    return FeatureStoreService(
        definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
        offline=SqlAlchemyFeatureValueRepository(session=session),
        online=RedisFeatureStore(client=get_redis_client()),
        # Phase 2 audit fix — same process-wide breaker SportsProviderRouter already uses for
        # provider calls, keyed separately ("feature_store:online" vs a provider key) so the two
        # never collide. See FeatureStoreService's own docstring for why this matters.
        circuit_breaker=get_circuit_breaker(),
    )


@dataclass
class AdminProviderReliabilityAdapter:
    """Implements modules.features.ports.provider_reliability.ProviderReliabilityPort by
    delegating to modules.admin's HealthIntelligenceEngine — the composition root is where
    this cross-module wiring happens, not inside modules/features itself (docs/decisions.md
    ADR-016, docs/architecture.md §5b)."""

    session: AsyncSession

    async def reliability_score(self, provider_key: str, now: datetime) -> float | None:
        provider = await SqlAlchemyProviderRepository(session=self.session).get_by_key(provider_key)
        if provider is None:
            return None
        engine = build_health_intelligence_engine(self.session)
        return await engine.reliability_score(provider.id, now)


def build_feature_quality_engine(session: AsyncSession) -> FeatureQualityEngine:
    return FeatureQualityEngine(
        definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
        values=SqlAlchemyFeatureValueRepository(session=session),
        reports=SqlAlchemyFeatureValidationReportRepository(session=session),
        computation_logs=SqlAlchemyFeatureComputationLogRepository(session=session),
        consumers=SqlAlchemyFeatureConsumerRepository(session=session),
        usage=SqlAlchemyFeatureUsageRepository(session=session),
        provider_reliability_port=AdminProviderReliabilityAdapter(session=session),
    )


# -- Milestone 5: Sports Data Ingestion Platform -------------------------------------------------


def build_kg_population_service(session: AsyncSession) -> KnowledgeGraphPopulationService:
    return KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )


# -- Milestone 7: Sports Semantic Intelligence Platform ------------------------------------------


def build_graph_query_service(session: AsyncSession) -> GraphQueryService:
    return GraphQueryService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )


def build_semantic_search_service(session: AsyncSession) -> SemanticSearchService:
    return SemanticSearchService(query=build_graph_query_service(session))


def build_context_engine(session: AsyncSession) -> ContextEngine:
    return ContextEngine(query=build_graph_query_service(session), nodes=SqlAlchemyKGNodeRepository(session=session))


def build_similarity_service(session: AsyncSession) -> SimilarityService:
    query = build_graph_query_service(session)
    return SimilarityService(
        similarity_port=GraphStructuralSimilarity(query=query),
        population=build_kg_population_service(session),
        nodes=SqlAlchemyKGNodeRepository(session=session),
    )


def build_graph_monitoring_service(session: AsyncSession) -> GraphMonitoringService:
    return GraphMonitoringService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )


PROVIDER_KEY_BY_SPORT = {"football": "api_football", "basketball": "api_basketball", "baseball": "api_baseball"}


def build_entity_reconciliation_service(session: AsyncSession) -> EntityReconciliationService:
    return EntityReconciliationService(
        sports=SqlAlchemySportRepository(session=session),
        countries=SqlAlchemyCountryRepository(session=session),
        competitions=SqlAlchemyCompetitionRepository(session=session),
        seasons=SqlAlchemySeasonRepository(session=session),
        venues=SqlAlchemyVenueRepository(session=session),
        teams=SqlAlchemyTeamRepository(session=session),
        players=SqlAlchemyPlayerRepository(session=session),
        fixtures=SqlAlchemyFixtureRepository(session=session),
        matches=SqlAlchemyMatchRepository(session=session),
        team_statistics=SqlAlchemyTeamStatisticsRepository(session=session),
        lineups=SqlAlchemyLineupRepository(session=session),
        standings=SqlAlchemyStandingRepository(session=session),
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        coaching_staff=SqlAlchemyCoachingStaffRepository(session=session),
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=build_kg_population_service(session),
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        alerts=build_alert_service(session),
        outcome_resolver=build_outcome_resolution_service(session),
        form_differential_calculators={
            "football": build_football_form_differential_calculators(session),
            "basketball": build_basketball_form_differential_calculators(session),
            "baseball": build_baseball_form_differential_calculators(session),
        },
        lineup_continuity_calculators={"football": build_football_lineup_continuity_calculators(session)},
        transfer_activity_calculators={"football": build_football_transfer_activity_calculators(session)},
        news_market_impact_engines={"football": build_football_news_market_impact_engine(session)},
        team_form_calculators=_build_team_form_calculators(session),
    )


def _build_team_form_calculators(session: AsyncSession) -> dict[str, tuple]:
    """Premier League data-enrichment audit (2026-08-22) — one `RollingTeamStatAverageCalculator`
    per sport, reusing the exact same `*_form_calculator` factories the market seeders already
    use (`football_form_calculator` etc., below) rather than defining a second set of
    feature_key/stat_key choices. Every sport with a seeder-registered form calculator gets one
    here too, not just football — a team's own rolling form is a real post-match signal
    regardless of which sport is still under active development."""
    team_statistics = SqlAlchemyTeamStatisticsRepository(session=session)
    registration = build_feature_registration_service(session)
    store = build_feature_store_service(session)
    return {
        "football": (football_form_calculator(registration, store, team_statistics),),
        "basketball": (basketball_form_calculator(registration, store, team_statistics),),
        "baseball": (baseball_form_calculator(registration, store, team_statistics),),
        "table_tennis": (table_tennis_form_calculator(registration, store, team_statistics),),
    }


def build_historical_import_service(session: AsyncSession) -> HistoricalImportService:
    """POST-M24 Phase 4 — reuses `build_entity_reconciliation_service` and `SqlAlchemySyncRunRepository`
    verbatim; adds no new repositories or reconciliation logic of its own. POST-M24 Phase 12 —
    `market_lines` wires the existing (previously never-called) `SqlAlchemyMarketLineRepository` so
    a source's real historical odds (`HistoricalFixtureRecord.odds`) can be written, reusing the
    exact `FixtureId` this same service's own reconciliation resolves — no second write path."""
    return HistoricalImportService(
        reconciler=build_entity_reconciliation_service(session),
        sync_runs=SqlAlchemySyncRunRepository(session=session),
        market_lines=SqlAlchemyMarketLineRepository(session=session),
    )


def build_outcome_resolution_service(session: AsyncSession) -> OutcomeResolutionService:
    return OutcomeResolutionService(
        predictions=SqlAlchemyPredictionRepository(session=session),
        markets=SqlAlchemyMarketRepository(session=session),
        outcomes=SqlAlchemyPredictionOutcomeRepository(session=session),
    )


def build_ingestion_quality_engine(session: AsyncSession) -> IngestionQualityEngine:
    return IngestionQualityEngine(
        sync_runs=SqlAlchemySyncRunRepository(session=session),
        reports=SqlAlchemyDataQualityReportRepository(session=session),
        provider_quality_port=AdminProviderReliabilityAdapter(session=session),
    )


def _make_api_key_getter(admin_service: ProviderManagementService, provider_key: str) -> Callable[[], Awaitable[str]]:
    async def _get() -> str:
        provider = await admin_service.providers.get_by_key(provider_key)
        credentials = await admin_service.usable_credentials(provider.id)
        return await admin_service.reveal_plaintext(credentials[0].id)

    return _get


FOOTBALL_DATA_ORG_PROVIDER_KEY = "football_data_org"


def build_football_data_org_adapter(session: AsyncSession) -> FootballDataOrgAdapter:
    admin_service = build_provider_management_service(session)
    return FootballDataOrgAdapter(get_api_key=_make_api_key_getter(admin_service, FOOTBALL_DATA_ORG_PROVIDER_KEY))


def get_football_data_org_adapter(session: AsyncSession) -> FootballDataOrgAdapter:
    """Alias kept for call sites (admin endpoints) that only need the adapter directly, not the
    full router — same construction as `build_football_data_org_adapter`, just named for its
    "get me the thing" use rather than "build me a wired-up service" use."""
    return build_football_data_org_adapter(session)


THESPORTSDB_PROVIDER_KEY = "thesportsdb"

def build_thesportsdb_adapter(session: AsyncSession) -> TheSportsDbAdapter:
    admin_service = build_provider_management_service(session)
    return TheSportsDbAdapter(get_api_key=_make_api_key_getter(admin_service, THESPORTSDB_PROVIDER_KEY))

def build_competition_fixture_source_repository(session: AsyncSession) -> SqlAlchemyCompetitionFixtureSourceRepository:
    return SqlAlchemyCompetitionFixtureSourceRepository(session=session)


def build_cross_provider_team_mapping_service(session: AsyncSession) -> CrossProviderTeamMappingService:
    return CrossProviderTeamMappingService(ref_index=SqlAlchemyProviderRefIndexRepository(session=session))


def build_sports_provider_router(session: AsyncSession) -> SportsProviderRouter:
    admin_service = build_provider_management_service(session)
    real_adapters = {
        "football": ApiFootballAdapter(get_api_key=_make_api_key_getter(admin_service, PROVIDER_KEY_BY_SPORT["football"])),
        "basketball": ApiBasketballAdapter(get_api_key=_make_api_key_getter(admin_service, PROVIDER_KEY_BY_SPORT["basketball"])),
        "baseball": ApiBaseballAdapter(get_api_key=_make_api_key_getter(admin_service, PROVIDER_KEY_BY_SPORT["baseball"])),
    }
    mock_adapters = {
        "football": MockSportsDataProvider(provider_key="api_football", sport_code="football"),
        "basketball": MockSportsDataProvider(provider_key="api_basketball", sport_code="basketball"),
        "baseball": MockSportsDataProvider(provider_key="api_baseball", sport_code="baseball"),
        "table_tennis": MockSportsDataProvider(provider_key="mock_table_tennis", sport_code="table_tennis"),
    }
    fixture_schedule_adapters = {
        FOOTBALL_DATA_ORG_PROVIDER_KEY: build_football_data_org_adapter(session),
        THESPORTSDB_PROVIDER_KEY: build_thesportsdb_adapter(session),
    }
    return SportsProviderRouter(
        admin_service=admin_service, quota_engine=build_quota_intelligence_engine(session),
        circuit_breaker=get_circuit_breaker(), real_adapters=real_adapters, mock_adapters=mock_adapters,
        fixture_schedule_adapters=fixture_schedule_adapters,
        # POST-M24 Phase 2: the same Redis-backed cache/lock singletons SyncOrchestrator already
        # uses (below) — a cache write from one Celery worker is now visible to every other
        # worker, and concurrent identical requests are deduplicated, instead of each worker
        # process holding its own invisible-to-everyone-else in-memory cache.
        cache=get_redis_sync_cache(), lock=get_redis_lock(),
    )


def build_capability_resolver(session: AsyncSession) -> CapabilityResolver:
    """POST-M24 Phase 3 — a new, additive query service. Does not replace
    `SportsProviderRouter._resolve_adapter`'s existing selection (unchanged since Phase 2); reuses
    the exact same `ProviderManagementService`/`CircuitBreaker`/`QuotaIntelligenceEngine`/
    `CompetitionFixtureSourceRepositoryPort` instances that router already depends on."""
    return CapabilityResolver(
        admin_service=build_provider_management_service(session),
        circuit_breaker=get_circuit_breaker(),
        quota_engine=build_quota_intelligence_engine(session),
        fixture_source_preferences=build_competition_fixture_source_repository(session),
    )


def build_source_selection_service(session: AsyncSession) -> SourceSelectionService:
    return SourceSelectionService(resolver=build_capability_resolver(session))


@lru_cache
def get_redis_lock():
    return RedisDistributedLock(client=get_redis_client())


@lru_cache
def get_redis_sync_cache():
    return RedisSyncCache(client=get_redis_client())


def build_sync_orchestrator(session: AsyncSession) -> SyncOrchestrator:
    return SyncOrchestrator(
        router=build_sports_provider_router(session),
        validator=DataValidationEngine(),
        quality=build_ingestion_quality_engine(session),
        reconciler=build_entity_reconciliation_service(session),
        sports=SqlAlchemySportRepository(session=session),
        checkpoints=SqlAlchemySyncCheckpointRepository(session=session),
        sync_runs=SqlAlchemySyncRunRepository(session=session),
        timeline=SqlAlchemyTimelineEventRepository(session=session),
        lock=get_redis_lock(),
        cache=get_redis_sync_cache(),
        odds_feature_writers={"football": build_football_odds_feature_writer(session)},
        fixture_source_preferences=build_competition_fixture_source_repository(session),
        supplementary_provider_keys=frozenset({THESPORTSDB_PROVIDER_KEY}),
    )


def build_monitoring_service(session: AsyncSession) -> MonitoringService:
    return MonitoringService(sync_runs=SqlAlchemySyncRunRepository(session=session))


# -- Milestone 6: Enterprise Supabase Platform & Identity ----------------------------------------


def build_identity_service(session: AsyncSession) -> IdentityService:
    return IdentityService(
        users=SqlAlchemyUserRepository(session=session),
        federated_identities=SqlAlchemyFederatedIdentityRepository(session=session),
        tokens=SqlAlchemyPersonalAccessTokenRepository(session=session),
        sessions=SqlAlchemySessionRepository(session=session),
        security_events=SqlAlchemySecurityEventRepository(session=session),
        account_locks=SqlAlchemyAccountLockRepository(session=session),
        audit_log=SqlAlchemyAuditLogRepository(session=session),
        password_hasher=BcryptPasswordHasher(),
        token_hasher=Sha256TokenHasher(),
    )


def build_tenancy_service(session: AsyncSession) -> TenancyService:
    return TenancyService(
        organizations=SqlAlchemyOrganizationRepository(session=session),
        teams=SqlAlchemyTenancyTeamRepository(session=session),
        memberships=SqlAlchemyMembershipRepository(session=session),
        invitations=SqlAlchemyInvitationRepository(session=session),
        audit_log=SqlAlchemyAuditLogRepository(session=session),
        token_hasher=Sha256TokenHasher(),
    )


def build_billing_service(session: AsyncSession) -> BillingService:
    return BillingService(
        plans=SqlAlchemyPlanRepository(session=session),
        entitlements=SqlAlchemyEntitlementRepository(session=session),
        subscriptions=SqlAlchemySubscriptionRepository(session=session),
        usage_counters=SqlAlchemyUsageCounterRepository(session=session),
        audit_log=SqlAlchemyAuditLogRepository(session=session),
    )


FLUTTERWAVE_PROVIDER_KEY = "flutterwave"


def _make_credential_getter_by_label(
    admin_service: ProviderManagementService, provider_key: str
) -> Callable[[str], Awaitable[str | None]]:
    """Like `_make_api_key_getter` but for a provider with multiple named credentials (client_id,
    client_secret, encryption_key, webhook_secret_hash) rather than one single API key — looks up
    by normalized label instead of always taking the first active credential."""

    async def _get(label: str) -> str | None:
        provider = await admin_service.providers.get_by_key(provider_key)
        if provider is None:
            return None
        usable = await admin_service.usable_credentials(provider.id)
        match = next((c for c in usable if normalize_credential_label(c.label) == label), None)
        return await admin_service.reveal_plaintext(match.id) if match else None

    return _get


def build_flutterwave_payment_provider(session: AsyncSession) -> FlutterwavePaymentProvider:
    admin_service = build_provider_management_service(session)
    return FlutterwavePaymentProvider(
        get_credential=_make_credential_getter_by_label(admin_service, FLUTTERWAVE_PROVIDER_KEY)
    )


def build_checkout_service(session: AsyncSession) -> CheckoutService:
    return CheckoutService(
        billing=build_billing_service(session),
        provider=build_flutterwave_payment_provider(session),
        pending_checkouts=SqlAlchemyPendingCheckoutRepository(session=session),
        processed_events=SqlAlchemyProcessedPaymentEventRepository(session=session),
    )


def build_webhook_service(session: AsyncSession) -> WebhookService:
    return WebhookService(
        endpoints=SqlAlchemyWebhookEndpointRepository(session=session),
        deliveries=SqlAlchemyWebhookDeliveryRepository(session=session),
        vault=FernetCredentialVault(),
    )


def build_watchlist_service(session: AsyncSession) -> WatchlistService:
    return WatchlistService(repository=SqlAlchemyWatchlistRepository(session=session))


def build_alert_service(session: AsyncSession) -> AlertService:
    return AlertService(
        events=SqlAlchemyAlertEventRepository(session=session),
        watchlist=SqlAlchemyWatchlistRepository(session=session),
    )


# -- Milestone 8: News Intelligence & Community Intelligence Platform ----------------------------


def get_text_intelligence_provider(session: AsyncSession) -> TextIntelligenceProviderPort:
    """Real `GeminiAdapter` when an active, credentialed "gemini" provider is registered via the
    Provider Management System; `MockGeminiAdapter` otherwise — resolved per call by
    `TextIntelligenceRouter`, not once here, so a credential added/disabled after startup takes
    effect immediately (docs/decisions.md ADR-008 follow-up; previously hardcoded to the mock
    adapter permanently, even once a working key existed)."""
    admin_service = build_provider_management_service(session)
    return TextIntelligenceRouter(
        admin_service=admin_service,
        real_adapter=GeminiAdapter(
            get_api_key=_make_api_key_getter(admin_service, GeminiAdapter.provider_key),
            metrics_recorder=get_intelligence_metrics_recorder(),
        ),
        mock_adapter=MockGeminiAdapter(),
    )


def build_news_ingestion_service(session: AsyncSession) -> NewsIngestionService:
    # Real, working RSS/Atom adapter (no paid API key required) — registered under the
    # `rss_feed` NewsSourceType value, the only key `NewsIngestionService._resolve_provider`
    # looks up for a source of that type. Other source types (official club sites, sports
    # news APIs) have no adapter yet; sources of those types will raise on sync until one
    # is added, which is correct — no silent mock fallback for a real ingestion pipeline.
    return NewsIngestionService(
        sources=SqlAlchemyNewsSourceRepository(session=session),
        articles=SqlAlchemyNewsArticleRepository(session=session),
        checkpoints=SqlAlchemyIntelligenceSyncCheckpointRepository(session=session),
        sync_runs=SqlAlchemyIntelligenceSyncRunRepository(session=session),
        providers={"rss_feed": RssNewsProvider()},
    )


def build_community_ingestion_service(session: AsyncSession) -> CommunityIngestionService:
    return CommunityIngestionService(
        posts=SqlAlchemyCommunityPostRepository(session=session),
        checkpoints=SqlAlchemyIntelligenceSyncCheckpointRepository(session=session),
        sync_runs=SqlAlchemyIntelligenceSyncRunRepository(session=session),
    )


def build_entity_extraction_service(session: AsyncSession) -> EntityExtractionService:
    nodes = SqlAlchemyKGNodeRepository(session=session)
    edges = SqlAlchemyKGEdgeRepository(session=session)
    resolution = EntityResolutionService(
        nodes=nodes, edges=edges, population=KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    )
    return EntityExtractionService(text_intelligence=get_text_intelligence_provider(session), entity_resolution=resolution)


def build_event_extraction_service(session: AsyncSession) -> EventExtractionService:
    return EventExtractionService(
        text_intelligence=get_text_intelligence_provider(session),
        entity_extraction=build_entity_extraction_service(session),
        events=SqlAlchemyNewsEventRepository(session=session),
    )


def build_source_reliability_service(session: AsyncSession) -> SourceReliabilityService:
    return SourceReliabilityService(reliability=SqlAlchemySourceReliabilityRepository(session=session))


def build_sentiment_service(session: AsyncSession) -> SentimentService:
    return SentimentService(
        text_intelligence=get_text_intelligence_provider(session), results=SqlAlchemySentimentResultRepository(session=session)
    )


def build_news_impact_engine(session: AsyncSession) -> NewsImpactEngine:
    return NewsImpactEngine(
        impact_scores=SqlAlchemyImpactScoreRepository(session=session),
        sentiment_results=SqlAlchemySentimentResultRepository(session=session),
        kg_nodes=SqlAlchemyKGNodeRepository(session=session),
    )


def build_summarization_service(session: AsyncSession) -> SummarizationService:
    return SummarizationService(
        text_intelligence=get_text_intelligence_provider(session), summaries=SqlAlchemySummaryRepository(session=session)
    )


def build_intelligence_kg_enrichment_service(session: AsyncSession) -> KnowledgeGraphEnrichmentService:
    nodes = SqlAlchemyKGNodeRepository(session=session)
    edges = SqlAlchemyKGEdgeRepository(session=session)
    population = KnowledgeGraphPopulationService(nodes=nodes, edges=edges)
    query = build_graph_query_service(session)
    return KnowledgeGraphEnrichmentService(
        population=population, temporal=TemporalGraphService(query=query, edges=edges, population=population), nodes=nodes
    )


def build_feature_store_enrichment_service(session: AsyncSession) -> FeatureStoreEnrichmentService:
    return FeatureStoreEnrichmentService(
        registration=build_feature_registration_service(session), store=build_feature_store_service(session)
    )


def build_intelligence_enrichment_orchestrator(session: AsyncSession) -> IntelligenceEnrichmentOrchestrator:
    return IntelligenceEnrichmentOrchestrator(
        event_extraction=build_event_extraction_service(session),
        news_impact=build_news_impact_engine(session),
        source_reliability=build_source_reliability_service(session),
        feature_store=build_feature_store_enrichment_service(session),
        sources=SqlAlchemyNewsSourceRepository(session=session),
        events=SqlAlchemyNewsEventRepository(session=session),
        kg_enrichment=build_intelligence_kg_enrichment_service(session),
    )


def build_scheduled_news_sync_service(session: AsyncSession) -> ScheduledNewsSyncService:
    """Milestone 10 — composes the real ingestion + enrichment pipeline behind the one Celery
    task allowed to ever produce SyncTrigger.LIVE_SCHEDULED news provenance."""
    return ScheduledNewsSyncService(
        news_ingestion=build_news_ingestion_service(session),
        enrichment=build_intelligence_enrichment_orchestrator(session),
        fixtures=SqlAlchemyFixtureRepository(session=session),
        teams=SqlAlchemyTeamRepository(session=session),
        players=SqlAlchemyPlayerRepository(session=session),
        kg_nodes=SqlAlchemyKGNodeRepository(session=session),
    )


def build_historical_entity_resolution_service(session: AsyncSession) -> HistoricalEntityResolutionService:
    """Milestone 13 — point-in-time player->team membership, reconstructed exclusively from
    `Transfer.effective_date` chains. Never wired to `Player.team_id` or Knowledge Graph
    `PLAYS_FOR` edges — the M13 audit confirmed neither is a reliable historical source."""
    return HistoricalEntityResolutionService(transfers=SqlAlchemyTransferRepository(session=session))


def _market_rule_exists(event_type, market_key: str) -> bool:
    """Milestone 13 — the real `market_rule_exists` implementation, composed here (not inside
    `modules.intelligence`) so that module keeps its existing one-directional boundary: it has
    never imported `modules.predictions`, and this milestone does not change that. Queries
    Milestone 9's `MARKET_IMPACT_RULES` read-only — never redesigns the market-impact system."""
    from modules.predictions.application.news_market_impact_registry import MARKET_IMPACT_RULES

    return any(rule.event_type is event_type and rule.market_key == market_key for rule in MARKET_IMPACT_RULES)


def build_historical_news_relevance_engine(session: AsyncSession) -> HistoricalNewsRelevanceEngine:
    """Milestone 13 — Mode 2 (historical reconstruction) relevance, a sibling to
    `build_scheduled_news_sync_service`'s Mode 1 vocabulary, never a replacement for it."""
    return HistoricalNewsRelevanceEngine(
        kg_nodes=SqlAlchemyKGNodeRepository(session=session),
        entity_resolution=build_historical_entity_resolution_service(session),
        market_rule_exists=_market_rule_exists,
    )


def build_news_backfill_service(session: AsyncSession) -> NewsBackfillService:
    """Milestone 12 — composes the same real ingestion + enrichment pipeline behind the
    administrator-only, dry-run-by-default BACKFILL entry point. Reuses NewsIngestionService/
    IntelligenceEnrichmentOrchestrator exactly as built above; SyncTrigger.BACKFILL is the only
    difference, and it is never eligible to produce VERIFIED_PRE_MATCH provenance."""
    return NewsBackfillService(
        news_ingestion=build_news_ingestion_service(session),
        enrichment=build_intelligence_enrichment_orchestrator(session),
        fixtures=SqlAlchemyFixtureRepository(session=session),
        teams=SqlAlchemyTeamRepository(session=session),
        players=SqlAlchemyPlayerRepository(session=session),
        kg_nodes=SqlAlchemyKGNodeRepository(session=session),
    )


def build_intelligence_retrieval_service(session: AsyncSession) -> IntelligenceRetrievalService:
    nodes = SqlAlchemyKGNodeRepository(session=session)
    edges = SqlAlchemyKGEdgeRepository(session=session)
    graph_query = GraphQueryService(nodes=nodes, edges=edges)
    return IntelligenceRetrievalService(
        news=NewsRetrieval(events=SqlAlchemyNewsEventRepository(session=session)),
        community=CommunityRetrieval(posts=SqlAlchemyCommunityPostRepository(session=session)),
        knowledge_graph=KnowledgeGraphRetrievalAdapter(
            graph_retrieval=GraphNativeRetrieval(query=graph_query), nodes=nodes
        ),
        ai_reports=AIReportRetrieval(summaries=SqlAlchemySummaryRepository(session=session)),
        team_names=MatchTeamNamesResolver(nodes=nodes, query=graph_query),
    )


def build_intelligence_monitoring_service(session: AsyncSession) -> IntelligenceMonitoringService:
    return IntelligenceMonitoringService(
        sync_runs=SqlAlchemyIntelligenceSyncRunRepository(session=session),
        articles=SqlAlchemyNewsArticleRepository(session=session),
        community_posts=SqlAlchemyCommunityPostRepository(session=session),
        source_reliability=SqlAlchemySourceReliabilityRepository(session=session),
        recorder=get_intelligence_metrics_recorder(),
    )


# -- Milestone 9: Prediction Intelligence Platform ------------------------------------------------


def build_market_registry_service(session: AsyncSession) -> MarketRegistryService:
    return MarketRegistryService(
        markets=SqlAlchemyMarketRepository(session=session),
        feature_mappings=SqlAlchemyFeatureMarketMappingRepository(session=session),
    )


def build_model_registry_service(session: AsyncSession) -> ModelRegistryService:
    return ModelRegistryService(models=SqlAlchemyModelRepository(session=session))


def build_feature_market_mapping_service(session: AsyncSession) -> FeatureMarketMappingService:
    return FeatureMarketMappingService(
        mappings=SqlAlchemyFeatureMarketMappingRepository(session=session),
        markets=SqlAlchemyMarketRepository(session=session),
        feature_definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
    )


@lru_cache
def get_predictor_registry() -> PredictorRegistry:
    """Formula-fallback predictors for markets whose Champion has no real trained artifact yet.
    ML-architecture consolidation (2026-08-04): this registry no longer contains a Poisson (or
    any other single-purpose statistical) predictor — `football.correct_score` and the eleven
    Over/Under-style markets that used to fall back to one now have NO entry here at all (see
    `scripts/seed_football_markets.py`'s `NOT_YET_TRAINED_MARKET_KEYS`) and never reach this
    registry in the first place: `PredictionContextBuilder.build()` raises `NoChampionModelError`
    for them until a real trained model exists, which the API surfaces as an honest "insufficient
    historical data" response rather than silently substituting a formula guess. The remaining
    three generic weighted predictors stay the production path for every other market kind."""
    registry = PredictorRegistry()
    registry.register_many(WeightedLogisticPredictor.SUPPORTED_KINDS, WeightedLogisticPredictor())
    registry.register_many(WeightedLinearPredictor.SUPPORTED_KINDS, WeightedLinearPredictor())
    registry.register_many(WeightedOrdinalPredictor.SUPPORTED_KINDS, WeightedOrdinalPredictor())
    return registry


def build_calibrator(session: AsyncSession) -> CalibratorPort:
    """Phase 3 audit fix: the previous `@lru_cache` process-wide singleton kept fitted parameters
    in memory only — a Celery worker's `fit()` never reached the API process's own instance
    (documented bug, `calibration_fitting_service.py`'s own "Deployment-topology note"). Now
    session-scoped and backed by `SqlAlchemyCalibrationParametersRepository`: a fit from any
    process reaches every process's `calibrate()` on its next cache miss, via the DB."""
    return PlattScalingCalibrator(repository=SqlAlchemyCalibrationParametersRepository(session=session))


@lru_cache
def get_confidence_engine() -> ConfidenceEngine:
    return ConfidenceEngine()


def build_explainability_engine(session: AsyncSession) -> ExplainabilityEngine:
    return ExplainabilityEngine(
        retrieval=build_intelligence_retrieval_service(session), text_intelligence=get_text_intelligence_provider(session),
        cache=get_redis_sync_cache(),
    )


def build_prediction_context_builder(session: AsyncSession) -> PredictionContextBuilder:
    return PredictionContextBuilder(
        markets=SqlAlchemyMarketRepository(session=session),
        models=SqlAlchemyModelRepository(session=session),
        mapping_service=build_feature_market_mapping_service(session),
        feature_values=SqlAlchemyFeatureValueRepository(session=session),
        definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
    )


def build_prediction_engine(session: AsyncSession) -> PredictionEngine:
    return PredictionEngine(
        context_builder=build_prediction_context_builder(session),
        predictors=get_predictor_registry(),
        calibrator=build_calibrator(session),
        confidence_engine=get_confidence_engine(),
        explainability_engine=build_explainability_engine(session),
        retrieval=build_intelligence_retrieval_service(session),
        outcomes=SqlAlchemyPredictionOutcomeRepository(session=session),
        model_evaluations=SqlAlchemyModelEvaluationRepository(session=session),
        predictions=SqlAlchemyPredictionRepository(session=session),
        model_loader=get_model_loader_service(),
    )


def build_prediction_cache_service(session: AsyncSession) -> PredictionCacheService:
    return PredictionCacheService(
        engine=build_prediction_engine(session),
        markets=SqlAlchemyMarketRepository(session=session),
        predictions=SqlAlchemyPredictionRepository(session=session),
        audits=SqlAlchemyPredictionAuditRepository(session=session),
        alerts=build_alert_service(session),
    )


def build_prediction_admin_service(session: AsyncSession) -> PredictionAdminService:
    return PredictionAdminService(
        markets=SqlAlchemyMarketRepository(session=session),
        models=SqlAlchemyModelRepository(session=session),
        predictions=SqlAlchemyPredictionRepository(session=session),
        outcomes=SqlAlchemyPredictionOutcomeRepository(session=session),
    )


def build_error_memory_service(session: AsyncSession) -> ErrorMemoryService:
    return ErrorMemoryService(
        markets=SqlAlchemyMarketRepository(session=session),
        models=SqlAlchemyModelRepository(session=session),
        predictions=SqlAlchemyPredictionRepository(session=session),
        outcomes=SqlAlchemyPredictionOutcomeRepository(session=session),
        model_evaluations=SqlAlchemyModelEvaluationRepository(session=session),
    )


def build_experiment_repository(session: AsyncSession) -> SqlAlchemyExperimentRepository:
    return SqlAlchemyExperimentRepository(session=session)


def build_prediction_audit_repository(session: AsyncSession) -> SqlAlchemyPredictionAuditRepository:
    return SqlAlchemyPredictionAuditRepository(session=session)


# --- Milestone 9.1 Enterprise ML Platform composition ---------------------------------------


def build_dataset_repo(session: AsyncSession) -> DatasetRepositoryPort:
    """Milestone 20: durable, SQL-backed (`SqlAlchemyDatasetRepository` against the `datasets`
    table, which has existed unused since Milestone 4/9) — closes the `dataset_provenance_persisted`
    gap `TrainingPreflightService` (Milestone 19) identified. Session-scoped like every other
    `Sql*Repository` factory in this module, not a process-wide singleton — the previous
    `InMemoryDatasetRepository()` posture (docs/decisions.md ADR-008) is retired for production
    wiring; `InMemoryDatasetRepository` itself is untouched and still available for tests."""
    return SqlAlchemyDatasetRepository(session=session)


def build_model_comparison_repo(session: AsyncSession) -> ModelComparisonRepositoryPort:
    """Phase 3 audit fix: SQL-backed (`challenger_evaluations` table), session-scoped like every
    other `Sql*Repository` factory in this module — replaces the previous process-wide
    `InMemoryModelComparisonRepository()` singleton, whose Continuous Outcome Learning Engine
    Challenger-vs-Champion verdicts were lost on every worker restart (the only comparison
    artifact in this schema that wasn't already durable)."""
    return SqlAlchemyModelComparisonRepository(session=session)


@lru_cache
def get_latency_repo() -> LatencySampleRepositoryPort:
    return InMemoryLatencySampleRepository()


@lru_cache
def get_model_artifact_store() -> ModelArtifactStorePort:
    return LocalFilesystemArtifactStore()


@lru_cache
def get_model_loader_service() -> ModelLoaderService:
    return ModelLoaderService(artifact_store=get_model_artifact_store())


def build_statistical_baseline_provider(session: AsyncSession) -> StatisticalBaselineProvider:
    return StatisticalBaselineProvider(
        markets=SqlAlchemyMarketRepository(session=session),
        models=SqlAlchemyModelRepository(session=session),
        model_loader=get_model_loader_service(),
    )


def build_goal_generative_comparison_service(session: AsyncSession) -> GoalGenerativeComparisonService:
    """Spec §9 "Cross-Architecture Validation" — compares the derived Poisson baseline
    (`StatisticalBaselineProvider`) against `football.match_winner`/`football.both_teams_to_score`'s
    own direct-classifier Champion using real resolved outcome history, recording the result as an
    `Experiment` rather than ever auto-promoting or auto-ensembling."""
    return GoalGenerativeComparisonService(
        models=SqlAlchemyModelRepository(session=session),
        predictions=SqlAlchemyPredictionRepository(session=session),
        outcomes=SqlAlchemyPredictionOutcomeRepository(session=session),
        baseline_provider=build_statistical_baseline_provider(session),
        experiments=build_experiment_repository(session),
    )


def build_live_evidence_gatherer(session: AsyncSession) -> LiveEvidenceGatherer:
    return LiveEvidenceGatherer(
        fixtures=SqlAlchemyFixtureRepository(session=session),
        news=SqlAlchemyNewsEventRepository(session=session),
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        lineups=SqlAlchemyLineupRepository(session=session),
    )


def build_prediction_consistency_gate(session: AsyncSession) -> PredictionConsistencyGate:
    """Pre-Gemini Prediction-Explanation Consistency Gate (spec §23) — shared by both opt-in
    explanation subsystems below, so a prediction that has drifted out of sync with the market's
    current state (a newer Champion since promoted, provenance gone missing, an empty feature
    snapshot, or a stale prediction) never reaches Gemini for narration."""
    return PredictionConsistencyGate(models=SqlAlchemyModelRepository(session=session))


def build_contextual_reasoning_service(session: AsyncSession) -> ContextualReasoningService:
    """Gemini Prediction Reasoning Engine — reuses the exact same real/mock Gemini resolution
    (`get_text_intelligence_provider`) and Redis sync cache (`get_redis_sync_cache`) every other
    intelligence/ingestion feature already depends on; no new external-facing infrastructure."""
    return ContextualReasoningService(
        baseline_provider=build_statistical_baseline_provider(session),
        evidence_gatherer=build_live_evidence_gatherer(session),
        text_intelligence=get_text_intelligence_provider(session),
        cache=get_redis_sync_cache(),
        context_reviews=SqlAlchemyContextReviewRepository(session=session),
        consistency_gate=build_prediction_consistency_gate(session),
    )


def build_football_explanation_service(session: AsyncSession) -> FootballExplanationService:
    """Sports-Analyst Explainability — reuses the same real/mock Gemini resolution
    (`get_text_intelligence_provider`) and `LiveEvidenceGatherer` every other intelligence
    feature already depends on; no new external-facing infrastructure. Distinct from
    `ContextualReasoningService` (news/injury reconsideration) — this answers "why did the model
    predict this," grounded in real per-instance model attribution."""
    return FootballExplanationService(
        attribution=ModelAttributionService(),
        evidence_gatherer=build_live_evidence_gatherer(session),
        model_loader=get_model_loader_service(),
        models=SqlAlchemyModelRepository(session=session),
        dataset_builder=build_dataset_builder(session),
        text_intelligence=get_text_intelligence_provider(session),
        explanations=SqlAlchemyFootballExplanationRepository(session=session),
        consistency_gate=build_prediction_consistency_gate(session),
        cache=get_redis_sync_cache(),
    )


@lru_cache
def get_isotonic_calibrator() -> IsotonicRegressionCalibrator:
    return IsotonicRegressionCalibrator()


@lru_cache
def get_temperature_calibrator() -> TemperatureScalingCalibrator:
    return TemperatureScalingCalibrator()


def build_dataset_registry_service(session: AsyncSession) -> DatasetRegistryService:
    return DatasetRegistryService(datasets=build_dataset_repo(session))


def build_dataset_builder(session: AsyncSession) -> DatasetBuilder:
    return DatasetBuilder(
        markets=SqlAlchemyMarketRepository(session=session),
        predictions=SqlAlchemyPredictionRepository(session=session),
        outcomes=SqlAlchemyPredictionOutcomeRepository(session=session),
    )


def build_calibration_validation_service(session: AsyncSession) -> CalibrationValidationService:
    """Phase 3 (Champion Validation + Calibration) — real sklearn `CalibratedClassifierCV`-based
    comparison, persisted `CalibrationReport`s, and versioned calibrated challengers. Independent
    of `build_calibrator()`'s `PlattScalingCalibrator` (a different, pre-existing, lighter-weight
    mechanism, now also DB-backed) — this service's decisions are durable model versions + DB
    rows, not per-process fitted parameters."""
    return CalibrationValidationService(
        dataset_builder=build_dataset_builder(session),
        model_loader=get_model_loader_service(),
        models=SqlAlchemyModelRepository(session=session),
        calibration_reports=SqlAlchemyCalibrationReportRepository(session=session),
        model_registry=build_model_registry_service(session),
        artifact_store=get_model_artifact_store(),
        markets=SqlAlchemyMarketRepository(session=session),
    )


def build_training_preflight_service(session: AsyncSession) -> TrainingPreflightService:
    return TrainingPreflightService(
        markets=SqlAlchemyMarketRepository(session=session),
        mappings=SqlAlchemyFeatureMarketMappingRepository(session=session),
        feature_definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
        dataset_builder=build_dataset_builder(session),
        dataset_repo=build_dataset_repo(session),
    )


def build_predictive_signal_audit_service(session: AsyncSession) -> PredictiveSignalAuditService:
    return PredictiveSignalAuditService(
        markets=SqlAlchemyMarketRepository(session=session),
        mappings=SqlAlchemyFeatureMarketMappingRepository(session=session),
        feature_definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
        dataset_repo=build_dataset_repo(session),
        models=SqlAlchemyModelRepository(session=session),
        model_evaluations=SqlAlchemyModelEvaluationRepository(session=session),
        predictions=SqlAlchemyPredictionRepository(session=session),
        outcomes=SqlAlchemyPredictionOutcomeRepository(session=session),
        experiments=build_experiment_repository(session),
        preflight=build_training_preflight_service(session),
    )


def build_experiment_tracking_service(session: AsyncSession) -> ExperimentTrackingService:
    return ExperimentTrackingService(experiments=build_experiment_repository(session))


def build_model_version_resolver(session: AsyncSession) -> ModelVersionResolver:
    return ModelVersionResolver(models=SqlAlchemyModelRepository(session=session))


def build_training_pipeline_service() -> TrainingPipelineService:
    return TrainingPipelineService()


def build_automatic_model_selection_service(session: AsyncSession) -> AutomaticModelSelectionService:
    return AutomaticModelSelectionService(
        training_pipeline=build_training_pipeline_service(),
        model_registry=build_model_registry_service(session),
        experiments=build_experiment_tracking_service(session),
        artifact_store=get_model_artifact_store(),
        feature_definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
        training_runs=SqlAlchemyTrainingRunRepository(session=session),
    )


def build_backtest_service() -> BacktestService:
    return BacktestService(evaluator=ChallengerEvaluationService())


def build_retraining_scheduler(session: AsyncSession) -> RetrainingScheduler:
    return RetrainingScheduler(dataset_registry=build_dataset_registry_service(session))


def build_scheduled_retraining_orchestrator(session: AsyncSession) -> ScheduledRetrainingOrchestrator:
    return ScheduledRetrainingOrchestrator(
        markets=SqlAlchemyMarketRepository(session=session),
        models=SqlAlchemyModelRepository(session=session),
        scheduler=build_retraining_scheduler(session),
        dataset_builder=build_dataset_builder(session),
        dataset_registry=build_dataset_registry_service(session),
        model_selection=build_automatic_model_selection_service(session),
        model_loader=get_model_loader_service(),
        evaluator=ChallengerEvaluationService(),
        comparisons=build_model_comparison_repo(session),
        preflight=build_training_preflight_service(session),
    )


def build_calibration_fitting_service(session: AsyncSession) -> CalibrationFittingService:
    return CalibrationFittingService(
        markets=SqlAlchemyMarketRepository(session=session),
        models=SqlAlchemyModelRepository(session=session),
        predictions=SqlAlchemyPredictionRepository(session=session),
        outcomes=SqlAlchemyPredictionOutcomeRepository(session=session),
        calibrator=build_calibrator(session),
    )


def build_model_monitoring_service(session: AsyncSession) -> ModelMonitoringService:
    return ModelMonitoringService(
        admin=build_prediction_admin_service(session),
        dataset_registry=build_dataset_registry_service(session),
        latency=get_latency_repo(),
        predictions=SqlAlchemyPredictionRepository(session=session),
        outcomes=SqlAlchemyPredictionOutcomeRepository(session=session),
    )


def build_batch_prediction_service(session: AsyncSession) -> BatchPredictionService:
    return BatchPredictionService(cache_service=build_prediction_cache_service(session))


@lru_cache
def get_async_prediction_queue_service() -> AsyncPredictionQueueService:
    """Process-wide singleton — the queue's pending/results state must survive across the
    `enqueue()` request and the later `process_next()`/poll requests, which are different HTTP
    calls. Each `process_next()` call is given a freshly-built, request-scoped
    `PredictionCacheService` (see that method's docstring) — this singleton holds no database
    session itself."""
    return AsyncPredictionQueueService()


def build_calibration_report_builder() -> CalibrationReportBuilder:
    return CalibrationReportBuilder()


@lru_cache
def get_shap_explainer_service() -> SHAPExplainerService:
    return SHAPExplainerService()


def build_football_form_differential_calculators(session: AsyncSession) -> tuple[FixtureFormDifferentialCalculator, ...]:
    return football_fixture_stat_differential_calculators(
        build_feature_registration_service(session),
        build_feature_store_service(session),
        SqlAlchemyTeamStatisticsRepository(session=session),
    )


def build_basketball_form_differential_calculators(session: AsyncSession) -> tuple[FixtureFormDifferentialCalculator, ...]:
    """POST-M24 Phase 5A — mirrors `build_football_form_differential_calculators`; a single
    points-differential calculator today (basketball has only one stat-differential feature
    declared so far, unlike football's multi-stat tuple)."""
    return (
        basketball_fixture_form_differential_calculator(
            build_feature_registration_service(session),
            build_feature_store_service(session),
            SqlAlchemyTeamStatisticsRepository(session=session),
        ),
    )


def build_baseball_form_differential_calculators(session: AsyncSession) -> tuple[FixtureFormDifferentialCalculator, ...]:
    """POST-M24 Phase 5A — mirrors `build_basketball_form_differential_calculators` above."""
    return (
        baseball_fixture_form_differential_calculator(
            build_feature_registration_service(session),
            build_feature_store_service(session),
            SqlAlchemyTeamStatisticsRepository(session=session),
        ),
    )


def build_football_lineup_continuity_calculators(session: AsyncSession) -> tuple[LineupContinuityCalculator, LineupContinuityCalculator]:
    return football_lineup_continuity_calculators(
        build_feature_registration_service(session),
        build_feature_store_service(session),
        SqlAlchemyLineupRepository(session=session),
    )


def build_football_transfer_activity_calculators(session: AsyncSession) -> tuple[TransferActivityCalculator, TransferActivityCalculator]:
    return football_transfer_activity_calculators(
        build_feature_registration_service(session),
        build_feature_store_service(session),
        SqlAlchemyTransferRepository(session=session),
    )


def build_football_news_market_impact_engine(session: AsyncSession) -> NewsMarketImpactEngine:
    return NewsMarketImpactEngine(
        registration=build_feature_registration_service(session),
        store=build_feature_store_service(session),
        events=SqlAlchemyNewsEventRepository(session=session),
        kg_nodes=SqlAlchemyKGNodeRepository(session=session),
        players=SqlAlchemyPlayerRepository(session=session),
        # Milestone 14 — wired unconditionally (harmless when unused: only consulted if a caller
        # passes `historical_reference_time`) so historical reconstruction is available wherever
        # this engine already is, with no separate composition path to keep in sync.
        transfers=SqlAlchemyTransferRepository(session=session),
        historical_entity_resolution=build_historical_entity_resolution_service(session),
        sport_code="football",
    )


def build_historical_feature_reconstruction_service(session: AsyncSession) -> HistoricalFeatureReconstructionService:
    """Milestone 14 — not wired into any live endpoint or Celery task; see
    docs/milestone14_verification_report.md's Known Limitations / Deferred Work. Milestone 15 wired
    it into scripts/backfill_both_teams_to_score_training_data.py (a one-off training script, not a
    live path)."""
    return HistoricalFeatureReconstructionService(
        news_market_impact=build_football_news_market_impact_engine(session),
        relevance_engine=build_historical_news_relevance_engine(session),
    )


def build_football_odds_feature_writer(session: AsyncSession) -> FootballOddsFeatureWriter:
    return football_odds_feature_writer(build_feature_store_service(session))


def build_football_expected_goals_calculator(session: AsyncSession) -> FixtureExpectedGoalsCalculator:
    return football_fixture_expected_goals_calculator(
        build_feature_registration_service(session),
        build_feature_store_service(session),
        SqlAlchemyFixtureRepository(session=session),
    )


def build_football_market_seeder(session: AsyncSession) -> FootballMarketSeeder:
    team_statistics = SqlAlchemyTeamStatisticsRepository(session=session)
    return FootballMarketSeeder(
        registration=build_feature_registration_service(session),
        markets=build_market_registry_service(session),
        mappings=build_feature_market_mapping_service(session),
        windowed_calculator=football_form_calculator(
            build_feature_registration_service(session), build_feature_store_service(session), team_statistics
        ),
        differential_calculators=build_football_form_differential_calculators(session),
        expected_goals_calculator=build_football_expected_goals_calculator(session),
        lineup_continuity_calculators=build_football_lineup_continuity_calculators(session),
        transfer_activity_calculators=build_football_transfer_activity_calculators(session),
        news_market_impact_engine=build_football_news_market_impact_engine(session),
    )


def build_basketball_market_seeder(session: AsyncSession) -> BasketballMarketSeeder:
    team_statistics = SqlAlchemyTeamStatisticsRepository(session=session)
    return BasketballMarketSeeder(
        registration=build_feature_registration_service(session),
        markets=build_market_registry_service(session),
        mappings=build_feature_market_mapping_service(session),
        windowed_calculator=basketball_form_calculator(
            build_feature_registration_service(session), build_feature_store_service(session), team_statistics
        ),
        differential_calculator=basketball_fixture_form_differential_calculator(
            build_feature_registration_service(session), build_feature_store_service(session), team_statistics
        ),
    )


def build_baseball_market_seeder(session: AsyncSession) -> BaseballMarketSeeder:
    team_statistics = SqlAlchemyTeamStatisticsRepository(session=session)
    return BaseballMarketSeeder(
        registration=build_feature_registration_service(session),
        markets=build_market_registry_service(session),
        mappings=build_feature_market_mapping_service(session),
        windowed_calculator=baseball_form_calculator(
            build_feature_registration_service(session), build_feature_store_service(session), team_statistics
        ),
        differential_calculator=baseball_fixture_form_differential_calculator(
            build_feature_registration_service(session), build_feature_store_service(session), team_statistics
        ),
    )


def build_table_tennis_market_seeder(session: AsyncSession) -> TableTennisMarketSeeder:
    team_statistics = SqlAlchemyTeamStatisticsRepository(session=session)
    return TableTennisMarketSeeder(
        registration=build_feature_registration_service(session),
        markets=build_market_registry_service(session),
        mappings=build_feature_market_mapping_service(session),
        windowed_calculator=table_tennis_form_calculator(
            build_feature_registration_service(session), build_feature_store_service(session), team_statistics
        ),
    )


@lru_cache
def get_jwt_validator() -> JWTValidatorPort:
    """Real Supabase JWKS validation when ``TITANIQ_SUPABASE_PROJECT_URL`` is configured;
    otherwise the caller is expected to be running fast offline tests / local dev without a
    live Supabase project, so no validator is constructed here — routes that need auth build
    their own ``MockJWTValidator`` in that environment (docs/decisions.md ADR-008 mock-first
    pattern, same as every other external-service port in this codebase)."""
    return SupabaseJWKSValidator()
