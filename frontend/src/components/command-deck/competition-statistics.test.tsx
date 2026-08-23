import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CompetitionStatisticsSection } from './competition-statistics'
import type { FixtureSummaryDto } from '@/lib/api/types'

function completedFixture(homeScore: number, awayScore: number, id: string): FixtureSummaryDto {
  return {
    id,
    season_id: 'season-1',
    sport_code: 'football',
    competition_id: 'comp-1',
    competition_name: 'Premier League',
    competition_logo_url: null,
    home_team: { id: 'h', name: 'Home FC', short_name: 'HOM', logo_url: null },
    away_team: { id: 'a', name: 'Away FC', short_name: 'AWY', logo_url: null },
    venue_name: null,
    scheduled_at: '2026-01-01T15:00:00Z',
    status: 'completed',
    final_state: { home: homeScore, away: awayScore },
  } as FixtureSummaryDto
}

describe('CompetitionStatisticsSection', () => {
  it('never fabricates statistics when no completed fixture has a real recorded score', () => {
    render(<CompetitionStatisticsSection completedFixtures={[]} />)
    expect(screen.getByText('Statistics unavailable')).toBeInTheDocument()
    expect(screen.queryByText('Total goals')).not.toBeInTheDocument()
  })

  it('never fabricates statistics for a scheduled fixture with no final score', () => {
    const scheduled = { ...completedFixture(0, 0, 'x'), status: 'scheduled', final_state: null } as FixtureSummaryDto
    render(<CompetitionStatisticsSection completedFixtures={[scheduled]} />)
    expect(screen.getByText('Statistics unavailable')).toBeInTheDocument()
  })

  it('computes real, internally-consistent statistics from actual recorded scores only', () => {
    render(
      <CompetitionStatisticsSection
        completedFixtures={[completedFixture(2, 1, 'f1'), completedFixture(0, 0, 'f2'), completedFixture(1, 3, 'f3')]}
      />,
    )
    expect(screen.getByText('Based on 3 completed fixtures')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument() // total goals: 3+0+4
    expect(screen.getAllByText('33%').length).toBeGreaterThan(0) // 1 home win of 3, evenly split W/D/L
  })
})
