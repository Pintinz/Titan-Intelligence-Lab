import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import MatchDetailPage from './match-detail-page'
import type { FixtureSummaryDto, PredictionDto, PredictionMarketDto } from '@/lib/api/types'

vi.mock('@/lib/api/sports', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/sports')>('@/lib/api/sports')
  return { ...actual, sportsApi: { getFixture: vi.fn(), teamFixtures: vi.fn(), fixtureStatistics: vi.fn() } }
})
vi.mock('@/lib/api/markets', () => ({ marketsApi: { list: vi.fn() } }))
vi.mock('@/lib/api/predictions', () => ({ predictionsApi: { generate: vi.fn() } }))
vi.mock('@/lib/hooks/use-realtime-invalidate', () => ({ useRealtimeInvalidate: vi.fn() }))

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

const RELATED_FIXTURE: FixtureSummaryDto = {
  id: 'fx-2',
  season_id: 's1',
  competition_name: 'Premier League',
  home_team: { id: 't1', name: 'Arsenal', short_name: 'ARS' },
  away_team: { id: 't3', name: 'Fulham', short_name: 'FUL' },
  venue_name: 'Emirates Stadium',
  // A real recent-form entry is a completed match with a real score — Recent Form now renders
  // only fixtures with a real recorded result (never a fabricated 0-0 for a scoreless fixture).
  scheduled_at: new Date(Date.now() - 7 * 24 * 3600_000).toISOString(),
  status: 'completed',
  final_state: { home: 2, away: 1 },
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
    feature_quality: 0.9,
    feature_freshness: 0.9,
    historical_accuracy: 0.8,
    knowledge_graph_completeness: 0.85,
    news_reliability: 0.7,
    community_reliability: 0.9,
    data_completeness: 0.85,
    model_reliability: 0.88,
    prediction_stability: 0.8,
    composite: 0.81,
  },
  explanation: {
    top_positive_features: [['form_shots_on_target_last5', 0.3]],
    top_negative_features: [],
    feature_importance: {},
    knowledge_graph_evidence: [],
    news_contribution: [],
    community_contribution: [],
    ai_explanation: 'Both attacks are in strong scoring form.',
  },
  feature_snapshot: {},
  model_version: '1.0.0',
  status: 'draft',
  generated_at: new Date().toISOString(),
  data_freshness: null,
  probability_distribution: { Yes: 0.81, No: 0.19 },
  confidence_interval: null,
  expected_error: null,
  contextual_review: null,
}

function renderPage(matchId = 'fx-1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/app/football/matches/${matchId}`]}>
        <Routes>
          <Route path="/app/:sport/matches/:matchId" element={<MatchDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MatchDetailPage', () => {
  it('renders the match hero and walks market selection through to a generated prediction', async () => {
    vi.mocked(sportsApi.getFixture).mockResolvedValue(FIXTURE)
    vi.mocked(sportsApi.teamFixtures).mockResolvedValue([])
    vi.mocked(marketsApi.list).mockResolvedValue([MARKET])
    vi.mocked(predictionsApi.generate).mockResolvedValue(PREDICTION)

    renderPage()

    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Arsenal vs Chelsea'))
    expect(screen.getByText('Premier League')).toBeInTheDocument()
    expect(screen.getByText('Emirates Stadium')).toBeInTheDocument()

    await userEvent.click(await screen.findByText('Both Teams to Score'))
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Intelligence — Both Teams to Score' }))

    await waitFor(() => expect(screen.getByText('Both attacks are in strong scoring form.')).toBeInTheDocument())
    expect(predictionsApi.generate).toHaveBeenCalledWith({
      market_key: 'football.both_teams_to_score',
      entity_type: 'fixture',
      entity_id: 'fx-1',
      subject_ref: 'fx-1',
      include_football_explanation: true,
      include_contextual_review: true,
    })
    expect(screen.getByText('Form Shots On Target (Last 5)', { exact: false })).toBeInTheDocument()
  })

  it('renders the Contextual Review section when the backend returns one', async () => {
    vi.mocked(sportsApi.getFixture).mockResolvedValue(FIXTURE)
    vi.mocked(sportsApi.teamFixtures).mockResolvedValue([])
    vi.mocked(marketsApi.list).mockResolvedValue([MARKET])
    vi.mocked(predictionsApi.generate).mockResolvedValue({
      ...PREDICTION,
      contextual_review: {
        review_status: 'SUPPORTED',
        overall_assessment: 'Fresh evidence aligns with the base prediction.',
        confidence_level: 'HIGH',
        confidence_score: 0.82,
        statistical_baseline: { applicable: true, available: true, algorithm: 'poisson_goals_model', probabilities: { Yes: 0.79, No: 0.21 }, reason: null },
        contextual_assessment: { injuries: { impact: 'POSITIVE', strength: 'MODERATE', score: 0.6, reason: 'Both attacking lineups are fully available.' } },
        supporting_factors: [{ factor: 'lineup_availability', impact: 'POSITIVE', strength: 'MODERATE', evidence: 'Both first-choice attackers confirmed starting.', source_ids: ['src-1'] }],
        risk_factors: [],
        missing_context: [],
        reconsideration: { direction: 'SUPPORTS_BASE_PREDICTION', material_change: false, reason: 'No new information changes the outlook.' },
        evidence_quality: { overall: 'HIGH', source_count: 2, timestamp_valid: true, pre_event_only: true, conflicting_information: false },
        source_ids: ['src-1', 'src-2'],
        prediction_cutoff: new Date().toISOString(),
        prompt_version: 'v1',
        generated_at: new Date().toISOString(),
      },
    })

    renderPage()

    await userEvent.click(await screen.findByText('Both Teams to Score'))
    await userEvent.click(await screen.findByRole('button', { name: 'Generate Intelligence — Both Teams to Score' }))

    await waitFor(() => expect(screen.getByText('Contextual review')).toBeInTheDocument())
    expect(screen.getByText('Fresh evidence aligns with the base prediction.')).toBeInTheDocument()
    expect(screen.getByText('Supported by current evidence')).toBeInTheDocument()
    expect(screen.getByText('Both first-choice attackers confirmed starting.')).toBeInTheDocument()
  })

  it('splits recent form into home/away columns excluding the current fixture', async () => {
    vi.mocked(sportsApi.getFixture).mockResolvedValue(FIXTURE)
    vi.mocked(sportsApi.teamFixtures).mockImplementation((teamId: string) =>
      Promise.resolve(teamId === 't1' ? [FIXTURE, RELATED_FIXTURE] : []),
    )
    vi.mocked(sportsApi.fixtureStatistics).mockResolvedValue([])
    vi.mocked(marketsApi.list).mockResolvedValue([])

    renderPage()

    // Home form (Arsenal, t1) is mocked with [FIXTURE, RELATED_FIXTURE] — the current fixture
    // (fx-1) must be excluded from its own team's "recent form", leaving only the related
    // fixture (fx-2, Arsenal vs Fulham) — proves the exclude-current-match filter works.
    await waitFor(() => expect(screen.getByText('Fulham')).toBeInTheDocument())

    // Away form (Chelsea, t2) is mocked with [] — its own empty state must render, not a
    // duplicate of the current match card.
    expect(await screen.findByText('No recent matches yet')).toBeInTheDocument()
  })
})
