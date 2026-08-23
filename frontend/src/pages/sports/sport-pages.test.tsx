import { beforeAll, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SportShell } from '@/components/layout/sport-shell'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { useAuthStore } from '@/stores/auth-store'
import PredictionLabPage from './prediction-lab-page'
import type { FixtureSummaryDto, PredictionDto, PredictionMarketDto } from '@/lib/api/types'

// Basketball/Baseball/Table Tennis are gated to administrators only (still under development —
// see SportShell's non-football guard). This suite verifies the sport-agnostic plumbing itself
// works correctly across all 4 sports, which is exactly what an admin exercises while building/
// QA-ing the other sports — so it runs as an admin, not the "regular user sees only Football"
// default this test environment would otherwise have.
beforeAll(() => {
  useAuthStore.setState({
    profile: {
      id: 'test-admin', email: 'admin@titaniq.test', role: 'administrator', status: 'active',
      email_verified: true, created_at: new Date().toISOString(), last_login_at: null,
    },
  })
})

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
    // Prediction Laboratory/News/Community were deliberately pulled from the tab bar
    // (sport-shell.tsx) — only Matches/Teams/Players/Competitions carry primary nav weight.
    // "Live" was pulled too (2026-08-23) — match-list-page.tsx already surfaces live fixtures
    // via its own LiveRail, so a separate primary Live destination was pure duplication.
    expect(screen.getByRole('link', { name: 'Matches' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Live' })).not.toBeInTheDocument()
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
      include_contextual_review: true,
      include_football_explanation: true,
    })
  })
})

// Phase 3: the Football Intelligence Center built in Phase 2 is generic and sport-parameterized,
// not football-specific — "only market types differ by sport" (brief). These tests prove that
// claim across all four real sports rather than assuming it from football alone.
describe('Sport Intelligence Center genericity (Phase 3)', () => {
  it.each(SPORT_SLUGS)('$label: SportShell resolves the :sport param and shows the right label', ({ slug, label }) => {
    renderAtSport(`/app/${slug}`, <div />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it.each(SPORT_SLUGS)('$label: Prediction Laboratory requests production markets scoped to this sport', async ({ slug, code }) => {
    vi.mocked(marketsApi.list).mockResolvedValue([])
    renderAtSport(`/app/${slug}/lab`, <PredictionLabPage />)
    await waitFor(() => expect(marketsApi.list).toHaveBeenCalledWith({ sport_code: code, status: 'production' }))
  })
})
