import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import InsightsPage from './insights-page'
import type { FixtureSummaryDto, PredictionDto, PredictionMarketDto, PredictionSummaryDto, TeamSummaryDto } from '@/lib/api/types'

vi.mock('@/lib/api/sports', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/sports')>('@/lib/api/sports')
  return {
    ...actual,
    sportsApi: {
      listTeams: vi.fn(),
      listFixtures: vi.fn(),
      listCompetitions: vi.fn(),
      listPlayers: vi.fn(),
      getTeam: vi.fn(),
      getFixture: vi.fn(),
      getCompetition: vi.fn(),
      getPlayer: vi.fn(),
    },
  }
})
vi.mock('@/lib/api/markets', () => ({ marketsApi: { list: vi.fn() } }))
vi.mock('@/lib/api/predictions', () => ({ predictionsApi: { history: vi.fn(), compare: vi.fn(), get: vi.fn(), generate: vi.fn() } }))
vi.mock('@/lib/api/intelligence', () => ({ intelligenceApi: { newsForEntity: vi.fn() } }))
vi.mock('@/lib/api/graph', () => ({ graphApi: { getEntity: vi.fn(), context: vi.fn() } }))

const { sportsApi } = await import('@/lib/api/sports')
const { marketsApi } = await import('@/lib/api/markets')
const { predictionsApi } = await import('@/lib/api/predictions')
const { intelligenceApi } = await import('@/lib/api/intelligence')
const { graphApi } = await import('@/lib/api/graph')

const TEAM: TeamSummaryDto = { id: 't1', sport_code: 'football', name: 'Arsenal', short_name: 'ARS', country: 'England', venue_name: 'Emirates', logo_url: null }

const MARKET: PredictionMarketDto = {
  id: 'm1',
  market_key: 'football.match_winner',
  sport_code: 'football',
  name: 'Match Winner',
  category: 'winner',
  market_kind: 'classification',
  target_type: 'classification',
  description: 'Who wins the match',
  status: 'production',
  confidence_threshold: 0.55,
  explainability_required: true,
  owner: 'predictions',
}

function makePredictionSummary(id: string, marketId: string, value: string, confidence: number): PredictionSummaryDto {
  return { id, market_id: marketId, model_id: 'model1', subject_ref: 't1', value, probability: confidence, confidence_composite: confidence, status: 'draft', generated_at: new Date().toISOString() }
}

function makePrediction(id: string, value: string, confidence: number): PredictionDto {
  return {
    id,
    market_id: 'm1',
    model_id: 'model1',
    subject_ref: 't1',
    value,
    probability: confidence,
    confidence: {
      feature_quality: 0.9,
      feature_freshness: 0.9,
      historical_accuracy: 0.8,
      knowledge_graph_completeness: 0.85,
      news_reliability: 0.7,
      community_reliability: 0.9,
      data_completeness: 0.85,
      model_reliability: 0.88,
      prediction_stability: 0.8,
      composite: confidence,
    },
    explanation: { top_positive_features: [], top_negative_features: [], feature_importance: {}, knowledge_graph_evidence: [], news_contribution: [], community_contribution: [], ai_explanation: null },
    feature_snapshot: {},
    model_version: '1.0.0',
    status: 'draft',
    generated_at: new Date().toISOString(),
    data_freshness: null,
    probability_distribution: { [value]: confidence },
    confidence_interval: null,
    expected_error: null,
    contextual_review: null,
  }
}

const FIXTURE: FixtureSummaryDto = {
  id: 'f1',
  season_id: 's1',
  sport_code: 'football',
  competition_id: 'c1',
  competition_name: 'Premier League',
  competition_logo_url: null,
  competition_tier: 1,
  home_team: { id: 'h1', name: 'Arsenal', short_name: 'ARS', logo_url: null },
  away_team: { id: 'a1', name: 'Chelsea', short_name: 'CHE', logo_url: null },
  venue_name: null,
  scheduled_at: new Date().toISOString(),
  status: 'scheduled',
  final_state: null,
}

function renderPage(initialEntries: string[] = ['/app/insights']) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <InsightsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function mockDefaults() {
  vi.mocked(sportsApi.listFixtures).mockResolvedValue([])
  vi.mocked(sportsApi.listTeams).mockResolvedValue([])
  vi.mocked(sportsApi.listCompetitions).mockResolvedValue([])
  vi.mocked(sportsApi.listPlayers).mockResolvedValue([])
  vi.mocked(marketsApi.list).mockResolvedValue([])
  vi.mocked(intelligenceApi.newsForEntity).mockResolvedValue([])
  vi.mocked(graphApi.getEntity).mockRejectedValue(new Error('not found'))
}

describe('InsightsPage (Intelligence Workspace)', () => {
  it('shows the Start an Investigation empty state, not a chat placeholder', async () => {
    mockDefaults()
    renderPage()
    expect(await screen.findByText('Start an Investigation')).toBeInTheDocument()
    expect(screen.queryByText('Pin something to get started')).not.toBeInTheDocument()
  })

  it('pins a team from search and shows its Mission Brief coverage', async () => {
    mockDefaults()
    vi.mocked(sportsApi.listTeams).mockResolvedValue([TEAM])
    vi.mocked(marketsApi.list).mockResolvedValue([MARKET])
    vi.mocked(predictionsApi.history).mockResolvedValue([makePredictionSummary('p1', 'm1', 'Yes', 0.75)])

    renderPage()

    await userEvent.click(screen.getByText('Teams'))
    await userEvent.type(screen.getByPlaceholderText(/Search matches, teams, competitions/), 'Arsenal')
    await userEvent.click(await screen.findByText('Arsenal'))

    await waitFor(() => expect(predictionsApi.history).toHaveBeenCalledWith('t1'))
    expect(await screen.findByText('Mission Brief')).toBeInTheDocument()
    expect(await screen.findByText('1/1')).toBeInTheDocument()
  })

  it('auto-pins a fixture from a cross-link query param', async () => {
    mockDefaults()
    vi.mocked(sportsApi.getFixture).mockResolvedValue(FIXTURE)
    vi.mocked(predictionsApi.history).mockResolvedValue([])

    renderPage(['/app/insights?pin_type=fixture&pin_id=f1'])

    expect((await screen.findAllByText('ARS vs CHE')).length).toBeGreaterThan(0)
  })

  it('opens the Evidence Inspector for a generated prediction', async () => {
    mockDefaults()
    vi.mocked(sportsApi.getFixture).mockResolvedValue(FIXTURE)
    vi.mocked(marketsApi.list).mockResolvedValue([MARKET])
    vi.mocked(predictionsApi.history).mockResolvedValue([makePredictionSummary('p1', 'm1', 'HOME_WIN', 0.75)])
    vi.mocked(predictionsApi.get).mockResolvedValue(makePrediction('p1', 'HOME_WIN', 0.75))

    renderPage(['/app/insights?pin_type=fixture&pin_id=f1'])
    await waitFor(async () => expect((await screen.findAllByText('ARS vs CHE')).length).toBeGreaterThan(0))

    await userEvent.click(screen.getByRole('button', { name: 'Predictions' }))
    await userEvent.click(await screen.findByText('View evidence →'))

    await waitFor(() => expect(predictionsApi.get).toHaveBeenCalledWith('p1'))
    expect(await screen.findByText('Evidence Inspector')).toBeInTheDocument()
  })
})
