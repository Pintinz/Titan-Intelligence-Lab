import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PredictionIntelligenceSection } from './prediction-intelligence'
import type { FixtureSummaryDto, PredictionDto, PredictionMarketDto, PredictionSummaryDto } from '@/lib/api/types'

vi.mock('@/lib/api/predictions', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/predictions')>('@/lib/api/predictions')
  return { ...actual, predictionsApi: { history: vi.fn(), get: vi.fn(), review: vi.fn() } }
})

const { predictionsApi } = await import('@/lib/api/predictions')

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

function fixture(overrides: Partial<FixtureSummaryDto> = {}): FixtureSummaryDto {
  return {
    id: 'fixture-1',
    season_id: 'season-1',
    sport_code: 'football',
    competition_id: 'comp-1',
    competition_name: 'Premier League',
    competition_logo_url: null,
    home_team: { id: 'home-1', name: 'Manchester United', short_name: 'MUN', logo_url: null },
    away_team: { id: 'away-1', name: 'Ipswich Town FC', short_name: 'IPS', logo_url: null },
    venue_name: null,
    scheduled_at: '2026-08-30T15:30:00Z',
    status: 'scheduled',
    final_state: null,
    ...overrides,
  } as FixtureSummaryDto
}

function market(overrides: Partial<PredictionMarketDto> = {}): PredictionMarketDto {
  return {
    id: 'market-1',
    market_key: 'football.match_winner',
    sport_code: 'football',
    name: 'Match Winner',
    category: 'result',
    market_kind: 'three_way' as PredictionMarketDto['market_kind'],
    target_type: 'classification' as PredictionMarketDto['target_type'],
    description: '',
    status: 'production' as PredictionMarketDto['status'],
    confidence_threshold: 0.5,
    explainability_required: false,
    owner: 'system',
    ...overrides,
  } as PredictionMarketDto
}

function summary(overrides: Partial<PredictionSummaryDto> = {}): PredictionSummaryDto {
  return {
    id: 'pred-1',
    market_id: 'market-1',
    model_id: 'model-1',
    subject_ref: 'fixture-1',
    value: 'HOME_WIN',
    probability: 0.72,
    confidence_composite: 0.6,
    status: 'published',
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
    probability: 0.72,
    confidence: { composite: 0.6 } as PredictionDto['confidence'],
    explanation: {
      top_positive_features: [],
      top_negative_features: [],
      feature_importance: {},
      knowledge_graph_evidence: [],
      news_contribution: [],
      community_contribution: [],
      ai_explanation: 'Real grounded narration.',
    },
    feature_snapshot: {},
    model_version: '1',
    status: 'published',
    generated_at: new Date().toISOString(),
    data_freshness: null,
    probability_distribution: { HOME_WIN: 0.72, DRAW: 0.18, AWAY_WIN: 0.1 },
    confidence_interval: null,
    expected_error: null,
    contextual_review: null,
    football_explanation: null,
    prediction_status: 'READY',
    champion_status: 'ACTIVE',
    ...overrides,
  } as PredictionDto
}

describe('PredictionIntelligenceSection', () => {
  it('shows an honest empty state when the team has no upcoming fixture', () => {
    renderWithProviders(
      <PredictionIntelligenceSection nextFixture={undefined} markets={[market()]} marketsLoading={false} recentCompletedFixtures={[]} />,
    )
    expect(screen.getByText('No upcoming prediction')).toBeInTheDocument()
  })

  it('shows "coverage building" when the sport has no production markets yet', async () => {
    vi.mocked(predictionsApi.history).mockResolvedValue([])
    renderWithProviders(
      <PredictionIntelligenceSection nextFixture={fixture()} markets={[]} marketsLoading={false} recentCompletedFixtures={[]} />,
    )
    expect(await screen.findByText('Coverage building')).toBeInTheDocument()
  })

  it('never fabricates a prediction when none has been generated for the next fixture', async () => {
    vi.mocked(predictionsApi.history).mockResolvedValue([])
    renderWithProviders(
      <PredictionIntelligenceSection nextFixture={fixture()} markets={[market()]} marketsLoading={false} recentCompletedFixtures={[]} />,
    )
    expect(await screen.findByText('Prediction not available yet')).toBeInTheDocument()
  })

  it('renders the real generated prediction, market table, and cross-market interpretation when both markets exist', async () => {
    const matchWinnerMarket = market({ id: 'mw-market', market_key: 'football.match_winner', name: 'Match Winner' })
    const correctScoreMarket = market({ id: 'cs-market', market_key: 'football.correct_score', name: 'Correct Score' })
    vi.mocked(predictionsApi.history).mockResolvedValue([
      summary({ id: 'mw-pred', market_id: 'mw-market', value: 'HOME_WIN', probability: 0.742 }),
      summary({ id: 'cs-pred', market_id: 'cs-market', value: '1-1', probability: 0.104 }),
    ])
    vi.mocked(predictionsApi.get).mockImplementation((id: string) =>
      Promise.resolve(fullPrediction({ id, market_id: id === 'mw-pred' ? 'mw-market' : 'cs-market', value: id === 'mw-pred' ? 'HOME_WIN' : '1-1' })),
    )
    vi.mocked(predictionsApi.review).mockResolvedValue({ markets: [], meta: { market_count: 0, resolved_count: 0, correct_count: 0, accuracy: null, average_confidence: null } })

    renderWithProviders(
      <PredictionIntelligenceSection
        nextFixture={fixture()}
        markets={[matchWinnerMarket, correctScoreMarket]}
        marketsLoading={false}
        recentCompletedFixtures={[]}
      />,
    )

    expect(await screen.findByText('Manchester United', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByText('Market interpretation')).toBeInTheDocument()
    expect(screen.getByText(/These markets measure different probability distributions/)).toBeInTheDocument()
    expect(screen.getByText('Market intelligence')).toBeInTheDocument()
  })

  it('omits the prediction history panel entirely when nothing has been resolved yet — never a fabricated 0%', async () => {
    vi.mocked(predictionsApi.history).mockResolvedValue([])
    vi.mocked(predictionsApi.review).mockResolvedValue({ markets: [], meta: { market_count: 0, resolved_count: 0, correct_count: 0, accuracy: null, average_confidence: null } })

    renderWithProviders(
      <PredictionIntelligenceSection
        nextFixture={undefined}
        markets={[market()]}
        marketsLoading={false}
        recentCompletedFixtures={[fixture({ id: 'completed-1', status: 'completed' })]}
      />,
    )

    await waitFor(() => expect(predictionsApi.review).toHaveBeenCalled())
    expect(screen.queryByText('Prediction intelligence')).not.toBeInTheDocument()
  })

  it('aggregates real resolved counts into the prediction history panel when outcomes exist', async () => {
    vi.mocked(predictionsApi.history).mockResolvedValue([])
    vi.mocked(predictionsApi.review).mockResolvedValue({
      markets: [],
      meta: { market_count: 1, resolved_count: 4, correct_count: 3, accuracy: 0.75, average_confidence: 0.62 },
    })

    renderWithProviders(
      <PredictionIntelligenceSection
        nextFixture={undefined}
        markets={[market()]}
        marketsLoading={false}
        recentCompletedFixtures={[fixture({ id: 'completed-1', status: 'completed' })]}
      />,
    )

    expect(await screen.findByText('Prediction intelligence')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
  })
})
