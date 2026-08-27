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

export type PlanTier = 'free' | 'rewarded' | 'pro' | 'premium' | 'enterprise'
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

// -- checkout ---------------------------------------------------------------------------------

export interface CheckoutCardInput {
  number: string
  expiry_month: string
  expiry_year: string
  cvv: string
}

export interface CheckoutCustomerInput {
  email: string
  first_name: string
  last_name: string
  middle_name?: string
  phone_country_code: string
  phone_number: string
  address_line1: string
  city: string
  state: string
  postal_code: string
  country: string
}

export type ChargeStatus = 'pending' | 'succeeded' | 'failed'

export interface ChargeResultDto {
  status: ChargeStatus
  redirect_url: string | null
  message: string
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
  aliases: string[]
  status: string
  confidence: number
  version: number
  /** Only populated by `GET /api/v1/graph/entities/{node_type}/{entity_ref}` (single-entity
   * lookup) — absent on nodes returned from list/search/subgraph endpoints. */
  edges_out?: KgEdgeDto[]
  edges_in?: KgEdgeDto[]
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

/** Matches `_serialize_context` (backend/apps/api/routers/graph_router.py) — confirmed against
 * the live API. A previous version of this type (`{node, related, summary}`) never matched the
 * real response and crashed `match-detail-page.tsx` the first time a match actually had populated
 * Knowledge Graph context to render (`related`/`summary` don't exist on the real payload). */
export interface KgContextDto {
  subject: KgNodeDto
  neighborhood: KgSubgraphDto
  related_by_type: Record<string, KgNodeDto[]>
  generated_at: string | null
}

// -- intelligence ---------------------------------------------------------------------------

/** Matches `_serialize_news_source` (backend/apps/api/main.py) — a registered origin of news
 * content (RSS feed, official site, etc.) the admin news-ingestion trigger syncs from. */
export interface NewsSourceDto {
  id: string
  source_type: string
  name: string
  url: string
  is_official: boolean
  created_at: string | null
}

/** Matches `_serialize_article` (backend/apps/api/routers/intelligence_router.py) — confirmed
 * against the live API. No `entities` field exists on an article; entity linking runs through
 * `NewsEventDto.affected_entity_refs` instead (an article can produce zero or more events). */
export interface NewsArticleDto {
  id: string
  source_id: string
  title: string
  url: string
  published_at: string
  language: string
  version: number
  status: string
}

/** Matches `_serialize_event` — confirmed against the live API. `headline`/`entity_refs`/
 * `category` never existed on the real response; the actual fields are `summary`/
 * `affected_entity_refs`/`event_type`. */
export interface NewsEventDto {
  id: string
  event_type: string
  summary: string
  confidence: number
  source_id: string
  article_id: string | null
  occurred_at: string
  detected_at: string
  affected_entity_refs: string[]
}

/** Matches `_serialize_topic` — confirmed against the live API. The originally-declared
 * `title`/`volume`/`sentiment_score` don't exist on the real response. */
export interface CommunityTopicDto {
  id: string
  platform: string
  topic_label: string
  related_entity_refs: string[]
  post_count: number
  momentum: number | null
}

/** Matches `_serialize_sentiment` — confirmed against the live API. */
export interface SentimentResultDto {
  id: string
  target_entity_ref: string
  target_entity_type: string
  label: string
  momentum: number | null
  confidence: number
  source_ref: string | null
  computed_at: string
}

/** Matches `_serialize_impact` — confirmed against the live API. There is no single `entity_ref`
 * on an impact score; it's expressed as which teams/players/competitions were affected. */
export interface ImpactScoreDto {
  id: string
  news_event_id: string
  impact_score: number
  confidence: number
  factors: Record<string, unknown>
  affected_teams: string[]
  affected_players: string[]
  affected_competitions: string[]
}

export interface SummaryDto {
  subject_ref: string
  summary_type: string
  text: string
  generated_at: string
}

/** Matches `_serialize_reliability` — confirmed against the live API. No `sample_size` field
 * exists on the real response. */
export interface SourceReliabilityDto {
  source_id: string
  reliability_score: number
  historical_accuracy: number
  bias_rating: string | null
  verification_status: string
  trust_level: string
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

/**
 * Matches `_serialize_confidence` (backend/apps/api/routers/prediction_analytics_router.py) and
 * the inline `confidence` block of `_serialize_prediction` (prediction_router.py) — confirmed
 * against the live API, not the originally-declared shape (`overall`/`data_quality`/
 * `model_certainty`/etc., none of which the backend actually returns). `composite` is the overall
 * score; the other nine are the named factors, matching `modules/predictions/domain/entities.py`.
 */
export interface ConfidenceBreakdownDto {
  feature_quality: number
  feature_freshness: number
  historical_accuracy: number
  knowledge_graph_completeness: number
  news_reliability: number
  community_reliability: number
  data_completeness: number
  model_reliability: number
  prediction_stability: number
  composite: number
}

/**
 * Matches `_serialize_explanation`/the inline `explanation` block of `_serialize_prediction` —
 * confirmed against the live API. Two drifts from the originally-declared shape: feature entries
 * are `[feature_key, contribution]` tuples, not `{feature_key, contribution}` objects (the
 * declared shape caused a live crash — `f.feature_key/f.contribution` on an array is `undefined`);
 * and KG/news/community evidence are string lists, not a single nullable string each. No
 * `shap_explanation` field exists in the real response.
 */
export interface ExplanationBundleDto {
  top_positive_features: Array<[feature_key: string, contribution: number]>
  top_negative_features: Array<[feature_key: string, contribution: number]>
  feature_importance: Record<string, number>
  knowledge_graph_evidence: string[]
  news_contribution: string[]
  community_contribution: string[]
  ai_explanation: string | null
}

/** Matches `_serialize_contextual_review` (prediction_router.py) — the Gemini Prediction
 * Reasoning Engine's structured assessment of the base prediction against verified pre-cutoff
 * evidence. `confidence_score`/`confidence_level` here are Gemini's confidence *in this
 * contextual assessment itself*, never an outcome probability — never render either alongside or
 * instead of `PredictionDto.probability` (see `ContextualReviewPanel`'s own docstring). */
export interface ContextualReviewDto {
  review_status:
    | 'SUPPORTED'
    | 'WEAKLY_SUPPORTED'
    | 'NEUTRAL'
    | 'CHALLENGED'
    | 'STRONGLY_CHALLENGED'
    | 'INSUFFICIENT_CONTEXT'
  overall_assessment: string
  confidence_level: 'VERY_LOW' | 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH'
  confidence_score: number
  statistical_baseline: {
    applicable: boolean
    available: boolean
    algorithm: string | null
    probabilities: Record<string, number> | null
    reason: string | null
  }
  contextual_assessment: Record<
    string,
    { impact: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | 'MIXED' | 'UNKNOWN'; strength: string; score: number; reason: string }
  >
  supporting_factors: Array<{
    factor: string
    impact: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | 'MIXED' | 'UNKNOWN'
    strength: string
    evidence: string
    source_ids: string[]
  }>
  risk_factors: Array<{
    factor: string
    impact: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | 'MIXED' | 'UNKNOWN'
    strength: string
    evidence: string
    source_ids: string[]
  }>
  missing_context: string[]
  reconsideration: {
    direction: 'SUPPORTS_BASE_PREDICTION' | 'WEAKENS_BASE_PREDICTION' | 'MIXED' | 'NO_MATERIAL_CHANGE' | 'INSUFFICIENT_EVIDENCE'
    material_change: boolean
    reason: string
  } | null
  evidence_quality: {
    overall: 'VERY_LOW' | 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH'
    source_count: number
    timestamp_valid: boolean
    pre_event_only: boolean
    conflicting_information: boolean
  } | null
  source_ids: string[]
  prediction_cutoff: string | null
  prompt_version: string
  generated_at: string | null
}

/** Matches `_serialize_football_explanation` (prediction_router.py) — the Sports-Analyst
 * Explainability pipeline's attribution-grounded "why did the model predict this" read.
 * `key_reasons`/`counter_signals`/`context` carry real, computed values (`feature`,
 * `football_concept`, `team`, `direction`, `contribution`, `role`) that TitanIQ itself derived
 * from the model's attribution — `analysis` within each is Gemini's narration of that already-
 * fixed number, never a replacement for it. Football-specific by design (module name, semantic
 * mapping); requesting it for a non-football market degrades to `UNAVAILABLE` rather than
 * fabricating football language for a market that has none. */
export interface FootballExplanationDto {
  /** Sourced from the same `Prediction` this explanation was generated for (spec §17: "every
   * attribution must include feature/value/contribution/model ID/model version/prediction ID"). */
  model_id: string
  model_version: string
  prediction_id: string
  status: 'available' | 'unavailable' | 'validation_failed'
  attribution_method: 'linear_coefficient' | 'shap' | 'heuristic_importance' | 'unavailable'
  key_reasons: Array<{
    rank: number
    feature: string
    football_concept: string
    team: string | null
    direction: 'supports' | 'opposes'
    contribution: number
    evidence: string
    analysis: string
  }>
  counter_signals: Array<{
    feature: string
    football_concept: string
    contribution: number
    analysis: string
  }>
  context: Array<{
    type: string
    description: string
    model_contribution: number
    role: 'model_driver' | 'supporting_context' | 'context_only'
  }>
  verdict: string
  match_profile: string
  confidence_explanation: string
  bottom_line: string
  /** Sports-Analyst Explainability Upgrade — market-aware summary (spec §1), grounded only in
   * the real key_reasons/counter_signals already computed. Empty string when unavailable. */
  market_analysis: string
  /** Correct-Score-only deep reasoning (spec §2/§3/§4) — `null` for every other market. Every
   * numeric field is real (`Prediction.probability_distribution`/`feature_snapshot`); only the
   * four prose fields are narrated. */
  scoreline_reasoning: {
    selected_score: string
    selected_probability: number
    expected_home_goals: number | null
    expected_away_goals: number | null
    alternatives: Array<{ score: string; probability: number }>
    home_goal_case: string
    away_goal_case: string
    alternative_comparison: string
  } | null
  /** One real, verified evidence item (spec §5/§6/§17) per array entry, `source_id` traceable to
   * a real backend item — never a Gemini-invented source. `analysis` is empty when the item
   * wasn't narrated but is still real, verified evidence and still rendered. */
  injury_evidence: Array<NarratedEvidenceDto>
  news_evidence: Array<NarratedEvidenceDto>
  lineup_evidence: Array<NarratedEvidenceDto>
  context_quality: string
  unavailable_reason: string | null
  prompt_version: string
  generated_at: string | null
}

export interface NarratedEvidenceDto {
  source_id: string
  category: string
  summary: string
  entity_ref: string | null
  source_name: string | null
  published_at: string | null
  analysis: string
}

export interface PredictionDto {
  id: string
  market_id: string
  model_id: string
  /** Real `ModelDefinition.algorithm`/`.framework` for the model that produced this prediction
   * (e.g. `"xgboost_gbm"`/`"xgboost"`, `"poisson_goals_model"`/`"poisson_goals"`) — `null` only if
   * the model lookup itself failed, never a stand-in for "unknown". Humanize via
   * `humanizeModelAlgorithm` before display; never infer architecture from the market name. */
  model_algorithm: string | null
  model_framework: string | null
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
  /** Every outcome's calibrated probability for a classification-shaped market (real label ->
   * probability), including `value`'s own — "Alternative Outcomes". Empty for a regression-shaped
   * market (`confidence_interval`/`expected_error` populated instead). */
  probability_distribution: Record<string, number>
  /** `[low, high]` — populated only for a regression-shaped market, where `value` is the
   * predicted continuous number itself rather than a classification label. */
  confidence_interval: [number, number] | null
  /** Historical mean absolute error for this market — populated only for a regression-shaped
   * market, and only once it has evaluated outcome history to derive it from. */
  expected_error: number | null
  /** Present only when the request set `include_contextual_review: true` — `null` otherwise
   * (existing callers see no shape change) and also `null` on any Gemini Reasoning Engine
   * failure (never breaks this response). */
  contextual_review: ContextualReviewDto | null
  /** Present only when the request set `include_football_explanation: true` — `null` otherwise,
   * and also `null` on any Sports-Analyst Explainability pipeline failure (never breaks this
   * response). Distinct from `contextual_review`: this explains what the model itself weighed;
   * `contextual_review` assesses that prediction against fresh evidence. */
  football_explanation: FootballExplanationDto | null
  /** Always `"READY"` on a successful response — a blocked/insufficient-data generation returns
   * a non-2xx status with a structured `{prediction_status: "BLOCKED", reason_code, failed_gates}`
   * body instead of this shape (see `ApiError`/prediction_router.py `_blocked_detail`). */
  prediction_status: 'READY'
  /** Real prod incident audit (2026-08-23): "a Champion is registered for this market" and "the
   * Champion's own artifact actually served this prediction" are different claims — a corrupt/
   * missing artifact silently falls back to a generic formula predictor, previously reported here
   * as "ACTIVE" regardless. Derived from `predictor_provenance`: "ACTIVE" only when a real trained
   * model served this prediction, "FALLBACK" when the formula predictor did, "UNKNOWN" for
   * predictions generated before this field existed (never inferred after the fact). */
  champion_status: 'ACTIVE' | 'FALLBACK' | 'UNKNOWN'
  /** "trained_model" | "formula_fallback" | `null` (generated before this field existed) — the
   * raw signal `champion_status` above is derived from; prefer reading this directly when you
   * need the actual value rather than the human-facing label. */
  predictor_provenance: 'trained_model' | 'formula_fallback' | null
  /** Whether the always-on `ExplainabilityEngine` narrative (`explanation.ai_explanation`) was
   * produced — distinct from `contextual_review`/`football_explanation`, which carry their own
   * status fields for the two opt-in explanation subsystems. */
  explanation_status: 'GENERATED' | 'UNAVAILABLE'
}

/** Matches `_serialize_summary` (prediction_analytics_router.py) — the shape actually returned by
 * `GET /predictions/history/{subject_ref}` and `POST /predictions/compare`, a flatter view than
 * `PredictionDto` (no nested `confidence`/`explanation`, just the composite score). */
export interface PredictionSummaryDto {
  id: string
  market_id: string
  model_id: string
  subject_ref: string
  value: string | number
  probability: number
  confidence_composite: number
  status: string
  generated_at: string | null
}

/** Matches `_serialize_summary` + the market/evidence fields `ai_picks` (prediction_analytics_router.py)
 * adds on top — a `PredictionSummaryDto` enriched with which market/sport it belongs to, since a
 * cross-sport feed can't assume the caller already knows. */
export interface PredictionPickDto extends PredictionSummaryDto {
  market_key: string
  market_name: string
  sport_code: string
  evidence_count: number
  ai_explanation: string | null
}

/** Mobile V1 monetization — matches `GET /api/v1/predictions/entitlement`
 * (prediction_router.py). `requires_rewarded_ad` is a convenience flag (`available_predictions
 * <= 0`), not independent state — never diverges from the count. */
export interface PredictionEntitlementDto {
  available_predictions: number
  initial_free_predictions: number
  rewarded_predictions_granted: number
  requires_rewarded_ad: boolean
}

/** Matches `_serialize_market_review` (prediction_analytics_router.py) — one market's real
 * predicted-vs-actual reading. `actual_value`/`is_correct`/`evaluated_at` are `null` when the
 * fixture hasn't completed yet or the market has no registered outcome resolver — never guessed. */
export interface MarketReviewDto {
  market_id: string
  market_key: string
  market_name: string
  predicted_value: string
  probability: number
  confidence: number
  probability_distribution: Record<string, number>
  top_positive_features: Array<[feature_key: string, contribution: number]>
  top_negative_features: Array<[feature_key: string, contribution: number]>
  ai_explanation: string | null
  generated_at: string | null
  actual_value: string | null
  is_correct: boolean | null
  evaluated_at: string | null
}

export interface FixtureReviewMetaDto {
  market_count: number
  resolved_count: number
  correct_count: number
  accuracy: number | null
  average_confidence: number | null
}

// -- sports (backed by the new sports_router.py, Task #196 — modules/sports/domain/entities.py) -

export interface CompetitionSummaryDto {
  id: string
  sport_code: string
  name: string
  type: string
  country: string | null
  tier: number | null
  logo_url: string | null
}

export interface SeasonSummaryDto {
  id: string
  label: string
  start_date: string | null
  status: string
}

export interface TeamSummaryDto {
  id: string
  sport_code: string
  name: string
  short_name: string
  country: string | null
  venue_name: string | null
  logo_url: string | null
}

export interface PlayerSummaryDto {
  id: string
  sport_code: string
  name: string
  date_of_birth: string | null
  position: string | null
  team_id: string | null
  team_name: string | null
  photo_url: string | null
}

export interface FixtureSummaryDto {
  id: string
  season_id: string
  sport_code: string | null
  competition_id: string | null
  competition_name: string
  competition_logo_url: string | null
  competition_tier: number | null
  home_team: { id: string; name: string; short_name: string; logo_url: string | null }
  away_team: { id: string; name: string; short_name: string; logo_url: string | null }
  venue_name: string | null
  scheduled_at: string
  status: string
  final_state: { home: number | null; away: number | null } | null
  /** Real period-by-period score breakdown — quarters for basketball, innings for baseball.
   * `null` for football (not fetched by that adapter) or before the provider has reported any
   * periods for this fixture yet. */
  period_scores: { kind: 'quarter' | 'inning'; home: Array<number | null>; away: Array<number | null> } | null
  /** Real possession/shots/corners/fouls/cards for a completed match, keyed exactly like the
   * backend's `team_statistics.stat_set` — `null` whenever nothing was ever recorded for this
   * fixture (most historical matches today), never a fabricated placeholder. */
  stats: { home: Record<string, number | null> | null; away: Record<string, number | null> | null } | null
}

export interface StandingRowDto {
  team_id: string
  team_name: string
  rank: number
  points: number
  record: Record<string, unknown>
}

/** Matches `_serialize_team_statistics_summary`-equivalent shape from `get_team_statistics` —
 * every field is a real average over recently recorded matches, or `null` if that stat was never
 * recorded in the sample. `sample_size` is how many matches actually had any stats logged. Which
 * keys are present is sport-aware on the backend (`_TEAM_STATISTIC_KEYS_BY_SPORT`) — football
 * carries `possession_pct`/`shots_total`/etc, basketball carries `points`/`rebounds_total`/etc,
 * baseball carries `runs`/`hits`/`errors` — so this stays a generic index rather than one fixed
 * football-shaped interface. */
export interface TeamStatisticsSummaryDto {
  sample_size: number
  [statKey: string]: number | null
}

/** Real per-fixture stat row from `GET /sports/fixtures/{id}/statistics` — one entry per team
 * that actually had a `TeamStatistics` row synced for that specific match. Genuinely different
 * from `TeamStatisticsSummaryDto` above (a rolling-window average): this is the exact recorded
 * numbers for one match, and `stats` carries only the keys that were actually recorded — never
 * padded with nulls for keys nobody synced. Coverage is honestly sparse — most completed
 * fixtures have zero rows here until the stats sync job runs for them. Key vocabulary is
 * sport-aware (see `api_sports_adapter.py`'s per-sport `stat_set` shapes), so this is a generic
 * numeric map rather than one fixed football-shaped interface. */
export interface FixtureTeamStatisticsDto {
  team_id: string
  stats: Record<string, number>
}

// -- Squad intelligence (injuries, transfers, coaching staff) -------------------------------------

/** A player's currently-reported unavailability. `status`/`reason` are the provider's own raw
 * text (e.g. API-Football's "Missing Fixture"/"Hamstring") — never a normalized enum, since the
 * real states a provider reports don't map onto one. `expected_return` is `null` whenever the
 * provider doesn't report one — never inferred or fabricated. */
export interface InjuryDto {
  id: string
  player_id: string
  player_name: string | null
  status: string
  reason: string | null
  reported_at: string
  expected_return: string | null
}

/** A confirmed transfer only — `transfer_type` is the provider's raw fee/type text (e.g. "Loan",
 * "Free", "€25.5M"). No rumour/negotiating staging: that signal lives in the news pipeline
 * instead, since no connected provider reports pre-confirmation transfer stages. */
export interface TransferDto {
  id: string
  player_id: string
  player_name: string | null
  from_team_id: string | null
  from_team_name: string | null
  to_team_id: string | null
  to_team_name: string | null
  effective_date: string
  transfer_type: string | null
}

/** One coaching-staff row — `valid_to: null` means still in the role. History is never
 * overwritten: a departure closes the row instead of deleting it. */
export interface CoachingStaffDto {
  id: string
  team_id: string | null
  person_name: string
  role: string
  valid_from: string | null
  valid_to: string | null
}

// -- Watchlist ----------------------------------------------------------------------------------

export type WatchlistEntityType = 'team' | 'competition' | 'fixture' | 'prediction'

export interface WatchlistEntryDto {
  id: string
  entity_type: WatchlistEntityType
  entity_ref: string
  created_at: string | null
}

// -- Alerts ---------------------------------------------------------------------------------

export type AlertType = 'kickoff' | 'final_result' | 'prediction_changed'

export interface AlertEventDto {
  id: string
  alert_type: AlertType
  entity_type: WatchlistEntityType
  entity_ref: string
  title: string
  body: string
  created_at: string | null
  read_at: string | null
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

// -- Continuous Outcome Learning Engine (2026-08-08) --------------------------------------------

export type ComparisonVerdict = 'challenger_better' | 'champion_better' | 'inconclusive'

export interface ComparisonMetricsDto {
  log_loss: number | null
  brier_score: number | null
  expected_calibration_error: number | null
  mae: number | null
}

export interface ChallengerComparisonDto {
  id: string
  market_id: string
  challenger_model_id: string
  champion_model_id: string | null
  challenger_metrics: ComparisonMetricsDto
  champion_metrics: ComparisonMetricsDto | null
  verdict: ComparisonVerdict
  decisive_metric: string
  holdout_sample_count: number
  evaluated_at: string
}

export interface MarketPerformanceSummaryDto {
  market_id: string
  market_key: string
  sample_count: number
  mean_error: number | null
  accuracy: number | null
}

export interface FeatureFailureAssociationDto {
  feature_key: string
  correct_mean: number | null
  incorrect_mean: number | null
  divergence: number | null
  correct_sample_count: number
  incorrect_sample_count: number
}

export interface OverconfidenceSummaryDto {
  market_id: string
  sample_count: number
  mean_predicted_probability: number | null
  mean_actual_positive_rate: number | null
  overconfidence_score: number | null
  expected_calibration_error: number | null
}

// -- Provider Registry (Milestone 11B) ----------------------------------------------------------

export type ProviderCategory = 'sports_data' | 'ai' | 'news' | 'odds' | 'payment' | 'advertising' | 'general'
export type ProviderStatus = 'active' | 'inactive' | 'maintenance'
export type ProviderAuthType = 'bearer' | 'api_key_header' | 'api_key_query' | 'basic' | 'oauth2_client_credentials'
export type ConnectionTestStatus =
  | 'healthy'
  | 'warning'
  | 'offline'
  | 'unauthorized'
  | 'rate_limited'
  | 'timeout'
  | 'not_configured'

export interface ProviderDto {
  id: string
  key: string
  name: string
  category: ProviderCategory
  status: ProviderStatus
  priority: number
  daily_quota_limit: number | null
  monthly_quota_limit: number | null
  cache_ttl_seconds: number
  poll_interval_seconds: number
  base_url: string | null
  auth_type: ProviderAuthType | null
  auth_header_name: string | null
  region: string | null
  version: string | null
  environment: string
  timeout_seconds: number
  retry_count: number
  retry_delay_seconds: number
  created_by: string | null
  updated_by: string | null
  created_at: string | null
  updated_at: string | null
  /** Best-effort capability read from the provider's own connection-test response (e.g. an
   * API-SPORTS account's subscription plan) — null until a "Test connection" run detects one. */
  capability_note: string | null
  capability_checked_at: string | null
}

export interface ProviderCredentialMaskedDto {
  id: string
  provider_id: string
  label: string
  masked_value: string
  is_active: boolean
  created_at: string | null
  rotated_at: string | null
  expires_at: string | null
}

export interface SyncRunSummaryDto {
  run_id: string
  status: string
  records_fetched: number
  records_created: number
  records_updated: number
  records_rejected: number
}

export interface CompetitionFixtureSourceDto {
  competition_id: string
  preferred_provider_key: string
  provider_competition_ref: string
  notes: string | null
  updated_at: string | null
}

export interface TeamMappingSuggestionDto {
  football_data_org_team_id: string
  football_data_org_team_name: string
  suggested_titaniq_team_id: string | null
  suggested_titaniq_team_name: string | null
  confidence: number
}

export interface ConnectionTestResultDto {
  status: ConnectionTestStatus
  latency_ms: number | null
  http_status: number | null
  message: string
}

export interface ProviderUsageRecordDto {
  provider_id: string
  period: 'daily' | 'monthly'
  window_key: string
  request_count: number
  error_count: number
}

export interface ProviderUsageSummaryDto {
  provider_id: string
  period: 'daily' | 'monthly'
  quota_limit: number | null
  current_window_requests: number
  remaining_requests: number | null
  success_rate: number | null
  history: ProviderUsageRecordDto[]
}

export interface ProviderHistoryDto {
  recent_checks: Array<{ checked_at: string; success: boolean; latency_ms: number | null; message: string | null }>
  incidents: Array<{
    id: string
    provider_id: string
    severity: string
    opened_at: string
    resolved_at: string | null
    trigger: string
    is_open: boolean
  }>
}

export interface ProviderCategorySummaryDto {
  category: ProviderCategory
  provider_count: number
}

export interface ProviderStatusSummaryDto {
  total_providers: number
  by_status: Record<string, number>
  by_health: Record<string, number>
}

// -- public (unauthenticated) — backed by public_router.py, the landing page's only real data source

export interface PublicSportSummaryDto {
  code: string
  display_name: string
  competitions: number
  live_fixtures: number
  today_fixtures: number
}

export interface PublicPlatformSummaryDto {
  sports: PublicSportSummaryDto[]
  sports_covered: number
  competitions_tracked: number
  live_fixtures: number
  today_fixtures: number
  completed_fixtures_recent: number
  /** A sample over the most recent `published_predictions_sample_size` predictions, not a lifetime
   * total — no repository method exists for an unbounded COUNT(*) (see public_router.py). */
  published_predictions_sample: number
  published_predictions_sample_size: number
  knowledge_graph: { node_count: number; edge_count: number }
  last_synced_at: string | null
  generated_at: string
}

export interface PublicFeaturedIntelligenceDto {
  prediction_id: string
  fixture_id: string
  sport_code: string
  competition_name: string | null
  home_team: { name: string; short_name: string; logo_url: string | null } | null
  away_team: { name: string; short_name: string; logo_url: string | null } | null
  scheduled_at: string
  status: string
  home_score: number | null
  away_score: number | null
  /** Only set once the fixture is `completed` AND `OutcomeResolutionService` has resolved this
   * specific prediction — `null` for an upcoming/live fixture, and also `null` for a completed
   * one whose outcome hasn't been resolved yet (never inferred client-side). `is_correct` is
   * `null` for a REGRESSION market (no 0/1 "correct" concept for a continuous prediction). */
  outcome: { actual_value: string; is_correct: boolean | null } | null
  market_name: string
  market_key: string
  value: string | number
  probability: number
  probability_distribution: Record<string, number>
  confidence_composite: number
  evidence_highlights: { supporting: string[]; contradicting: string[] }
  generated_at: string | null
}

export interface PublicNewsIntelligenceItemDto {
  article_id: string
  headline: string
  url: string
  published_at: string
  event_summary: string
  event_type: string
  impact_score: number
  impact_confidence: number
  affected_teams: string[]
  affected_competitions: string[]
}

export interface PublicKgPreviewNodeDto {
  id: string
  type: string
  entity_ref: string
  /** Real display name resolved from the relational table `entity_ref` points at (team short
   * name, "Home vs Away" for a match, etc.) — null, never a guess, when no resolver exists yet
   * for this node type. Falls back to `type` when rendering. */
  label: string | null
}

/** `entity_ref`/`node_type` only, deliberately not resolved to a display name — no per-node-type
 * name resolver exists yet (see public_router.py's `knowledge_graph_preview` docstring). */
export interface PublicKnowledgeGraphPreviewDto {
  node_count: number
  edge_count: number
  nodes_by_type: Record<string, number>
  edges_by_type: Record<string, number>
  preview_entity: {
    node: PublicKgPreviewNodeDto
    connection_count: number
    neighbors: PublicKgPreviewNodeDto[]
    relationships: Array<{ from: string; to: string; type: string }>
  } | null
}
