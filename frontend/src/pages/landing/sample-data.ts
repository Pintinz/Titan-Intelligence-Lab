/**
 * Illustrative-but-contract-accurate landing content. Every sports/prediction/news/knowledge-graph
 * endpoint requires an authenticated session (frontend_architecture.md §7), so a signed-out
 * visitor never sees live data — this file's shapes are checked directly against the real
 * `_serialize_*` DTOs in `lib/api/types.ts`, not invented. Every section rendering it carries a
 * visible "Illustrative" marker (see `IllustrativeTag` in `section-primitives.tsx`).
 *
 * Deliberately NOT here: fabricated usage/business metrics (user counts, prediction volume,
 * revenue). PlatformStatisticsSection states only true, verifiable-by-the-product capability
 * facts instead.
 */
import type {
  ConfidenceBreakdownDto,
  FixtureSummaryDto,
  NewsArticleDto,
  CommunityTopicDto,
} from '@/lib/api/types'

export interface FeaturedMatch {
  fixture: FixtureSummaryDto
  sportLabel: string
  market: string
  pick: string
  confidence: ConfidenceBreakdownDto
  matchHighlight: string
  newsHighlight: string
  communityPulse: string
  whyItMatters: string
  rail: 'live' | 'scheduled'
}

function confidenceOf(overall: number): ConfidenceBreakdownDto {
  return {
    overall,
    data_quality: Math.min(0.98, overall + 0.08),
    feature_completeness: Math.min(0.97, overall + 0.05),
    model_certainty: overall,
    historical_accuracy: Math.min(0.95, overall + 0.02),
    sample_size_adequacy: Math.min(0.96, overall + 0.06),
    market_liquidity: Math.max(0.4, overall - 0.1),
    temporal_relevance: 0.94,
    ensemble_agreement: Math.min(0.97, overall + 0.04),
    calibration_quality: Math.min(0.96, overall + 0.03),
    volatility_penalty: Math.max(0.05, 0.3 - overall * 0.2),
  }
}

