import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GeneratedIntelligencePanel } from './generated-intelligence'
import type { FootballExplanationDto, PredictionDto } from '@/lib/api/types'

const homeTeam = { name: 'Manchester United', logoUrl: null }
const awayTeam = { name: 'Fulham', logoUrl: null }

function footballExplanation(overrides: Partial<FootballExplanationDto> = {}): FootballExplanationDto {
  return {
    model_id: 'model-1',
    model_version: '1',
    prediction_id: 'pred-1',
    status: 'available',
    attribution_method: 'linear_coefficient',
    key_reasons: [
      {
        rank: 1, feature: 'football.fixture.form_fouls_diff_last5', football_concept: 'recent physical/disciplinary intensity',
        team: 'home side', direction: 'supports', contribution: 0.31, evidence: 'football.fixture.form_fouls_diff_last5 = 2.4',
        analysis: 'Recent discipline trend favors the home side.',
      },
    ],
    counter_signals: [
      {
        feature: 'football.fixture.form_shots_on_target_diff_last5', football_concept: 'recent ability to generate attempts that test the goalkeeper',
        contribution: -0.22, analysis: 'The away side has generated more shots on target recently, which pushes against this lean.',
      },
    ],
    context: [],
    verdict: 'TitanIQ sees a narrow home-side edge, built primarily on recent discipline trends.',
    match_profile: '1 model-attributed factor(s) and 1 counter-signal(s) considered.',
    confidence_explanation: 'The selected outcome has a modeled probability of 43%.',
    bottom_line: 'A moderate statistical edge, not a high-confidence call.',
    market_analysis: 'Match Winner is driven mainly by recent discipline trends.',
    scoreline_reasoning: null,
    injury_evidence: [],
    news_evidence: [],
    lineup_evidence: [],
    context_quality: 'Verified pre-cutoff evidence available: 1 news.',
    unavailable_reason: null,
    prompt_version: 'TITANIQ_FOOTBALL_ANALYST_V1',
    generated_at: new Date().toISOString(),
    ...overrides,
  }
}

function fullPrediction(overrides: Partial<PredictionDto> = {}): PredictionDto {
  return {
    id: 'pred-1',
    market_id: 'market-1',
    model_id: 'model-1',
    model_algorithm: 'logistic_regression',
    model_framework: 'sklearn',
    subject_ref: 'fixture-1',
    value: 'HOME_WIN',
    probability: 0.43,
    confidence: {
      feature_quality: 0.6, feature_freshness: 0.6, historical_accuracy: 0.6, knowledge_graph_completeness: 0.6,
      news_reliability: 0.6, community_reliability: 0.6, data_completeness: 0.6, model_reliability: 0.6,
      prediction_stability: 0.6, composite: 0.6,
    },
    explanation: {
      top_positive_features: [], top_negative_features: [], feature_importance: {},
      knowledge_graph_evidence: [], news_contribution: [], community_contribution: [],
      ai_explanation: null,
    },
    feature_snapshot: {},
    model_version: '1',
    status: 'published',
    generated_at: new Date().toISOString(),
    data_freshness: null,
    probability_distribution: { HOME_WIN: 0.43, DRAW: 0.28, AWAY_WIN: 0.29 },
    confidence_interval: null,
    expected_error: null,
    contextual_review: null,
    football_explanation: null,
    prediction_status: 'READY',
    champion_status: 'ACTIVE',
    predictor_provenance: 'trained_model',
    explanation_status: 'GENERATED',
    ...overrides,
  }
}

describe('GeneratedIntelligencePanel — legacy evidence vs football explanation', () => {
  const legacyExplanation = {
    top_positive_features: [['football.fixture.form_corners_diff_last5', 0.4]] as Array<[string, number]>,
    top_negative_features: [] as Array<[string, number]>,
    feature_importance: {},
    knowledge_graph_evidence: [],
    news_contribution: [],
    community_contribution: [],
    ai_explanation: 'This verdict is driven mainly by Form Corners Diff (Last 5).',
  }

  it('hides the legacy Evidence/"Why TitanIQ believes this" block once the richer football explanation is available — no duplication', () => {
    render(
      <GeneratedIntelligencePanel
        marketName="Match Winner"
        prediction={fullPrediction({ explanation: legacyExplanation, football_explanation: footballExplanation() })}
        isGenerating={false}
        error={null}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )

    expect(screen.queryByText('Evidence')).not.toBeInTheDocument()
    expect(screen.queryByText('Why TitanIQ believes this')).not.toBeInTheDocument()
    expect(screen.getByText('Why this prediction')).toBeInTheDocument()
  })

  it('keeps the legacy block for sports with no football explanation (e.g. basketball) — never leaves the prediction unexplained', () => {
    render(
      <GeneratedIntelligencePanel
        marketName="Match Winner"
        prediction={fullPrediction({ explanation: legacyExplanation, football_explanation: null })}
        isGenerating={false}
        error={null}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )

    expect(screen.getByText('Evidence')).toBeInTheDocument()
    expect(screen.getByText('Why TitanIQ believes this')).toBeInTheDocument()
  })

  it('keeps the legacy block when the football explanation pipeline itself came back unavailable', () => {
    render(
      <GeneratedIntelligencePanel
        marketName="Match Winner"
        prediction={fullPrediction({
          explanation: legacyExplanation,
          football_explanation: footballExplanation({ status: 'unavailable', unavailable_reason: 'Champion model artifact unavailable.' }),
        })}
        isGenerating={false}
        error={null}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )

    expect(screen.getByText('Evidence')).toBeInTheDocument()
    expect(screen.getByText('Why TitanIQ believes this')).toBeInTheDocument()
  })
})

describe('GeneratedIntelligencePanel — football explanation counter-signals', () => {
  it('renders real counter-signals — evidence that argues against the verdict is never hidden', () => {
    render(
      <GeneratedIntelligencePanel
        marketName="Match Winner"
        prediction={fullPrediction({ football_explanation: footballExplanation() })}
        isGenerating={false}
        error={null}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )

    expect(screen.getByText('Counter-signals')).toBeInTheDocument()
    expect(screen.getByText('recent ability to generate attempts that test the goalkeeper')).toBeInTheDocument()
    expect(screen.getByText(/pushes against this lean/)).toBeInTheDocument()
  })

  it('renders nothing under "Counter-signals" when the model attributed none — never fabricates a counter-signal', () => {
    render(
      <GeneratedIntelligencePanel
        marketName="Match Winner"
        prediction={fullPrediction({ football_explanation: footballExplanation({ counter_signals: [] }) })}
        isGenerating={false}
        error={null}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )

    expect(screen.queryByText('Counter-signals')).not.toBeInTheDocument()
  })

  it('never leaks a raw ML feature key — model evidence renders as a football concept, not "form_fouls_diff_last5"', () => {
    render(
      <GeneratedIntelligencePanel
        marketName="Match Winner"
        prediction={fullPrediction({ football_explanation: footballExplanation() })}
        isGenerating={false}
        error={null}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )

    expect(screen.queryByText(/form_fouls_diff_last5/)).not.toBeInTheDocument()
    expect(screen.queryByText(/form_shots_on_target_diff_last5/)).not.toBeInTheDocument()
  })
})
