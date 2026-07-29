/**
 * Hand-written types mirroring the backend's `_serialize_*` dict shapes (apps/api/routers/*.py,
 * apps/api/main.py) — the backend defines no Pydantic *response* models (every response is a
 * plain dict built by a local `_serialize_*` function), so there is nothing to codegen from; these
 * types are kept in sync by hand against the router source, one interface per `_serialize_*`.
 */

export type Role =
  | 'guest'
  | 'free'
  | 'rewarded'
  | 'premium'
  | 'moderator'
  | 'analyst'
  | 'administrator'
  | 'super_administrator'

export const ROLE_LEVEL: Record<Role, number> = {
  guest: 0,
  free: 1,
  rewarded: 2,
  premium: 3,
  moderator: 4,
  analyst: 5,
  administrator: 6,
  super_administrator: 7,
}

export function isAtLeast(role: Role, minimum: Role): boolean {
  return ROLE_LEVEL[role] >= ROLE_LEVEL[minimum]
}

// -- identity ------------------------------------------------------------------------------

export interface UserDto {
  id: string
  email: string
  role: Role
  status: string
  email_verified: boolean
  created_at: string
  last_login_at: string | null
}

export interface SessionDto {
  id: string
  device_label: string | null
  ip_address: string | null
  risk_level: string
  created_at: string
  last_seen_at: string
}

export interface PersonalAccessTokenDto {
  id: string
  name: string
  scopes: string[]
  is_active: boolean
  created_at: string
  last_used_at: string | null
}

// -- tenancy --------------------------------------------------------------------------------

export type OrganizationRole = 'owner' | 'admin' | 'member'

export interface OrganizationDto {
  id: string
  name: string
  owner_id: string
  created_at: string
}

export interface TeamDto {
  id: string
  organization_id: string
  name: string
  created_at: string
}

export interface MembershipDto {
  organization_id: string
  user_id: string
  role: OrganizationRole
  joined_at: string
}

export interface InvitationDto {
  id: string
  organization_id: string
  email: string
  role: OrganizationRole
  status: string
  expires_at: string
}

// -- billing --------------------------------------------------------------------------------

export type PlanTier = 'free' | 'rewarded' | 'premium'
export type BillingPeriod = 'monthly' | 'annual'

export interface PlanDto {
  id: string
  key: string
  name: string
  tier: PlanTier
  billing_period: BillingPeriod
  price_cents: number
}

export interface SubscriptionDto {
  id: string
  subject_type: 'user' | 'organization'
  subject_id: string
  plan_key: string
  status: string
  started_at: string
  canceled_at: string | null
}

// -- webhooks -------------------------------------------------------------------------------

export interface WebhookEndpointDto {
  id: string
  organization_id: string
  url: string
  subscribed_events: string[]
  is_active: boolean
  created_at: string
}

export interface WebhookDeliveryDto {
  id: string
  endpoint_id: string
  event: string
  status: string
  attempted_at: string
  response_status: number | null
}

// -- knowledge graph --------------------------------------------------------------------------

export interface KgNodeDto {
  id: string
  node_type: string
  entity_ref: string
  attributes: Record<string, unknown>
}

export interface KgEdgeDto {
  edge_type: string
  from_node_id: string
  to_node_id: string
  attributes: Record<string, unknown>
}

export interface KgSubgraphDto {
  nodes: KgNodeDto[]
  edges: KgEdgeDto[]
}

export interface KgContextDto {
  node: KgNodeDto
  related: KgNodeDto[]
  summary: string | null
}

// -- intelligence ---------------------------------------------------------------------------

export interface NewsArticleDto {
  id: string
  source_id: string
  title: string
  url: string
  published_at: string
  entities: string[]
}

export interface NewsEventDto {
  id: string
  headline: string
  occurred_at: string
  entity_refs: string[]
  category: string
}

export interface CommunityTopicDto {
  id: string
  platform: string
  title: string
  volume: number
  sentiment_score: number | null
}

export interface SentimentResultDto {
  entity_ref: string
  score: number
  magnitude: number
  measured_at: string
}

