import type {
  PredictionDto,
  KgNodeDto,
  KgEdgeDto,
  FixtureSummaryDto,
  CompetitionSummaryDto,
  TeamSummaryDto,
  PlayerSummaryDto,
} from '@/lib/api/types'

/**
 * Illustrative-but-DTO-accurate sample data for the unauthenticated landing page.
 *
 * Every sports/prediction/knowledge-graph endpoint requires an authenticated session
 * (sports_router.py, graph_router.py:282-283 all depend on get_current_user) — there is no
 * public per-subject data source for a visitor who hasn't signed in yet. Every literal below
 * matches the real DTO shapes in lib/api/types.ts field-for-field (not a mockup image, not
 * invented fields), and every section that renders this data labels it "Illustrative" in the UI.
 * Nothing here is presented as live.
 */

const SPORTS = ['football', 'basketball', 'baseball', 'table_tennis'] as const

function confidence(overall: number) {
  return {
    overall,
    data_quality: Math.min(0.98, overall + 0.08),
    feature_completeness: Math.min(0.96, overall + 0.04),
    model_certainty: overall - 0.03,
    historical_accuracy: overall - 0.05,
    sample_size_adequacy: Math.min(0.95, overall + 0.1),
    market_liquidity: overall - 0.12,
    temporal_relevance: Math.min(0.97, overall + 0.06),
    ensemble_agreement: overall - 0.02,
    calibration_quality: overall + 0.01,
    volatility_penalty: overall - 0.1,
  }
}

function explanation(positive: string, negative: string, narrative: string) {
  return {
    top_positive_features: [
      { feature_key: positive, contribution: 0.16 },
      { feature_key: 'recent_form_index', contribution: 0.09 },
    ],
    top_negative_features: [{ feature_key: negative, contribution: -0.06 }],
    feature_importance: { [positive]: 0.16, recent_form_index: 0.09, [negative]: -0.06 },
    knowledge_graph_contribution: 'Historical head-to-head and venue record favor this outcome.',
    news_contribution: 'No material injury or lineup disruption reported in the last 72 hours.',
    community_contribution: null,
    ai_explanation: narrative,
    shap_explanation: { base_value: 0.5, feature_contributions: [{ feature_key: positive, shap_value: 0.16 }] },
  }
}

interface SamplePredictionSeed {
  sport: (typeof SPORTS)[number]
  subject: string
  market: string
  value: string | number
  probability: number
  overallConfidence: number
  positiveFeature: string
  negativeFeature: string
  narrative: string
}

