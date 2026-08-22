import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import LearningIntelligencePage from './learning-intelligence-page'
import { useAuthStore } from '@/stores/auth-store'

vi.mock('@/lib/api/predictions', () => ({
  predictionsApi: { monitoringSummary: vi.fn() },
}))
vi.mock('@/lib/api/markets', () => ({
  marketsApi: { list: vi.fn() },
}))
vi.mock('@/lib/api/ml-platform', () => ({
  mlPlatformApi: { champion: vi.fn(), listEvaluations: vi.fn(), featureImportance: vi.fn() },
}))

const { predictionsApi } = await import('@/lib/api/predictions')
const { marketsApi } = await import('@/lib/api/markets')
const { mlPlatformApi } = await import('@/lib/api/ml-platform')

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('LearningIntelligencePage', () => {
  it('renders the real pipeline and the monitoring summary as a key-value grid', async () => {
    vi.mocked(predictionsApi.monitoringSummary).mockResolvedValue({ total_predictions: 128, avg_confidence: 0.712 })
    vi.mocked(marketsApi.list).mockResolvedValue([])
    useAuthStore.setState({ profile: { id: 'u1', email: 'a@b.com', role: 'free', status: 'active', email_verified: true, created_at: '', last_login_at: null } })

    renderWithProviders(<LearningIntelligencePage />)

    expect(screen.getByText('Retraining Queue')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('128')).toBeInTheDocument())
    expect(screen.getByText(/restricted to administrator accounts/)).toBeInTheDocument()
  })

  it('shows the ML Operations console link for administrator roles instead of the restriction note', async () => {
    vi.mocked(predictionsApi.monitoringSummary).mockResolvedValue({})
    vi.mocked(marketsApi.list).mockResolvedValue([])
    useAuthStore.setState({ profile: { id: 'u2', email: 'admin@b.com', role: 'administrator', status: 'active', email_verified: true, created_at: '', last_login_at: null } })

    renderWithProviders(<LearningIntelligencePage />)

    const link = await screen.findByRole('link', { name: 'ML Operations console' })
    expect(link).toHaveAttribute('href', '/app/ops/ml')
  })

  it('lets a signed-in user pick a production market and see its real champion/evaluation/feature-importance data', async () => {
    vi.mocked(predictionsApi.monitoringSummary).mockResolvedValue({})
    vi.mocked(marketsApi.list).mockResolvedValue([
      {
        id: 'm1', market_key: 'football.match_result', sport_code: 'football', name: 'Match Result', category: 'outcome',
        market_kind: 'classification', target_type: 'classification', description: '', status: 'production',
        confidence_threshold: 0.6, explainability_required: true, owner: 'system',
      },
    ])
    vi.mocked(mlPlatformApi.champion).mockResolvedValue({ id: 'model-1', model_key: 'football.match_result.xgb', version: 2, status: 'champion' })
    vi.mocked(mlPlatformApi.listEvaluations).mockResolvedValue([
      { id: 'ev1', evaluated_at: new Date().toISOString(), metrics: { accuracy: 0.812 }, calibration_report: { expected_calibration_error: 0.031, brier_score: 0.19 } },
    ])
    vi.mocked(mlPlatformApi.featureImportance).mockResolvedValue({ model_id: 'model-1', global_importance: { form_last5: 0.42, xg_diff: -0.31 } })
    useAuthStore.setState({ profile: { id: 'u3', email: 'c@b.com', role: 'free', status: 'active', email_verified: true, created_at: '', last_login_at: null } })

    renderWithProviders(<LearningIntelligencePage />)

    await userEvent.click(await screen.findByText('Match Result'))

    expect(await screen.findByText('football.match_result.xgb')).toBeInTheDocument()
    expect(screen.getByText('form_last5')).toBeInTheDocument()
    expect(screen.getByText('0.0310')).toBeInTheDocument()
  })
})
