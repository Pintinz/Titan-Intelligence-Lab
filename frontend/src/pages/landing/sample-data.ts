import type {
  PredictionDto,
  KgNodeDto,
  KgEdgeDto,
  FixtureSummaryDto,
  CompetitionSummaryDto,
} from '@/lib/api/types'

/**
 * Illustrative-but-contract-accurate content for the unauthenticated landing page.
 *
 * Every sports/prediction/news/knowledge-graph endpoint requires an authenticated session
 * (sports_router.py, intelligence_router.py, graph_router.py, prediction_router.py all depend on
 * `get_current_user`) — there is no public per-subject data source for a visitor who hasn't
 * signed in yet. Nothing below is fetched or fabricated as live; every section that renders it
 * carries a visible "Illustrative" marker. Shapes are field-for-field accurate to the real
 * backend `_serialize_*` functions (read directly from apps/api/routers/*.py during this
 * milestone's backend audit) rather than `lib/api/types.ts`, which has drifted from the router
 * source on a few DTOs (ConfidenceBreakdownDto/ExplanationBundleDto/NewsArticleDto/
 * CommunityTopicDto) — see the Milestone 10.1 handoff notes for the fix, out of scope here.
 *
 * Sports covered match the real backend's Phase One set (docs/titaniq.md §3): Football,
 * Basketball, Baseball, Table Tennis. The brief's document referenced "Tennis" as the fourth
 * sport; the backend has no Tennis provider or plugin today (Tennis is explicitly a *future*
 * expansion sport) so this page follows the backend, not the brief, on that point.
 */

export const SPORTS = [
  { code: 'football', label: 'Football' },
  { code: 'basketball', label: 'Basketball' },
  { code: 'baseball', label: 'Baseball' },
  { code: 'table_tennis', label: 'Table Tennis' },
] as const

export type SportCode = (typeof SPORTS)[number]['code']

function confidence(composite: number) {
  return {
    feature_quality: Math.min(0.98, composite + 0.06),
    feature_freshness: Math.min(0.97, composite + 0.04),
    historical_accuracy: composite - 0.03,
    knowledge_graph_completeness: Math.min(0.95, composite + 0.02),
    news_reliability: composite - 0.05,
    community_reliability: composite - 0.1,
    data_completeness: Math.min(0.96, composite + 0.05),
    model_reliability: composite - 0.01,
    prediction_stability: composite - 0.04,
    composite,
  }
}

function explanation(positive: string, negative: string, narrative: string) {
  return {
    top_positive_features: [
      [positive, 0.16],
      ['recent_form_index', 0.09],
    ] as Array<[string, number]>,
    top_negative_features: [[negative, -0.06]] as Array<[string, number]>,
    feature_importance: { [positive]: 0.16, recent_form_index: 0.09, [negative]: -0.06 },
    knowledge_graph_evidence: ['Historical head-to-head favors this outcome.', 'Venue record supports current form.'],
    news_contribution: ['No material injury or lineup disruption reported in the last 72 hours.'],
    community_contribution: [],
    ai_explanation: narrative,
  }
}

interface MatchSeed {
  sport: SportCode
  competition: string
  home: string
  homeShort: string
  away: string
  awayShort: string
  venue: string
  kickoff: string
  status: 'scheduled' | 'live' | 'finished'
  market: string
  pick: string
  probability: number
  composite: number
  positiveFeature: string
  negativeFeature: string
  narrative: string
  whyItMatters: string
  newsHighlight: string
  pulseNote: string
}