const PREDICTION_SEEDS: SamplePredictionSeed[] = [
  { sport: 'football', subject: 'Arsenal vs. Manchester City', market: 'football.match_result', value: 'home_win', probability: 0.612, overallConfidence: 0.78, positiveFeature: 'home_form_last_5', negativeFeature: 'away_squad_rest_days', narrative: 'Home form and head-to-head record are the strongest signals this window.' },
  { sport: 'football', subject: 'Real Madrid vs. Barcelona', market: 'football.match_result', value: 'draw', probability: 0.31, overallConfidence: 0.64, positiveFeature: 'possession_balance', negativeFeature: 'travel_fatigue', narrative: 'Evenly matched squads with converging expected-goals models.' },
  { sport: 'football', subject: 'Bayern Munich vs. Dortmund', market: 'football.match_result', value: 'home_win', probability: 0.58, overallConfidence: 0.72, positiveFeature: 'home_xg_last_10', negativeFeature: 'set_piece_vulnerability', narrative: 'Bayern’s attacking output at home has outpaced Dortmund’s defensive metrics.' },
  { sport: 'football', subject: 'Inter Milan vs. AC Milan', market: 'football.match_result', value: 'away_win', probability: 0.44, overallConfidence: 0.61, positiveFeature: 'counter_attack_efficiency', negativeFeature: 'derby_variance', narrative: 'Milan’s counter-attacking profile matches Inter’s recent high defensive line.' },
  { sport: 'football', subject: 'PSG vs. Marseille', market: 'football.match_result', value: 'home_win', probability: 0.69, overallConfidence: 0.81, positiveFeature: 'squad_depth_index', negativeFeature: 'away_travel_distance', narrative: 'Squad depth and home advantage compound in PSG’s favor.' },
  { sport: 'football', subject: 'Liverpool vs. Chelsea', market: 'football.match_result', value: 'home_win', probability: 0.55, overallConfidence: 0.7, positiveFeature: 'high_press_success_rate', negativeFeature: 'injury_adjusted_xg', narrative: 'High-press success rate remains Liverpool’s clearest edge this season.' },
  { sport: 'basketball', subject: 'Lakers vs. Celtics', market: 'basketball.moneyline', value: 'away_win', probability: 0.53, overallConfidence: 0.67, positiveFeature: 'net_rating_last_10', negativeFeature: 'back_to_back_fatigue', narrative: 'Celtics’ net rating over the last 10 games edges out home-court advantage.' },
  { sport: 'basketball', subject: 'Warriors vs. Suns', market: 'basketball.moneyline', value: 'home_win', probability: 0.6, overallConfidence: 0.74, positiveFeature: 'three_point_variance', negativeFeature: 'rebounding_deficit', narrative: 'Three-point shooting variance favors the home side’s recent hot streak.' },
  { sport: 'basketball', subject: 'Bucks vs. 76ers', market: 'basketball.moneyline', value: 'home_win', probability: 0.57, overallConfidence: 0.69, positiveFeature: 'starting_five_continuity', negativeFeature: 'bench_scoring_gap', narrative: 'Lineup continuity is the strongest differentiator between these rosters.' },
  { sport: 'basketball', subject: 'Nuggets vs. Mavericks', market: 'basketball.moneyline', value: 'away_win', probability: 0.48, overallConfidence: 0.63, positiveFeature: 'pace_adjusted_efficiency', negativeFeature: 'altitude_disadvantage', narrative: 'Pace-adjusted efficiency narrows this to a near coin flip on the road.' },
  { sport: 'baseball', subject: 'Yankees vs. Red Sox', market: 'baseball.moneyline', value: 'home_win', probability: 0.56, overallConfidence: 0.68, positiveFeature: 'starting_pitcher_era', negativeFeature: 'bullpen_workload', narrative: 'Starting pitcher ERA differential is the clearest edge in this matchup.' },
  { sport: 'baseball', subject: 'Dodgers vs. Giants', market: 'baseball.moneyline', value: 'home_win', probability: 0.63, overallConfidence: 0.75, positiveFeature: 'batting_avg_vs_rhp', negativeFeature: 'road_split_variance', narrative: 'Batting average against right-handed pitching strongly favors the home lineup.' },
  { sport: 'baseball', subject: 'Astros vs. Rangers', market: 'baseball.moneyline', value: 'away_win', probability: 0.47, overallConfidence: 0.6, positiveFeature: 'bullpen_era_last_15', negativeFeature: 'division_rivalry_variance', narrative: 'Bullpen form over the last 15 games is the deciding factor here.' },
  { sport: 'table_tennis', subject: 'Ma Long vs. Fan Zhendong', market: 'table_tennis.match_winner', value: 'player_b', probability: 0.54, overallConfidence: 0.66, positiveFeature: 'recent_head_to_head', negativeFeature: 'tournament_fatigue', narrative: 'Recent head-to-head results give a slight edge in a closely-matched rivalry.' },
  { sport: 'table_tennis', subject: 'Tomokazu Harimoto vs. Hugo Calderano', market: 'table_tennis.match_winner', value: 'player_a', probability: 0.61, overallConfidence: 0.71, positiveFeature: 'serve_win_rate', negativeFeature: 'surface_adaptation', narrative: 'Serve win rate has been the deciding statistic across their last five meetings.' },
  { sport: 'table_tennis', subject: 'Wang Chuqin vs. Truls Moregard', market: 'table_tennis.match_winner', value: 'player_a', probability: 0.66, overallConfidence: 0.77, positiveFeature: 'rally_win_pct', negativeFeature: 'travel_adjustment', narrative: 'Rally win percentage over extended points is a decisive statistical gap.' },
]

export const SAMPLE_PREDICTIONS: PredictionDto[] = PREDICTION_SEEDS.map((seed, index) => ({
  id: `sample-prediction-${index}`,
  market_id: seed.market,
  model_id: `sample-model-${seed.sport}`,
  subject_ref: seed.subject,
  value: seed.value,
  probability: seed.probability,
  model_version: 'v14',
  status: 'published',
  generated_at: new Date(0).toISOString(),
  data_freshness: 'fresh',
  confidence: confidence(seed.overallConfidence),
  explanation: explanation(seed.positiveFeature, seed.negativeFeature, seed.narrative),
  feature_snapshot: {},
}))

export const SAMPLE_PREDICTIONS_BY_SPORT: Record<string, PredictionDto[]> = Object.fromEntries(
  SPORTS.map((sport) => [sport, SAMPLE_PREDICTIONS.filter((_, i) => PREDICTION_SEEDS[i].sport === sport)]),
)

