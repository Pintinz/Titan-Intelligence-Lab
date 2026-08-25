import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HeroIntelligenceReport, EngineIdleState } from './intelligence-card'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

// The hero count-up animates via requestAnimationFrame; jsdom never fires real frames, so use
// vitest's fake-timer rAF support (scoped to this file, restored after each test) to drive it to
// its finished value instead of asserting mid-animation state.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['requestAnimationFrame'] })
})

afterEach(() => {
  vi.useRealTimers()
})

function pick(overrides: Partial<PublicFeaturedIntelligenceDto> = {}): PublicFeaturedIntelligenceDto {
  return {
    prediction_id: 'pred-1',
    fixture_id: 'fixture-1',
    sport_code: 'football',
    competition_name: 'Premier League',
    home_team: { name: 'Hull City AFC', short_name: 'HUL', logo_url: null },
    away_team: { name: 'Manchester United', short_name: 'MUN', logo_url: null },
    scheduled_at: '2026-08-22T11:30:00Z',
    status: 'scheduled',
    market_name: 'Match Winner',
    market_key: 'football.match_winner',
    value: 'HOME_WIN',
    probability: 0.43,
    probability_distribution: {},
    confidence_composite: 0.6,
    evidence_highlights: { supporting: ['football.form_fouls_diff_last5'], contradicting: [] },
    generated_at: new Date().toISOString(),
    ...overrides,
  }
}

function renderHero(dto: PublicFeaturedIntelligenceDto) {
  const result = render(
    <MemoryRouter>
      <HeroIntelligenceReport pick={dto} />
    </MemoryRouter>,
  )
  // Let the count-up animation finish before asserting on the settled values.
  act(() => {
    vi.advanceTimersByTime(1000)
  })
  return result
}

describe('HeroIntelligenceReport', () => {
  it('renders the forecast', () => {
    renderHero(pick())
    expect(screen.getAllByText('Hull City AFC').length).toBeGreaterThan(0)
    expect(screen.getByText('Manchester United')).toBeInTheDocument()
    expect(screen.getByText('43%')).toBeInTheDocument()
  })

  it('shows the probability distribution as an honest two-way split, never a fabricated three-way breakdown', () => {
    renderHero(pick({ probability: 0.43 }))
    expect(screen.getByText(/Hull City AFC · 43%/)).toBeInTheDocument()
    expect(screen.getByText(/Other outcomes · 57%/)).toBeInTheDocument()
    expect(screen.queryByText(/draw/i)).not.toBeInTheDocument()
  })

  it('shows a real three-way Home/Draw/Away breakdown when the backend provides one', () => {
    renderHero(
      pick({
        probability_distribution: { HOME_WIN: 0.43, DRAW: 0.31, AWAY_WIN: 0.26 },
      }),
    )
    expect(screen.getByText('31%')).toBeInTheDocument()
    expect(screen.getByText('26%')).toBeInTheDocument()
    expect(screen.getByText('Draw')).toBeInTheDocument()
    // The two-way fallback text must not also render alongside the real breakdown.
    expect(screen.queryByText(/Other outcomes/)).not.toBeInTheDocument()
  })

  it('displays confidence separately from probability', () => {
    renderHero(pick({ confidence_composite: 0.6 }))
    expect(screen.getByText('60%')).toBeInTheDocument()
  })

  it('shows the real market instead of a fabricated model status', () => {
    renderHero(pick({ market_name: 'Both Teams To Score' }))
    expect(screen.getByText('Both Teams To Score')).toBeInTheDocument()
    expect(screen.queryByText(/champion/i)).not.toBeInTheDocument()
  })

  it('flags a stale prediction instead of implying it is fresh', () => {
    const staleTime = new Date(Date.now() - 24 * 3_600_000).toISOString()
    renderHero(pick({ generated_at: staleTime }))
    expect(screen.getByText('1d ago')).toBeInTheDocument()
  })
})

describe('EngineIdleState', () => {
  it('handles missing prediction data honestly, never a fabricated forecast', () => {
    render(<EngineIdleState />)
    expect(screen.getByText('Awaiting published intelligence')).toBeInTheDocument()
  })
})