export const FEATURED_MATCHES: FeaturedMatch[] = [
  {
    fixture: {
      id: 'illustrative-fx-1',
      season_id: 'illustrative-season-1',
      competition_name: 'Premier League',
      home_team: { id: 't1', name: 'Arsenal', short_name: 'ARS' },
      away_team: { id: 't2', name: 'Chelsea', short_name: 'CHE' },
      venue_name: 'Emirates Stadium',
      scheduled_at: new Date(Date.now() + 3 * 3600_000).toISOString(),
      status: 'scheduled',
      final_state: null,
    },
    sportLabel: 'Football',
    market: 'Both Teams to Score',
    pick: 'Yes',
    confidence: confidenceOf(0.81),
    matchHighlight: 'Arsenal unbeaten in 9 home league fixtures; Chelsea scoring in 11 of their last 12 away.',
    newsHighlight: "Chelsea's start XI reshaped by two late fitness clearances this week.",
    communityPulse: '2,340 community signals — 68% expect goals both ends',
    whyItMatters: 'Both attacks are trending up while both defenses are conceding at their highest rate all season.',
    rail: 'scheduled',
  },
  {
    fixture: {
      id: 'illustrative-fx-2',
      season_id: 'illustrative-season-2',
      competition_name: 'NBA',
      home_team: { id: 't3', name: 'Boston Celtics', short_name: 'BOS' },
      away_team: { id: 't4', name: 'Denver Nuggets', short_name: 'DEN' },
      venue_name: 'TD Garden',
      scheduled_at: new Date(Date.now() - 40 * 60_000).toISOString(),
      status: 'live',
      final_state: null,
    },
    sportLabel: 'Basketball',
    market: 'Point Spread',
    pick: 'Celtics -4.5',
    confidence: confidenceOf(0.74),
    matchHighlight: 'Celtics forcing turnovers at a season-high rate through the first quarter.',
    newsHighlight: "Nuggets' starting center listed as questionable pre-tip, downgraded to out.",
    communityPulse: '1,180 community signals — sentiment shifted +12% toward Celtics at tip-off',
    whyItMatters: "The center change removes Denver's primary rim-protection look for the rest of the game.",
    rail: 'live',
  },
  {
    fixture: {
      id: 'illustrative-fx-3',
      season_id: 'illustrative-season-3',
      competition_name: 'MLB',
      home_team: { id: 't5', name: 'Los Angeles Dodgers', short_name: 'LAD' },
      away_team: { id: 't6', name: 'San Francisco Giants', short_name: 'SF' },
      venue_name: 'Dodger Stadium',
      scheduled_at: new Date(Date.now() + 6 * 3600_000).toISOString(),
      status: 'scheduled',
      final_state: null,
    },
    sportLabel: 'Baseball',
    market: 'Total Runs',
    pick: 'Under 7.5',
    confidence: confidenceOf(0.88),
    matchHighlight: "Both starters carry a sub-3.20 ERA over their last five outings.",
    newsHighlight: 'Forecast confirms dry conditions — no weather-driven scoring bump expected.',
    communityPulse: '860 community signals — 74% leaning under',
    whyItMatters: 'Two of the league\'s form pitchers on the mound in a historically pitcher-friendly park.',
    rail: 'scheduled',
  },
  {
    fixture: {
      id: 'illustrative-fx-4',
      season_id: 'illustrative-season-4',
      competition_name: 'ITTF World Tour',
      home_team: { id: 't7', name: 'W. Zhang', short_name: 'ZHA' },
      away_team: { id: 't8', name: 'T. Ito', short_name: 'ITO' },
      venue_name: null,
      scheduled_at: new Date(Date.now() + 90 * 60_000).toISOString(),
      status: 'scheduled',
      final_state: null,
    },
    sportLabel: 'Table Tennis',
    market: 'Match Handicap',
    pick: 'Zhang -2.5 sets',
    confidence: confidenceOf(0.69),
    matchHighlight: "Zhang has won the last 4 meetings, dropping only one set across them.",
    newsHighlight: 'Ito enters off a five-match run, seven days without rest between events.',
    communityPulse: '410 community signals — split, 54% favoring the handicap',
    whyItMatters: "Fatigue is the deciding variable — Zhang's form edge alone wouldn't justify this line.",
    rail: 'scheduled',
  },
]

export const NEWS_ITEMS: Array<{
  article: NewsArticleDto
  summary: string
  predictionImpact: string
  communityImpact: string
  confidenceImpact: string
  relatedTeams: string[]
  relatedCompetition: string
}> = [
  {
    article: {
      id: 'illustrative-news-1',
      source_id: 'illustrative-source-wire',
      title: 'Chelsea reshuffles back line after fitness scare',
      url: '#',
      published_at: new Date(Date.now() - 5 * 3600_000).toISOString(),
      entities: ['Chelsea', 'Premier League'],
    },
    summary:
      'Two defenders cleared late in training, changing the expected starting shape for the away trip to Arsenal.',
    predictionImpact: 'Both Teams to Score confidence +4pts on the reshuffled back line.',
    communityImpact: 'Community sentiment on Chelsea shifted from neutral to cautiously positive.',
    confidenceImpact: 'Feature completeness improved once the confirmed XI was ingested.',
    relatedTeams: ['Arsenal', 'Chelsea'],
    relatedCompetition: 'Premier League',
  },
  {
    article: {
      id: 'illustrative-news-2',
      source_id: 'illustrative-source-wire',
      title: 'Nuggets downgrade starting center to out',
      url: '#',
      published_at: new Date(Date.now() - 90 * 60_000).toISOString(),
      entities: ['Denver Nuggets', 'NBA'],
    },
    summary: "Pregame status moved from questionable to out, removing Denver's primary interior defender.",
    predictionImpact: 'Point Spread model re-weighted rim-protection features within the hour.',
    communityImpact: 'Live sentiment tracking shows a fast swing toward the home side.',
    confidenceImpact: 'Model certainty dipped briefly on the late change, then recovered on ensemble agreement.',
    relatedTeams: ['Boston Celtics', 'Denver Nuggets'],
    relatedCompetition: 'NBA',
  },
  {
    article: {
      id: 'illustrative-news-3',
      source_id: 'illustrative-source-wire',
      title: 'Dry forecast confirmed for Dodger Stadium',
      url: '#',
      published_at: new Date(Date.now() - 8 * 3600_000).toISOString(),
      entities: ['Los Angeles Dodgers', 'San Francisco Giants', 'MLB'],
    },
    summary: 'Updated weather data rules out the wind pattern that historically inflates scoring at this park.',
    predictionImpact: 'Total Runs Under confidence held steady — weather feature contributed no penalty.',
    communityImpact: 'Minimal — weather news rarely moves community sentiment on totals.',
    confidenceImpact: 'Temporal relevance refreshed against a same-day forecast pull.',
    relatedTeams: ['Los Angeles Dodgers', 'San Francisco Giants'],
    relatedCompetition: 'MLB',
  },
]

