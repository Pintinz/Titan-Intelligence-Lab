import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SportShell } from '@/components/layout/sport-shell'
import SportHubPage from './sport-hub-page'
import MatchListPage from './match-list-page'
import PredictionLabPage from './prediction-lab-page'
import type { FixtureSummaryDto, PredictionDto, PredictionMarketDto } from '@/lib/api/types'

vi.mock('@/lib/api/sports', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/sports')>('@/lib/api/sports')
  return { ...actual, sportsApi: { listFixtures: vi.fn() } }
})
vi.mock('@/lib/api/markets', () => ({ marketsApi: { list: vi.fn() } }))
vi.mock('@/lib/api/predictions', () => ({ predictionsApi: { generate: vi.fn() } }))

const { sportsApi } = await import('@/lib/api/sports')
const { marketsApi } = await import('@/lib/api/markets')
const { predictionsApi } = await import('@/lib/api/predictions')

const FIXTURE: FixtureSummaryDto = {
  id: 'fx-1',
  season_id: 's1',
  competition_name: 'Premier League',
  home_team: { id: 't1', name: 'Arsenal', short_name: 'ARS' },
  away_team: { id: 't2', name: 'Chelsea', short_name: 'CHE' },
  venue_name: 'Emirates Stadium',
  scheduled_at: new Date().toISOString(),
  status: 'scheduled',
  final_state: null,
}

const MARKET: PredictionMarketDto = {
  id: 'm1',
  market_key: 'football.both_teams_to_score',
  sport_code: 'football',
  name: 'Both Teams to Score',
  category: 'goals',
  market_kind: 'classification',
  target_type: 'classification',
  description: 'Will both teams score',
  status: 'production',
  confidence_threshold: 0.6,
  explainability_required: true,
  owner: 'system',
}

const PREDICTION: PredictionDto = {
  id: 'p1',
  market_id: 'm1',
  model_id: 'model1',
  subject_ref: 'fx-1',
  value: 'Yes',
  probability: 0.81,
  confidence: {
    overall: 0.81,
    data_quality: 0.9,
    feature_completeness: 0.9,
    model_certainty: 0.81,
    historical_accuracy: 0.8,
    sample_size_adequacy: 0.85,
    market_liquidity: 0.7,
    temporal_relevance: 0.9,
    ensemble_agreement: 0.85,
    calibration_quality: 0.88,
    volatility_penalty: 0.1,
  },
  explanation: {
    top_positive_features: [{ feature_key: 'form_shots_on_target_last5', contribution: 0.3 }],
    top_negative_features: [],
    feature_importance: {},
    knowledge_graph_contribution: null,
    news_contribution: null,
    community_contribution: null,
    ai_explanation: 'Both attacks are in strong scoring form.',
  },
  feature_snapshot: {},
  model_version: '1.0.0',
  status: 'draft',
  generated_at: new Date().toISOString(),
  data_freshness: null,
}

function renderAtSport(path: string, element: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/:sport" element={<SportShell />}>
            <Route index element={element} />
            <Route path="matches" element={element} />
            <Route path="lab" element={element} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SportShell', () => {
  it('shows an unknown-sport state for an unrecognized slug', () => {
    renderAtSport('/app/cricket', <div />)
    expect(screen.getByText('Unknown sport')).toBeInTheDocument()
  })

  it('renders the sub-nav for a known sport', () => {
    renderAtSport('/app/football', <div />)
    expect(screen.getByText('Football')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Prediction Laboratory' })).toBeInTheDocument()
  })
})

describe('SportHubPage', () => {
  it('renders fixtures once loaded', async () => {
    vi.mocked(sportsApi.listFixtures).mockResolvedValue([FIXTURE])
    renderAtSport('/app/football', <SportHubPage />)
    await waitFor(() => expect(screen.getByText('Arsenal vs Chelsea')).toBeInTheDocument())
  })

  it('renders an empty state when there are no fixtures', async () => {
    vi.mocked(sportsApi.listFixtures).mockResolvedValue([])
    renderAtSport('/app/football', <SportHubPage />)
    await waitFor(() => expect(screen.getByText('No fixtures under coverage')).toBeInTheDocument())
  })
})

describe('MatchListPage', () => {
  it('renders an error state when the fixture query fails, and recovers on retry', async () => {
    vi.mocked(sportsApi.listFixtures).mockRejectedValueOnce(new Error('network down')).mockResolvedValueOnce([FIXTURE])
    renderAtSport('/app/football/matches', <MatchListPage />)
    await waitFor(() => expect(screen.getByText("Couldn't load this")).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByText('Arsenal vs Chelsea')).toBeInTheDocument())
  })
})

describe('PredictionLabPage', () => {
  it('walks market selection through to a generated prediction', async () => {
    vi.mocked(marketsApi.list).mockResolvedValue([MARKET])
    vi.mocked(sportsApi.listFixtures).mockResolvedValue([FIXTURE])
    vi.mocked(predictionsApi.generate).mockResolvedValue(PREDICTION)

    renderAtSport('/app/football/lab', <PredictionLabPage />)

    await waitFor(() => expect(screen.getByText('Both Teams to Score')).toBeInTheDocument())
    await userEvent.click(screen.getByText('Both Teams to Score'))

    const select = await screen.findByRole('combobox')
    await userEvent.click(select)
    const option = await screen.findByText(/Arsenal vs Chelsea/)
    await userEvent.click(option)

    const generateButton = await screen.findByRole('button', { name: 'Generate prediction' })
    await userEvent.click(generateButton)

    await waitFor(() => expect(screen.getByText('Both attacks are in strong scoring form.')).toBeInTheDocument())
    expect(predictionsApi.generate).toHaveBeenCalledWith({
      market_key: 'football.both_teams_to_score',
      entity_type: 'fixture',
      entity_id: 'fx-1',
      subject_ref: 'fx-1',
    })
  })
})
