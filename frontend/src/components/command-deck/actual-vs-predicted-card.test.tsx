import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ActualVsPredictedCard } from './actual-vs-predicted-card'
import type { FixtureSummaryDto, MarketReviewDto } from '@/lib/api/types'

const homeTeam = { name: 'Manchester United', logoUrl: null }
const awayTeam = { name: 'Fulham', logoUrl: null }

function fixture(overrides: Partial<FixtureSummaryDto> = {}): FixtureSummaryDto {
  return {
    id: 'fixture-1',
    season_id: 's1',
    sport_code: 'football',
    competition_id: 'comp-1',
    competition_name: 'Premier League',
    competition_logo_url: null,
    home_team: { id: 'home-1', name: homeTeam.name, short_name: 'MUN', logo_url: null },
    away_team: { id: 'away-1', name: awayTeam.name, short_name: 'FUL', logo_url: null },
    venue_name: null,
    scheduled_at: '2026-08-30T15:30:00Z',
    status: 'scheduled',
    final_state: null,
    ...overrides,
  } as FixtureSummaryDto
}

function market(overrides: Partial<MarketReviewDto> = {}): MarketReviewDto {
  return {
    market_id: 'mw-market',
    market_key: 'football.match_winner',
    market_name: 'Match Winner',
    predicted_value: 'HOME_WIN',
    probability: 0.72,
    confidence: 0.6,
    probability_distribution: { HOME_WIN: 0.72, DRAW: 0.18, AWAY_WIN: 0.1 },
    top_positive_features: [],
    top_negative_features: [],
    ai_explanation: null,
    generated_at: new Date().toISOString(),
    actual_value: null,
    is_correct: null,
    evaluated_at: null,
    ...overrides,
  }
}

describe('ActualVsPredictedCard', () => {
  it('shows "no prediction available" honestly when TitanIQ never generated one — never fabricates a comparison', () => {
    render(<ActualVsPredictedCard fixture={fixture()} market={undefined} homeTeam={homeTeam} awayTeam={awayTeam} />)
    expect(screen.getByText('No prediction available')).toBeInTheDocument()
  })

  it('shows the upcoming prediction without an actual result when the match has not been completed', () => {
    render(<ActualVsPredictedCard fixture={fixture({ status: 'scheduled' })} market={market()} homeTeam={homeTeam} awayTeam={awayTeam} />)
    expect(screen.getByText('Match has not been completed.')).toBeInTheDocument()
    expect(screen.getByText('Manchester United')).toBeInTheDocument()
    expect(screen.queryByText('Actually happened')).not.toBeInTheDocument()
  })

  it('shows the live state with the prediction locked and no final evaluation', () => {
    render(
      <ActualVsPredictedCard
        fixture={fixture({ status: 'live', final_state: { home: 1, away: 0 } })}
        market={market()}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )
    expect(screen.getByText('Live')).toBeInTheDocument()
    expect(screen.getByText(/Manchester United 1 – 0 Fulham/)).toBeInTheDocument()
    expect(screen.getByText(/Final evaluation pending/)).toBeInTheDocument()
  })

  it('shows "final result pending" honestly for a completed fixture with no verified score yet — never fabricates a score', () => {
    render(
      <ActualVsPredictedCard fixture={fixture({ status: 'completed', final_state: null })} market={market()} homeTeam={homeTeam} awayTeam={awayTeam} />,
    )
    expect(screen.getByText('Final result pending')).toBeInTheDocument()
  })

  it('shows the correct actual-vs-predicted comparison for a resolved, correct winner prediction', () => {
    render(
      <ActualVsPredictedCard
        fixture={fixture({ status: 'completed', final_state: { home: 2, away: 1 } })}
        market={market({ actual_value: 'HOME_WIN', is_correct: true, ai_explanation: 'Home form and attacking output carried the day.' })}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )
    expect(screen.getByText('Correct')).toBeInTheDocument()
    expect(screen.getByText(/Manchester United 2 – 1 Fulham/)).toBeInTheDocument()
    expect(screen.getByText('Why TitanIQ was right')).toBeInTheDocument()
  })

  it('shows an incorrect winner prediction honestly, never masking a miss', () => {
    render(
      <ActualVsPredictedCard
        fixture={fixture({ status: 'completed', final_state: { home: 0, away: 1 } })}
        market={market({ predicted_value: 'HOME_WIN', actual_value: 'AWAY_WIN', is_correct: false, ai_explanation: 'The upset went the other way.' })}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )
    expect(screen.getByText('Missed')).toBeInTheDocument()
    expect(screen.getByText('Why TitanIQ was wrong')).toBeInTheDocument()
  })

  it('shows "awaiting resolution" rather than a fabricated correct/incorrect verdict when the market has no resolver result yet', () => {
    render(
      <ActualVsPredictedCard
        fixture={fixture({ status: 'completed', final_state: { home: 2, away: 1 } })}
        market={market({ actual_value: null, is_correct: null })}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />,
    )
    expect(screen.getByText('Awaiting resolution')).toBeInTheDocument()
    expect(screen.queryByText('Correct')).not.toBeInTheDocument()
    expect(screen.queryByText('Missed')).not.toBeInTheDocument()
  })
})