const MATCH_SEEDS: MatchSeed[] = [
  {
    sport: 'football',
    competition: 'Premier League',
    home: 'Arsenal',
    homeShort: 'ARS',
    away: 'Manchester City',
    awayShort: 'MCI',
    venue: 'Emirates Stadium',
    kickoff: 'Sat · 18:30',
    status: 'scheduled',
    market: 'Match Winner',
    pick: 'Arsenal to win',
    probability: 0.61,
    composite: 0.87,
    positiveFeature: 'home_form_last_5',
    negativeFeature: 'away_squad_rest_days',
    narrative: 'Home form and head-to-head record are the strongest signals this window.',
    whyItMatters: 'A win keeps Arsenal within a point of the league summit with two rivals still to play each other.',
    newsHighlight: 'Full squad reported fit; no fresh injury news in the last 72 hours.',
    pulseNote: '2.3x normal post volume — highest engagement fixture of the round.',
  },
  {
    sport: 'basketball',
    competition: 'NBA',
    home: 'Lakers',
    homeShort: 'LAL',
    away: 'Celtics',
    awayShort: 'BOS',
    venue: 'Crypto.com Arena',
    kickoff: 'Tonight · 21:00',
    status: 'scheduled',
    market: 'Moneyline',
    pick: 'Celtics to win',
    probability: 0.53,
    composite: 0.69,
    positiveFeature: 'net_rating_last_10',
    negativeFeature: 'back_to_back_fatigue',
    narrative: "Celtics' net rating over the last 10 games edges out home-court advantage.",
    whyItMatters: "First meeting since last season's playoff series — a measuring-stick game for both rosters.",
    newsHighlight: 'Lakers listed as questionable on one starter; rotation change possible.',
    pulseNote: 'Sentiment trending mixed after a split head-to-head last season.',
  },
  {
    sport: 'baseball',
    competition: 'MLB',
    home: 'Yankees',
    homeShort: 'NYY',
    away: 'Red Sox',
    awayShort: 'BOS',
    venue: 'Yankee Stadium',
    kickoff: 'Tomorrow · 19:05',
    status: 'scheduled',
    market: 'Run Line',
    pick: 'Yankees -1.5',
    probability: 0.56,
    composite: 0.74,
    positiveFeature: 'starting_pitcher_era',
    negativeFeature: 'bullpen_workload',
    narrative: 'Starting pitcher ERA differential is the clearest edge in this matchup.',
    whyItMatters: 'A division rivalry game with direct standings implications in a tightening Wild Card race.',
    newsHighlight: 'Bullpen usage flagged as a watch item after three consecutive high-leverage outings.',
    pulseNote: 'Rivalry game — community volume up 40% on both fanbases.',
  },
  {
    sport: 'table_tennis',
    competition: 'WTT Champions',
    home: 'Ma Long',
    homeShort: 'MLO',
    away: 'Fan Zhendong',
    awayShort: 'FZD',
    venue: 'WTT Arena',
    kickoff: 'Sun · 14:00',
    status: 'scheduled',
    market: 'Match Winner',
    pick: 'Fan Zhendong to win',
    probability: 0.54,
    composite: 0.63,
    positiveFeature: 'recent_head_to_head',
    negativeFeature: 'tournament_fatigue',
    narrative: 'Recent head-to-head results give a slight edge in a closely-matched rivalry.',
    whyItMatters: 'A rematch of last year’s final, and the last group match before the knockout draw locks.',
    newsHighlight: 'Both players report full fitness ahead of the tie.',
    pulseNote: 'Steady engagement — no notable spikes this week.',
  },
]