export const COMMUNITY_TOPICS: CommunityTopicDto[] = [
  { id: 'illustrative-ct-1', platform: 'community', title: 'Arsenal vs Chelsea', volume: 2340, sentiment_score: 0.31 },
  { id: 'illustrative-ct-2', platform: 'community', title: 'Celtics vs Nuggets', volume: 1180, sentiment_score: 0.18 },
  { id: 'illustrative-ct-3', platform: 'community', title: 'Dodgers vs Giants', volume: 860, sentiment_score: 0.05 },
  { id: 'illustrative-ct-4', platform: 'community', title: 'Zhang vs Ito', volume: 410, sentiment_score: 0.22 },
]

export const INTELLIGENCE_FEED: Array<{ id: string; text: string; timestamp: string; kind: 'learning' | 'kg' | 'news' | 'confidence' }> = [
  { id: 'f1', text: 'Confidence recalibrated for Arsenal vs Chelsea BTTS after XI confirmation', timestamp: '2m ago', kind: 'confidence' },
  { id: 'f2', text: 'Model evaluation complete: Baseball Total Runs — Brier score improved 0.014', timestamp: '11m ago', kind: 'learning' },
  { id: 'f3', text: 'Knowledge Graph updated: new rivalry edge inferred, Celtics ↔ Nuggets', timestamp: '24m ago', kind: 'kg' },
  { id: 'f4', text: 'News Intelligence flagged a lineup change affecting Total Points confidence', timestamp: '38m ago', kind: 'news' },
  { id: 'f5', text: 'Retraining queued: Table Tennis Match Handicap — drift threshold crossed', timestamp: '1h ago', kind: 'learning' },
]

export const LEARNING_STEPS = [
  { title: 'Prediction Validation', detail: 'Every settled market is compared against the official result.' },
  { title: 'Model Evaluation', detail: 'Champion and challenger models are scored on the same outcome.' },
  { title: 'Learning Report', detail: 'Error signal is attributed back to specific features and markets.' },
  { title: 'Knowledge Graph Update', detail: 'New relationships and context are written back into the graph.' },
  { title: 'Confidence Recalibration', detail: 'Probability calibration is re-fit against the latest outcomes.' },
  { title: 'Retraining Queue', detail: 'Markets crossing a drift threshold are queued for retraining.' },
]

export const INSIGHTS_PROMPTS = [
  'Why is Arsenal favored to see goals both ends?',
  'Compare Celtics and Nuggets recent form',
  "What's driving the confidence drop on Ito?",
]

export const KG_PREVIEW = {
  nodes: [
    { id: 'n1', label: 'Arsenal', type: 'team' },
    { id: 'n2', label: 'Chelsea', type: 'team' },
    { id: 'n3', label: 'Premier League', type: 'competition' },
    { id: 'n4', label: 'Emirates Stadium', type: 'venue' },
    { id: 'n5', label: 'B. Saka', type: 'player' },
  ],
  edges: [
    { from: 'n1', to: 'n3', label: 'competes in' },
    { from: 'n2', to: 'n3', label: 'competes in' },
    { from: 'n1', to: 'n4', label: 'home venue' },
    { from: 'n5', to: 'n1', label: 'plays for' },
    { from: 'n1', to: 'n2', label: 'rivalry' },
  ],
}