export const SAMPLE_FEATURED_PREDICTION = SAMPLE_PREDICTIONS[0]

// -- Fixtures (Live Sports Intelligence ticker) -----------------------------------------------

export const SAMPLE_FIXTURES: Array<FixtureSummaryDto & { sport_code: string }> = [
  {
    id: 'sample-fixture-1',
    sport_code: 'football',
    season_id: 'sample-season',
    competition_name: 'Premier League',
    home_team: { id: 'team-arsenal', name: 'Arsenal', short_name: 'ARS' },
    away_team: { id: 'team-mancity', name: 'Manchester City', short_name: 'MCI' },
    venue_name: 'Emirates Stadium',
    scheduled_at: new Date(0).toISOString(),
    status: 'live',
    final_state: { home_score: 1, away_score: 1 },
  },
  {
    id: 'sample-fixture-2',
    sport_code: 'basketball',
    season_id: 'sample-season',
    competition_name: 'NBA',
    home_team: { id: 'team-lakers', name: 'Lakers', short_name: 'LAL' },
    away_team: { id: 'team-celtics', name: 'Celtics', short_name: 'BOS' },
    venue_name: 'Crypto.com Arena',
    scheduled_at: new Date(0).toISOString(),
    status: 'scheduled',
    final_state: null,
  },
  {
    id: 'sample-fixture-3',
    sport_code: 'baseball',
    season_id: 'sample-season',
    competition_name: 'MLB',
    home_team: { id: 'team-yankees', name: 'Yankees', short_name: 'NYY' },
    away_team: { id: 'team-redsox', name: 'Red Sox', short_name: 'BOS' },
    venue_name: 'Yankee Stadium',
    scheduled_at: new Date(0).toISOString(),
    status: 'finished',
    final_state: { home_score: 5, away_score: 3 },
  },
  {
    id: 'sample-fixture-4',
    sport_code: 'table_tennis',
    season_id: 'sample-season',
    competition_name: 'WTT Champions',
    home_team: { id: 'team-malong', name: 'Ma Long', short_name: 'MLO' },
    away_team: { id: 'team-fan', name: 'Fan Zhendong', short_name: 'FZD' },
    venue_name: 'WTT Arena',
    scheduled_at: new Date(0).toISOString(),
    status: 'scheduled',
    final_state: null,
  },
]

export const SAMPLE_ALERTS = [
  { tone: 'warning' as const, label: 'Injury alert', detail: 'Starting midfielder listed as doubtful — confidence recalculated.' },
  { tone: 'info' as const, label: 'Confidence shift', detail: 'Overall confidence moved +4pts after latest team-news ingest.' },
  { tone: 'danger' as const, label: 'Transfer alert', detail: 'Key striker linked with a mid-season transfer — monitored, not yet acted on.' },
  { tone: 'success' as const, label: 'Trending team', detail: 'Five straight covered predictions — trending in the Prediction Center.' },
]

// -- Competitions / Teams / Players -------------------------------------------------------------

export const SAMPLE_COMPETITIONS: CompetitionSummaryDto[] = [
  { id: 'comp-epl', sport_code: 'football', name: 'Premier League', type: 'league', country: 'England', tier: 1 },
  { id: 'comp-ucl', sport_code: 'football', name: 'Champions League', type: 'cup', country: null, tier: 1 },
  { id: 'comp-laliga', sport_code: 'football', name: 'La Liga', type: 'league', country: 'Spain', tier: 1 },
  { id: 'comp-nba', sport_code: 'basketball', name: 'NBA', type: 'league', country: 'United States', tier: 1 },
  { id: 'comp-mlb', sport_code: 'baseball', name: 'MLB', type: 'league', country: 'United States', tier: 1 },
  { id: 'comp-wtt', sport_code: 'table_tennis', name: 'WTT Champions', type: 'tour', country: null, tier: 1 },
]

export const SAMPLE_TEAMS: TeamSummaryDto[] = [
  { id: 'team-arsenal', sport_code: 'football', name: 'Arsenal', short_name: 'ARS', country: 'England', venue_name: 'Emirates Stadium' },
  { id: 'team-mancity', sport_code: 'football', name: 'Manchester City', short_name: 'MCI', country: 'England', venue_name: 'Etihad Stadium' },
  { id: 'team-lakers', sport_code: 'basketball', name: 'Los Angeles Lakers', short_name: 'LAL', country: 'United States', venue_name: 'Crypto.com Arena' },
  { id: 'team-yankees', sport_code: 'baseball', name: 'New York Yankees', short_name: 'NYY', country: 'United States', venue_name: 'Yankee Stadium' },
]