export const FEATURED_MATCHES = MATCH_SEEDS.map((seed, index) => {
  const prediction: PredictionDto = {
    id: `sample-prediction-${index}`,
    market_id: seed.market.toLowerCase().replace(/\s+/g, '_'),
    model_id: `sample-model-${seed.sport}`,
    subject_ref: `${seed.home} vs. ${seed.away}`,
    value: seed.pick,
    probability: seed.probability,
    model_version: 'v14',
    status: 'published',
    generated_at: new Date(0).toISOString(),
    data_freshness: new Date(0).toISOString(),
    confidence: confidence(seed.composite) as unknown as PredictionDto['confidence'],
    explanation: explanation(seed.positiveFeature, seed.negativeFeature, seed.narrative) as unknown as PredictionDto['explanation'],
    feature_snapshot: {},
  }
  const fixture: FixtureSummaryDto = {
    id: `sample-fixture-${index}`,
    season_id: 'sample-season',
    competition_name: seed.competition,
    home_team: { id: `team-${seed.homeShort}`, name: seed.home, short_name: seed.homeShort },
    away_team: { id: `team-${seed.awayShort}`, name: seed.away, short_name: seed.awayShort },
    venue_name: seed.venue,
    scheduled_at: new Date(0).toISOString(),
    status: seed.status,
    final_state: null,
  }
  return { seed, prediction, fixture }
})

// -- Today's Intelligence ticker -----------------------------------------------------------------

export const TICKER_ITEMS = FEATURED_MATCHES.map(({ seed }) => ({
  sport: seed.sport,
  label: `${seed.homeShort} vs ${seed.awayShort}`,
  pick: `${Math.round(seed.probability * 100)}% ${seed.pick.split(' ')[0]}`,
  composite: seed.composite,
}))

// -- Competitions -----------------------------------------------------------------------------

export const SAMPLE_COMPETITIONS: CompetitionSummaryDto[] = [
  { id: 'comp-epl', sport_code: 'football', name: 'Premier League', type: 'league', country: 'England', tier: 1 },
  { id: 'comp-nba', sport_code: 'basketball', name: 'NBA', type: 'league', country: 'United States', tier: 1 },
  { id: 'comp-mlb', sport_code: 'baseball', name: 'MLB', type: 'league', country: 'United States', tier: 1 },
  { id: 'comp-wtt', sport_code: 'table_tennis', name: 'WTT Champions', type: 'tour', country: null, tier: 1 },
]

// -- Knowledge Graph preview -----------------------------------------------------------------------

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

// -- News Intelligence ------------------------------------------------------------------------------
// Field names match intelligence_router.py's real `_serialize_article` shape (id, source_id,
// title, url, published_at, language, version, status) plus separately-composed sentiment/impact/
// summary fields — this card composes several real endpoints' outputs into one illustrative shape,
// same honesty convention the previous milestone established, not itself a single backend DTO.

export interface SampleNewsCard {
  sport: SportCode
  title: string
  publishedAt: string
  summary: string
  predictionImpact: string
  communityImpact: string
  confidenceImpact: string
  relatedTeams: string[]
  relatedCompetition: string
  sourceLabel: string
}

export const SAMPLE_NEWS: SampleNewsCard[] = [
  {
    sport: 'football',
    title: 'Arsenal confirm clean bill of health ahead of City clash',
    publishedAt: new Date(0).toISOString(),
    summary: 'Club statement confirms no first-team injuries; full squad expected to be available for selection.',
    predictionImpact: 'Confidence composite +3pts on Arsenal match-winner model',
    communityImpact: 'Sentiment holding positive across tracked fan channels',
    confidenceImpact: 'Feature freshness recalculated within the last 2 hours',
    relatedTeams: ['Arsenal', 'Manchester City'],
    relatedCompetition: 'Premier League',
    sourceLabel: 'Read original source',
  },
  {
    sport: 'basketball',
    title: 'Lakers list starter as questionable ahead of Celtics rematch',
    publishedAt: new Date(0).toISOString(),
    summary: 'Coaching staff signals a possible rotation change heading into a nationally televised game.',
    predictionImpact: 'Model reliability flagged pending final inactive list',
    communityImpact: 'Community discussion volume up 18% in the last 6 hours',
    confidenceImpact: 'Data completeness holding steady, re-check scheduled pregame',
    relatedTeams: ['Lakers', 'Celtics'],
    relatedCompetition: 'NBA',
    sourceLabel: 'Read original source',
  },
  {
    sport: 'baseball',
    title: 'Yankees bullpen usage under scrutiny after high-leverage series',
    publishedAt: new Date(0).toISOString(),
    summary: 'Beat reporters raise workload concerns following three consecutive high-pitch-count outings.',
    predictionImpact: 'Historical accuracy weighting adjusted for late-inning markets',
    communityImpact: 'Sentiment trending cautious among tracked beat accounts',
    confidenceImpact: 'News reliability score: 0.84 (verified outlet)',
    relatedTeams: ['Yankees', 'Red Sox'],
    relatedCompetition: 'MLB',
    sourceLabel: 'Read original source',
  },
]

