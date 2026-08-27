import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HeroIntelligenceReport, VerifiedIntelligenceReport, EngineIdleState } from './intelligence-card'
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
    home_score: null,
    away_score: null,
    outcome: null,
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

  describe('a completed fixture (rare hero fallback)', () => {
    // Featured Intelligence is forecast-only now — a completed pick only ever reaches the hero
    // when nothing live/upcoming is available at all (landing-page.tsx's own fallback), and even
    // then it renders exactly like any other forecast, never the "Verified Outcome" treatment.
    // That comparison view now lives exclusively in the "Verified Intelligence" section
    // (VerifiedIntelligenceReport, tested below).
    it('still shows the normal forecast, never a verified-outcome comparison', () => {
      renderHero(
        pick({ status: 'completed', home_score: 2, away_score: 0, outcome: { actual_value: 'HOME_WIN', is_correct: true } }),
      )
      expect(screen.getByText("Today's Top Forecast")).toBeInTheDocument()
      expect(screen.getByText('43%')).toBeInTheDocument()
      expect(screen.queryByText('Verified Outcome')).not.toBeInTheDocument()
      expect(screen.queryByText('Correct')).not.toBeInTheDocument()
      expect(screen.queryByText('Predicted')).not.toBeInTheDocument()
    })

    it('still shows the real final score on the status line', () => {
      renderHero(pick({ status: 'completed', home_score: 2, away_score: 0 }))
      expect(screen.getByText('FINAL · 2–0')).toBeInTheDocument()
    })
  })

  it('flags a stale prediction instead of implying it is fresh', () => {
    const staleTime = new Date(Date.now() - 24 * 3_600_000).toISOString()
    renderHero(pick({ generated_at: staleTime }))
    expect(screen.getByText('1d ago')).toBeInTheDocument()
  })
})

function renderVerified(dto: PublicFeaturedIntelligenceDto) {
  return render(
    <MemoryRouter>
      <VerifiedIntelligenceReport pick={dto} />
    </MemoryRouter>,
  )
}

describe('VerifiedIntelligenceReport', () => {
  it('shows the real final score and predicted value', () => {
    renderVerified(
      pick({ status: 'completed', home_score: 2, away_score: 0, outcome: { actual_value: 'HOME_WIN', is_correct: true } }),
    )
    expect(screen.getByText('FINAL · 2–0')).toBeInTheDocument()
    expect(screen.getByText(/43%/)).toBeInTheDocument()
  })

  it('shows a real correct verdict when OutcomeResolutionService resolved this prediction as a match', () => {
    renderVerified(
      pick({ status: 'completed', home_score: 2, away_score: 0, outcome: { actual_value: 'HOME_WIN', is_correct: true } }),
    )
    expect(screen.getByText('Correct')).toBeInTheDocument()
    expect(screen.getByText('HOME_WIN')).toBeInTheDocument()
  })

  it('shows a real missed verdict when the prediction did not match', () => {
    renderVerified(
      pick({ status: 'completed', home_score: 2, away_score: 0, outcome: { actual_value: 'AWAY_WIN', is_correct: false } }),
    )
    expect(screen.getByText('Missed')).toBeInTheDocument()
  })

  it('never fabricates a verdict when the outcome has not been resolved yet', () => {
    renderVerified(pick({ status: 'completed', home_score: 2, away_score: 0, outcome: null }))
    expect(screen.getByText('Verifying')).toBeInTheDocument()
    expect(screen.getByText('Awaiting verified outcome')).toBeInTheDocument()
    expect(screen.queryByText('Correct')).not.toBeInTheDocument()
    expect(screen.queryByText('Missed')).not.toBeInTheDocument()
  })
})

describe('EngineIdleState', () => {
  it('handles missing prediction data honestly, never a fabricated forecast', () => {
    render(<EngineIdleState />)
    expect(screen.getByText('Awaiting published intelligence')).toBeInTheDocument()
  })
})