export const SAMPLE_PLAYERS: PlayerSummaryDto[] = [
  { id: 'player-1', sport_code: 'football', name: 'Bukayo Saka', date_of_birth: null, position: 'Forward', team_id: 'team-arsenal', team_name: 'Arsenal' },
  { id: 'player-2', sport_code: 'football', name: 'Erling Haaland', date_of_birth: null, position: 'Forward', team_id: 'team-mancity', team_name: 'Manchester City' },
  { id: 'player-3', sport_code: 'basketball', name: 'LeBron James', date_of_birth: null, position: 'Forward', team_id: 'team-lakers', team_name: 'Los Angeles Lakers' },
]

// -- Spotlight cards ------------------------------------------------------------------------------
// Each composes its underlying summary DTO with a few illustrative "showcase" fields (live-match
// count, form, power ranking, AI summary) that don't live on a single real DTO today — same
// honesty convention as SampleNewsCard above: not claimed as a real endpoint response shape.

export interface CompetitionSpotlight extends CompetitionSummaryDto {
  season: string
  liveMatches: number
  predictionsAvailable: number
  teamsCount: number
  newsCount: number
  trendingStory: string
}

export const SAMPLE_COMPETITION_SPOTLIGHTS: CompetitionSpotlight[] = [
  { ...SAMPLE_COMPETITIONS[0], season: '2025/26', liveMatches: 1, predictionsAvailable: 6, teamsCount: 20, newsCount: 34, trendingStory: 'Title race tightens after a run of high-confidence upsets.' },
  { ...SAMPLE_COMPETITIONS[3], season: '2025/26', liveMatches: 0, predictionsAvailable: 4, teamsCount: 30, newsCount: 21, trendingStory: 'Western Conference standings shift after back-to-back sets.' },
  { ...SAMPLE_COMPETITIONS[4], season: '2025', liveMatches: 0, predictionsAvailable: 3, teamsCount: 30, newsCount: 18, trendingStory: 'Bullpen usage trends dominate this week’s model recalibration.' },
]

export interface TeamSpotlight extends TeamSummaryDto {
  recentForm: string
  powerRanking: number
  predictionStrength: number
  upcomingOpponent: string
  aiSummary: string
}

export const SAMPLE_TEAM_SPOTLIGHTS: TeamSpotlight[] = [
  { ...SAMPLE_TEAMS[0], recentForm: 'W-W-D-W-L', powerRanking: 3, predictionStrength: 0.78, upcomingOpponent: 'Manchester City', aiSummary: 'Strong home form driven by high-press efficiency and low injury exposure.' },
  { ...SAMPLE_TEAMS[2], recentForm: 'W-L-W-W-W', powerRanking: 5, predictionStrength: 0.67, upcomingOpponent: 'Boston Celtics', aiSummary: 'Offensive rating trending up over the last 10 games despite rotation changes.' },
  { ...SAMPLE_TEAMS[3], recentForm: 'W-W-W-L-W', powerRanking: 2, predictionStrength: 0.74, upcomingOpponent: 'Boston Red Sox', aiSummary: 'Starting rotation ERA is the clearest edge in the current model snapshot.' },
]

export interface PlayerSpotlight extends PlayerSummaryDto {
  availability: 'available' | 'doubtful' | 'out'
  performanceTrend: 'up' | 'stable' | 'down'
  predictionImpact: number
  aiInsight: string
}

export const SAMPLE_PLAYER_SPOTLIGHTS: PlayerSpotlight[] = [
  { ...SAMPLE_PLAYERS[0], availability: 'available', performanceTrend: 'up', predictionImpact: 0.14, aiInsight: 'Involved in 60% of this team’s expected-goals chain over the last 5 matches.' },
  { ...SAMPLE_PLAYERS[1], availability: 'doubtful', performanceTrend: 'stable', predictionImpact: 0.11, aiInsight: 'Availability status is the single largest swing factor on this fixture’s confidence.' },
  { ...SAMPLE_PLAYERS[2], availability: 'available', performanceTrend: 'down', predictionImpact: 0.09, aiInsight: 'Usage rate has declined slightly but efficiency metrics remain stable.' },
]

// -- Knowledge Graph preview ---------------------------------------------------------------------