// -- TitanIQ Pulse (Community Intelligence) --------------------------------------------------------
// Field names match intelligence_router.py's real `_serialize_topic` shape (id, platform,
// topic_label, related_entity_refs, post_count, momentum).

export const SAMPLE_TOPICS = [
  { id: 'topic-1', platform: 'x', topic_label: 'Arsenal team news', related_entity_refs: ['Arsenal'], post_count: 4820, momentum: 0.62 },
  { id: 'topic-2', platform: 'reddit', topic_label: 'Lakers rotation debate', related_entity_refs: ['Lakers'], post_count: 2130, momentum: 0.31 },
  { id: 'topic-3', platform: 'x', topic_label: 'Yankees bullpen concerns', related_entity_refs: ['Yankees'], post_count: 1875, momentum: -0.12 },
  { id: 'topic-4', platform: 'reddit', topic_label: 'WTT Champions preview', related_entity_refs: ['WTT Champions'], post_count: 640, momentum: 0.18 },
]

export const SAMPLE_MOMENTUM: number[] = Array.from({ length: 24 }, (_, i) =>
  Math.round(50 + 32 * Math.sin(i * 0.45) + (i % 4) * 4),
)

// -- Learning Intelligence pipeline (genuinely sequential — docs/titaniq.md §4) -------------------

export const LEARNING_PIPELINE = [
  { step: '01', title: 'Prediction Validation', detail: 'Every published prediction is checked against the official final result.' },
  { step: '02', title: 'Model Evaluation', detail: 'Accuracy, calibration, and error patterns are scored per model and market.' },
  { step: '03', title: 'Learning Report', detail: 'A structured report attributes error to specific features and data sources.' },
  { step: '04', title: 'Knowledge Graph Update', detail: 'Confirmed outcomes and entity relationships are written back into the graph.' },
  { step: '05', title: 'Confidence Recalibration', detail: 'Platt/isotonic/temperature scaling adjusts future confidence scoring.' },
  { step: '06', title: 'Retraining Queue', detail: 'Models below threshold are queued for the next Automatic Model Selection pass.' },
  { step: '07', title: 'Future Predictions Improve', detail: 'The next prediction on this subject inherits every lesson learned.' },
]

// -- Platform Intelligence Statistics ---------------------------------------------------------------

export const PLATFORM_STATS = [
  { label: 'Knowledge graph nodes', value: '48,210' },
  { label: 'Knowledge graph relationships', value: '132,840' },
  { label: 'Engineered features', value: '214' },
  { label: 'Supported prediction markets', value: '16' },
  { label: 'Machine learning models', value: '37' },
  { label: 'Sports covered', value: '4' },
]

// -- TitanIQ Assistant teaser ------------------------------------------------------------------------

export const ASSISTANT_SAMPLE_EXCHANGES = [
  {
    question: 'Why is Arsenal favoured against Manchester City?',
    answer:
      'Home form over the last 5 matches and head-to-head history are the strongest signals — feature quality and freshness are both high, so confidence sits at Peak Intelligence (87%).',
  },
  {
    question: 'How reliable is the Yankees run-line pick?',
    answer:
      'High confidence (74%) — driven mainly by starting-pitcher ERA differential, with bullpen workload flagged as a moderating factor worth watching pregame.',
  },
]
