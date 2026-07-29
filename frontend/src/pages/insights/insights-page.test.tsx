import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import InsightsPage from './insights-page'
import type { CommunityTopicDto, PredictionDto, TeamSummaryDto } from '@/lib/api/types'

vi.mock('@/lib/api/sports', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/sports')>('@/lib/api/sports')
  return { ...actual, sportsApi: { listTeams: vi.fn() } }
})
vi.mock('@/lib/api/markets', () => ({ marketsApi: { list: vi.fn() } }))
vi.mock('@/lib/api/predictions', () => ({ predictionsApi: { history: vi.fn(), compare: vi.fn() } }))
vi.mock('@/lib/api/intelligence', () => ({ intelligenceApi: { communityTopics: vi.fn() } }))

const { sportsApi } = await import('@/lib/api/sports')
const { marketsApi } = await import('@/lib/api/markets')
const { predictionsApi } = await import('@/lib/api/predictions')
const { intelligenceApi } = await import('@/lib/api/intelligence')

const TEAM: TeamSummaryDto = { id: 't1', sport_code: 'football', name: 'Arsenal', short_name: 'ARS', country: 'England', venue_name: 'Emirates' }

function makePrediction(id: string, value: string, confidence: number): PredictionDto {
  return {
    id,
    market_id: 'm1',
    model_id: 'model1',
    subject_ref: 't1',
    value,
    probability: confidence,
    confidence: {
      overall: confidence,
      data_quality: 0.9,
      feature_completeness: 0.9,
      model_certainty: confidence,
      historical_accuracy: 0.8,
      sample_size_adequacy: 0.85,
      market_liquidity: 0.7,
      temporal_relevance: 0.9,
      ensemble_agreement: 0.85,
      calibration_quality: 0.88,
      volatility_penalty: 0.1,
    },
    explanation: {
      top_positive_features: [],
      top_negative_features: [],
      feature_importance: {},
      knowledge_graph_contribution: null,
      news_contribution: null,
      community_contribution: null,
      ai_explanation: null,
    },
    feature_snapshot: {},
    model_version: '1.0.0',
    status: 'draft',
    generated_at: new Date().toISOString(),
    data_freshness: null,
  }
}

const COMMUNITY: CommunityTopicDto[] = [
  { id: 'c1', platform: 'community', title: 'Low volume topic', volume: 10, sentiment_score: 0 },
  { id: 'c2', platform: 'community', title: 'High volume topic', volume: 500, sentiment_score: 0.4 },
]

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <InsightsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('InsightsPage', () => {
  it('shows the disabled chat affordance, not a functional free-text input', () => {
    renderPage()
    expect(screen.getByText('Ask TitanIQ anything — coming soon')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('sorts community topics by volume, highest first', async () => {
    vi.mocked(intelligenceApi.communityTopics).mockResolvedValue(COMMUNITY)
    renderPage()
    const items = await screen.findAllByText(/volume topic/)
    expect(items[0]).toHaveTextContent('High volume topic')
    expect(items[1]).toHaveTextContent('Low volume topic')
  })

  it('walks sport -> team selection to prediction history, and expands a row to the full explanation', async () => {
    vi.mocked(sportsApi.listTeams).mockResolvedValue([TEAM])
    vi.mocked(marketsApi.list).mockResolvedValue([])
    vi.mocked(intelligenceApi.communityTopics).mockResolvedValue([])
    vi.mocked(predictionsApi.history).mockResolvedValue([makePrediction('p1', 'Yes', 0.75)])

    renderPage()

    await userEvent.click(screen.getByRole('combobox', { name: 'Sport' }))
    await userEvent.click(await screen.findByText('Football'))

    await userEvent.click(screen.getByRole('combobox', { name: 'Team' }))
    await userEvent.click(await screen.findByText('Arsenal'))

    await waitFor(() => expect(predictionsApi.history).toHaveBeenCalledWith('t1', undefined))
    expect(await screen.findByText('Yes')).toBeInTheDocument()

    await userEvent.click(screen.getByText('Yes'))
    expect(await screen.findByText('Confidence factors')).toBeInTheDocument()
  })

  it('compares two selected predictions side by side', async () => {
    vi.mocked(sportsApi.listTeams).mockResolvedValue([TEAM])
    vi.mocked(marketsApi.list).mockResolvedValue([])
    vi.mocked(intelligenceApi.communityTopics).mockResolvedValue([])
    vi.mocked(predictionsApi.history).mockResolvedValue([makePrediction('p1', 'Yes', 0.75), makePrediction('p2', 'No', 0.4)])
    vi.mocked(predictionsApi.compare).mockResolvedValue([makePrediction('p1', 'Yes', 0.75), makePrediction('p2', 'No', 0.4)])

    renderPage()
    await userEvent.click(screen.getByRole('combobox', { name: 'Sport' }))
    await userEvent.click(await screen.findByText('Football'))
    await userEvent.click(screen.getByRole('combobox', { name: 'Team' }))
    await userEvent.click(await screen.findByText('Arsenal'))
    await screen.findByText('Yes')

    const checkboxes = screen.getAllByRole('checkbox', { name: 'Select for comparison' })
    await userEvent.click(checkboxes[0])
    await userEvent.click(checkboxes[1])

    const compareButton = screen.getByRole('button', { name: /Compare 2 selected/ })
    expect(compareButton).toBeEnabled()
    await userEvent.click(compareButton)

    await waitFor(() => expect(predictionsApi.compare).toHaveBeenCalledWith(['p1', 'p2']))
    expect(await screen.findByText('40.0%')).toBeInTheDocument()
  })
})