export interface ImpactScoreDto {
  id: string
  news_event_id: string
  entity_ref: string
  impact_score: number
  rationale: string | null
}

export interface SummaryDto {
  subject_ref: string
  summary_type: string
  text: string
  generated_at: string
}

export interface SourceReliabilityDto {
  source_id: string
  reliability_score: number
  sample_size: number
}

// -- predictions / markets --------------------------------------------------------------------

export type MarketStatus = 'draft' | 'review' | 'approved' | 'production' | 'deprecated' | 'archived' | 'removed'
export type MarketKind = 'classification' | 'regression'
export type TargetType = 'classification' | 'regression'

export interface PredictionMarketDto {
  id: string
  market_key: string
  sport_code: string
  name: string
  category: string
  market_kind: MarketKind
  target_type: TargetType
  description: string
  status: MarketStatus
  confidence_threshold: number
  explainability_required: boolean
  owner: string
}

export interface FeatureMarketMappingDto {
  feature_key: string
  is_required: boolean
  importance: number
  confidence_contribution: number
  weight: number
}

export interface ConfidenceBreakdownDto {
  overall: number
  data_quality: number
  feature_completeness: number
  model_certainty: number
  historical_accuracy: number
  sample_size_adequacy: number
  market_liquidity: number
  temporal_relevance: number
  ensemble_agreement: number
  calibration_quality: number
  volatility_penalty: number
}

export interface ExplanationBundleDto {
  top_positive_features: Array<{ feature_key: string; contribution: number }>
  top_negative_features: Array<{ feature_key: string; contribution: number }>
  feature_importance: Record<string, number>
  knowledge_graph_contribution: string | null
  news_contribution: string | null
  community_contribution: string | null
  ai_explanation: string | null
  shap_explanation?: {
    base_value: number
    feature_contributions: Array<{ feature_key: string; shap_value: number }>
  } | null
}

export interface PredictionDto {
  id: string
  market_id: string
  model_id: string
  subject_ref: string
  value: string | number
  probability: number
  confidence: ConfidenceBreakdownDto
  explanation: ExplanationBundleDto
  feature_snapshot: Record<string, unknown>
  model_version: string
  status: string
  generated_at: string
  data_freshness: string | null
}

// -- sports (backed by the new sports_router.py, Task #196 — modules/sports/domain/entities.py) -

export interface CompetitionSummaryDto {
  id: string
  sport_code: string
  name: string
  type: string
  country: string | null
  tier: number | null
}

export interface TeamSummaryDto {
  id: string
  sport_code: string
  name: string
  short_name: string
  country: string | null
  venue_name: string | null
}

export interface PlayerSummaryDto {
  id: string
  sport_code: string
  name: string
  date_of_birth: string | null
  position: string | null
  team_id: string | null
  team_name: string | null
}

export interface FixtureSummaryDto {
  id: string
  season_id: string
  competition_name: string
  home_team: { id: string; name: string; short_name: string }
  away_team: { id: string; name: string; short_name: string }
  venue_name: string | null
  scheduled_at: string
  status: string
  final_state: Record<string, unknown> | null
}

export interface StandingRowDto {
  team_id: string
  team_name: string
  rank: number
  points: number
  record: Record<string, unknown>
}

// -- ML platform (admin) ----------------------------------------------------------------------

export type MlFramework = 'lightgbm' | 'xgboost' | 'catboost' | 'sklearn'
export type MlAlgorithm = string
export type DeploymentMode = 'shadow' | 'canary' | 'full'

export interface DatasetDto {
  id: string
  version: number
  status: string
  sample_count: number
  quality_issues: string[]
}

export interface ExperimentDto {
  id: string
  config: Record<string, unknown>
  metrics: Record<string, number>
  decision: string | null
}

export interface ModelDto {
  id: string
  model_key: string
  version: number
  algorithm: MlAlgorithm
  framework: MlFramework
  status: string
  deployment_mode: DeploymentMode | null
}

export interface CalibrationReportDto {
  method: string
  sample_count: number
  expected_calibration_error: number
  brier_score: number
  reliability_curve: Array<{ predicted_mean: number; actual_rate: number; sample_count: number }>
}