export const SAMPLE_KG_CENTER: KgNodeDto = { id: 'team-sample', node_type: 'Team', entity_ref: 'Arsenal', attributes: { name: 'Arsenal' } }

export const SAMPLE_KG_NEIGHBORS: KgNodeDto[] = [
  { id: 'player-1', node_type: 'Player', entity_ref: 'Bukayo Saka', attributes: { name: 'Bukayo Saka' } },
  { id: 'player-2', node_type: 'Player', entity_ref: 'Declan Rice', attributes: { name: 'Declan Rice' } },
  { id: 'competition-1', node_type: 'Competition', entity_ref: 'Premier League', attributes: { name: 'Premier League' } },
  { id: 'venue-1', node_type: 'Venue', entity_ref: 'Emirates Stadium', attributes: { name: 'Emirates Stadium' } },
  { id: 'team-2', node_type: 'Team', entity_ref: 'Manchester City', attributes: { name: 'Manchester City' } },
  { id: 'news-1', node_type: 'NewsEvent', entity_ref: 'Injury update', attributes: { name: 'Injury update' } },
]

export const SAMPLE_KG_EDGES: KgEdgeDto[] = [
  { edge_type: 'PLAYS_FOR', from_node_id: 'player-1', to_node_id: 'team-sample', attributes: {} },
  { edge_type: 'PLAYS_FOR', from_node_id: 'player-2', to_node_id: 'team-sample', attributes: {} },
  { edge_type: 'COMPETES_IN', from_node_id: 'team-sample', to_node_id: 'competition-1', attributes: {} },
  { edge_type: 'SCHEDULED_AT', from_node_id: 'team-sample', to_node_id: 'venue-1', attributes: {} },
  { edge_type: 'RIVALS', from_node_id: 'team-sample', to_node_id: 'team-2', attributes: {} },
  { edge_type: 'MENTIONS', from_node_id: 'news-1', to_node_id: 'team-sample', attributes: {} },
]

// -- News intelligence -----------------------------------------------------------------------------
// Composes fields from several real endpoints (news article + sentiment + summary + source
// reliability, all wired separately in the authenticated News Center) into one illustrative
// landing-page card shape — not itself a single backend DTO.

export interface SampleNewsCard {
  title: string
  publishedAt: string
  aiSummary: string
  sentiment: 'positive' | 'neutral' | 'negative'
  reliability: number
  relatedEntities: string[]
}

export const SAMPLE_NEWS: SampleNewsCard[] = [
  { title: 'Arsenal confirm clean bill of health ahead of City clash', publishedAt: new Date(0).toISOString(), aiSummary: 'No first-team injuries reported; full squad expected to be available.', sentiment: 'positive', reliability: 0.91, relatedEntities: ['Arsenal', 'Premier League'] },
  { title: 'Lakers rotate starting lineup after back-to-back stretch', publishedAt: new Date(0).toISOString(), aiSummary: 'Coaching staff signals minutes management heading into a dense schedule.', sentiment: 'neutral', reliability: 0.84, relatedEntities: ['Lakers', 'NBA'] },
  { title: 'Yankees bullpen usage under scrutiny after high-leverage series', publishedAt: new Date(0).toISOString(), aiSummary: 'Workload concerns raised by beat reporters following consecutive high-pitch outings.', sentiment: 'negative', reliability: 0.78, relatedEntities: ['Yankees', 'MLB'] },
]

// -- Model intelligence -----------------------------------------------------------------------------

export const SAMPLE_MODEL_INTELLIGENCE = {
  champion_model: 'football.match_result.heuristic_logistic_v14',
  status: 'champion',
  model_agreement: 0.87,
  calibration_status: 'calibrated (isotonic)',
  expected_calibration_error: 0.031,
  prediction_accuracy_30d: 0.68,
  training_freshness_days: 6,
}

// -- Platform statistics -----------------------------------------------------------------------------

export const SAMPLE_PLATFORM_STATS = [
  { label: 'Knowledge graph nodes', value: 48210 },
  { label: 'Knowledge graph relationships', value: 132840 },
  { label: 'Engineered features', value: 214 },
  { label: 'Supported prediction markets', value: 16 },
  { label: 'Machine learning models', value: 37 },
  { label: 'Countries covered', value: 42 },
]

// -- Momentum heatmap ---------------------------------------------------------------------------------

export const SAMPLE_MOMENTUM: number[] = Array.from({ length: 18 }, (_, i) =>
  Math.round(50 + 35 * Math.sin(i * 0.5) + (i % 3) * 5),
)
