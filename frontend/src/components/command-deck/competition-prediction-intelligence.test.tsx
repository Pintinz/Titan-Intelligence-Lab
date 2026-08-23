import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CompetitionPredictionIntelligence } from './competition-prediction-intelligence'
import type { FixtureSummaryDto, PredictionMarketDto, PredictionSummaryDto } from '@/lib/api/types'

vi.mock('@/lib/api/predictions', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/predictions')>('@/lib/api/predictions')
  return { ...actual, predictionsApi: { history: vi.fn(), review: vi.fn() } }
})

const { predictionsApi } = await import('@/lib/api/predictions')

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function fixture(id: string): FixtureSummaryDto {
  return {
    id,
    season_id: 's1',
    sport_code: 'football',
    competition_id: 'comp-1',
    competition_name: 'Premier League',
    competition_logo_url: null,
    home_team: { id: 'h', name: 'Home FC', short_name: 'HOM', logo_url: null },
    away_team: { id: 'a', name: 'Away FC', short_name: 'AWY', logo_url: null },
    venue_name: null,
    scheduled_at: '2026-08-30T15:30:00Z',
    status: 'scheduled',
    final_state: null,
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
    subject_ref: 'f1',
    value: 'HOME_WIN',
    probability: 0.6,
    confidence_composite: 0.55,
    status: 'published',
    generated_at: new Date().toISOString(),
    ...overrides,
  }
}

describe('CompetitionPredictionIntelligence', () => {
  it('never shows a fixture with nothing generated for it', async () => {
    vi.mocked(predictionsApi.history).mockResolvedValue([])
    vi.mocked(predictionsApi.review).mockResolvedValue({ markets: [], meta: { market_count: 0, resolved_count: 0, correct_count: 0, accuracy: null, average_confidence: null } })

    renderWithProviders(
      <CompetitionPredictionIntelligence upcomingFixtures={[fixture('f1')]} completedFixtures={[]} markets={[market()]} marketsLoading={false} sportSlug="football" />,
    )

    expect(await screen.findByText('No predicted matches yet')).toBeInTheDocument()
  })

  it('renders only fixtures with a real generated prediction', async () => {
    vi.mocked(predictionsApi.history).mockResolvedValue([summary()])
    vi.mocked(predictionsApi.review).mockResolvedValue({ markets: [], meta: { market_count: 0, resolved_count: 0, correct_count: 0, accuracy: null, average_confidence: null } })

    renderWithProviders(
      <CompetitionPredictionIntelligence upcomingFixtures={[fixture('f1')]} completedFixtures={[]} markets={[market()]} marketsLoading={false} sportSlug="football" />,
    )

    expect(await screen.findByText('Home FC vs Away FC')).toBeInTheDocument()
    expect(screen.getByText('Match Winner')).toBeInTheDocument()
  })

  it('never renders 0% accuracy when zero predictions have resolved — shows honest unavailable message instead', async () => {
    vi.mocked(predictionsApi.history).mockResolvedValue([])
    vi.mocked(predictionsApi.review).mockResolvedValue({ markets: [], meta: { market_count: 0, resolved_count: 0, correct_count: 0, accuracy: null, average_confidence: null } })

    renderWithProviders(
      <CompetitionPredictionIntelligence
        upcomingFixtures={[]}
        completedFixtures={[{ ...fixture('c1'), status: 'completed' }]}
        markets={[market()]}
        marketsLoading={false}
        sportSlug="football"
      />,
    )

    expect(await screen.findByText('Prediction performance unavailable')).toBeInTheDocument()
    expect(screen.getByText('No resolved production predictions are currently available for this competition.')).toBeInTheDocument()
    expect(screen.queryByText('0%')).not.toBeInTheDocument()
  })
})
