import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import InsightsPage from './insights-page'
import type { CommunityTopicDto, PredictionDto, PredictionSummaryDto, TeamSummaryDto } from '@/lib/api/types'

vi.mock('@/lib/api/sports', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/sports')>('@/lib/api/sports')
  return { ...actual, sportsApi: { listTeams: vi.fn(), listFixtures: vi.fn(), getFixture: vi.fn() } }
})
vi.mock('@/lib/api/predictions', () => ({ predictionsApi: { history: vi.fn(), compare: vi.fn(), get: vi.fn() } }))
vi.mock('@/lib/api/intelligence', () => ({ intelligenceApi: { communityTopics: vi.fn() } }))
vi.mock('@/lib/api/graph', () => ({ graphApi: { getEntity: vi.fn(), shortestPath: vi.fn() } }))
vi.mock('@/lib/hooks/use-realtime-invalidate', () => ({ useRealtimeInvalidate: vi.fn() }))

const { sportsApi } = await import('@/lib/api/sports')
const { predictionsApi } = await import('@/lib/api/predictions')
const { intelligenceApi } = await import('@/lib/api/intelligence')

const TEAM: TeamSummaryDto = { id: 't1', sport_code: 'football', name: 'Arsenal', short_name: 'ARS', country: 'England', venue_name: 'Emirates' }

function makePredictionSummary(id: string, value: string, confidence: number): PredictionSummaryDto {
  return {
    id,
    market_id: 'm1',
    model_id: 'model1',
    subject_ref: 't1',
    value,
    probability: confidence,
    confidence_composite: confidence,
    status: 'draft',
    generated_at: new Date().toISOString(),
  }
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
    explanation: {
      top_positive_features: [],
      top_negative_features: [],
      feature_importance: {},
      knowledge_graph_evidence: [],
      news_contribution: [],
      community_contribution: [],
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
  { id: 'c1', platform: 'community', topic_label: 'Low volume topic', related_entity_refs: [], post_count: 10, momentum: 0 },
  { id: 'c2', platform: 'community', topic_label: 'High volume topic', related_entity_refs: [], post_count: 500, momentum: 0.4 },
]

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

describe('InsightsPage (TitanIQ Assistant)', () => {
  it('shows the empty state and a real free-text input, not a disabled placeholder', () => {
    vi.mocked(intelligenceApi.communityTopics).mockResolvedValue([])
    renderPage()
    expect(screen.getByText('Pin something to get started')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Ask the Assistant' })).toBeInTheDocument()
  })

  it('pins a team and immediately shows its real prediction history', async () => {
    vi.mocked(sportsApi.listTeams).mockResolvedValue([TEAM])
    vi.mocked(predictionsApi.history).mockResolvedValue([makePredictionSummary('p1', 'Yes', 0.75)])
    vi.mocked(intelligenceApi.communityTopics).mockResolvedValue([])

    renderPage()

    await userEvent.click(screen.getByText('Football'))
    await userEvent.click(screen.getByText('Teams'))
    await userEvent.click(await screen.findByText('Arsenal'))

    await waitFor(() => expect(predictionsApi.history).toHaveBeenCalledWith('t1'))
    expect(await screen.findByText('Yes')).toBeInTheDocument()
  })

  it('compares two selected predictions and focuses evidence on click', async () => {
    vi.mocked(sportsApi.listTeams).mockResolvedValue([TEAM])
    vi.mocked(predictionsApi.history).mockResolvedValue([
      makePredictionSummary('p1', 'Yes', 0.75),
      makePredictionSummary('p2', 'No', 0.4),
    ])
    vi.mocked(predictionsApi.compare).mockResolvedValue([
      makePredictionSummary('p1', 'Yes', 0.75),
      makePredictionSummary('p2', 'No', 0.4),
    ])
    vi.mocked(predictionsApi.get).mockResolvedValue(makePrediction('p1', 'Yes', 0.75))
    vi.mocked(intelligenceApi.communityTopics).mockResolvedValue([])

    renderPage()
    await userEvent.click(screen.getByText('Football'))
    await userEvent.click(screen.getByText('Teams'))
    await userEvent.click(await screen.findByText('Arsenal'))
    await screen.findByText('Yes')

    const checkboxes = screen.getAllByRole('checkbox')
    await userEvent.click(checkboxes[0])
    await userEvent.click(checkboxes[1])

    const compareButton = screen.getByRole('button', { name: /Compare 2 selected/ })
    await userEvent.click(compareButton)

    await waitFor(() => expect(predictionsApi.compare).toHaveBeenCalledWith(['p1', 'p2']))
    expect(await screen.findByText('40.0%')).toBeInTheDocument()

    await userEvent.click(screen.getAllByText('Yes')[1])
    await waitFor(() => expect(predictionsApi.get).toHaveBeenCalledWith('p1'))
  })

  it('routes an unmatched free-text question to an honest fallback note', async () => {
    vi.mocked(intelligenceApi.communityTopics).mockResolvedValue([])
    renderPage()

    await userEvent.type(screen.getByRole('textbox', { name: 'Ask the Assistant' }), 'what is the weather today')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText(/free-form questions beyond that need a backend NL service/)).toBeInTheDocument()
  })

  it('auto-pins a fixture from a cross-link query param', async () => {
    vi.mocked(sportsApi.getFixture).mockResolvedValue({
      id: 'f1',
      season_id: 's1',
      competition_name: 'Premier League',
      home_team: { id: 'h1', name: 'Arsenal', short_name: 'ARS' },
      away_team: { id: 'a1', name: 'Chelsea', short_name: 'CHE' },
      venue_name: null,
      scheduled_at: new Date().toISOString(),
      status: 'scheduled',
      final_state: null,
    })
    vi.mocked(predictionsApi.history).mockResolvedValue([])
    vi.mocked(intelligenceApi.communityTopics).mockResolvedValue([])

    renderPage(['/app/insights?pin_type=fixture&pin_id=f1'])

    expect(await screen.findByText('ARS vs CHE')).toBeInTheDocument()
  })
})
