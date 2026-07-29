import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import NewsIntelligencePage from './news-intelligence-page'
import LearningIntelligencePage from './learning-intelligence-page'
import { useAuthStore } from '@/stores/auth-store'
import type { ImpactScoreDto, NewsArticleDto, NewsEventDto } from '@/lib/api/types'

vi.mock('@/lib/api/intelligence', () => ({
  intelligenceApi: { searchNews: vi.fn(), impact: vi.fn(), newsTimeline: vi.fn() },
}))
vi.mock('@/lib/api/predictions', () => ({
  predictionsApi: { monitoringSummary: vi.fn() },
}))

const { intelligenceApi } = await import('@/lib/api/intelligence')
const { predictionsApi } = await import('@/lib/api/predictions')

function renderWithProviders(ui: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const ARTICLE: NewsArticleDto = {
  id: 'a1',
  source_id: 'wire',
  title: 'Chelsea reshuffles back line',
  url: 'https://example.com/article',
  published_at: new Date().toISOString(),
  entities: ['Chelsea'],
}

const EVENT: NewsEventDto = {
  id: 'e1',
  headline: 'Chelsea defender cleared to start',
  occurred_at: new Date().toISOString(),
  entity_refs: ['team:chelsea'],
  category: 'lineup',
}

const IMPACT: ImpactScoreDto = {
  id: 'i1',
  news_event_id: 'e1',
  entity_ref: 'team:chelsea',
  impact_score: 0.42,
  rationale: 'Lineup change affects BTTS confidence',
}

describe('NewsIntelligencePage', () => {
  it('renders articles with a real outbound source link, and impact scores correlated to a headline', async () => {
    vi.mocked(intelligenceApi.searchNews).mockResolvedValue([ARTICLE])
    vi.mocked(intelligenceApi.impact).mockResolvedValue([IMPACT])
    vi.mocked(intelligenceApi.newsTimeline).mockResolvedValue([EVENT])

    renderWithProviders(<NewsIntelligencePage />)

    await waitFor(() => expect(screen.getByText('Chelsea reshuffles back line')).toBeInTheDocument())
    const link = screen.getByRole('link', { name: /Read original source/ })
    expect(link).toHaveAttribute('href', 'https://example.com/article')

    await waitFor(() => expect(screen.getByText('Chelsea defender cleared to start')).toBeInTheDocument())
    expect(screen.getByText('0.42')).toBeInTheDocument()
  })

  it('falls back to an entity-based label when no timeline event matches the impact score', async () => {
    vi.mocked(intelligenceApi.searchNews).mockResolvedValue([])
    vi.mocked(intelligenceApi.impact).mockResolvedValue([IMPACT])
    vi.mocked(intelligenceApi.newsTimeline).mockResolvedValue([])

    renderWithProviders(<NewsIntelligencePage />)

    await waitFor(() => expect(screen.getByText('Event affecting team:chelsea')).toBeInTheDocument())
  })
})

describe('LearningIntelligencePage', () => {
  it('renders the real pipeline and the monitoring summary as a key-value grid', async () => {
    vi.mocked(predictionsApi.monitoringSummary).mockResolvedValue({ total_predictions: 128, avg_confidence: 0.712 })
    useAuthStore.setState({ profile: { id: 'u1', email: 'a@b.com', role: 'free', status: 'active', email_verified: true, created_at: '', last_login_at: null } })

    renderWithProviders(<LearningIntelligencePage />)

    expect(screen.getByText('Retraining Queue')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('128')).toBeInTheDocument())
    expect(screen.getByText(/restricted to administrator accounts/)).toBeInTheDocument()
  })

  it('shows the Operations Center link for administrator roles instead of the restriction note', async () => {
    vi.mocked(predictionsApi.monitoringSummary).mockResolvedValue({})
    useAuthStore.setState({ profile: { id: 'u2', email: 'admin@b.com', role: 'administrator', status: 'active', email_verified: true, created_at: '', last_login_at: null } })

    renderWithProviders(<LearningIntelligencePage />)

    expect(await screen.findByRole('link', { name: 'Operations Center' })).toBeInTheDocument()
  })
})
