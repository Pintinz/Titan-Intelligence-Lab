import { describe, expect, it } from 'vitest'
import { buildMatchSnapshot } from './match-snapshot'

describe('buildMatchSnapshot', () => {
  it('derives result and clean sheet purely from real scores when no stats were synced', () => {
    const snapshot = buildMatchSnapshot({
      teamName: 'Arsenal',
      perspectiveIsHome: true,
      homeScore: 3,
      awayScore: 0,
    })

    expect(snapshot.result).toBe('win')
    expect(snapshot.stats).toEqual([
      { key: 'goals', label: 'Goals', value: '3' },
      { key: 'btts', label: 'BTTS', value: 'No' },
      { key: 'clean_sheet', label: 'Clean Sheet', value: 'Yes' },
    ])
    expect(snapshot.summary).toBe('Arsenal secured the win, kept a clean sheet, limiting the opponent to nothing.')
  })

  it('reads result from the away perspective when the team was away in this past match', () => {
    const snapshot = buildMatchSnapshot({
      teamName: 'Chelsea',
      perspectiveIsHome: false,
      homeScore: 2,
      awayScore: 1,
    })

    expect(snapshot.result).toBe('loss')
    expect(snapshot.summary).toBe('Chelsea came away with a loss, both sides found the net.')
  })

  it('only includes chips for stats that were actually recorded for this match', () => {
    const snapshot = buildMatchSnapshot({
      teamName: 'Fulham',
      perspectiveIsHome: true,
      homeScore: 1,
      awayScore: 1,
      perspectiveStats: { corners: 9 },
    })

    expect(snapshot.stats.map((s) => s.key)).toEqual(['goals', 'btts', 'corners', 'clean_sheet'])
    expect(snapshot.summary).toContain('sustained attacking pressure throughout')
  })

  it('never mentions a stat threshold that was not met', () => {
    const snapshot = buildMatchSnapshot({
      teamName: 'Fulham',
      perspectiveIsHome: true,
      homeScore: 1,
      awayScore: 1,
      perspectiveStats: { corners: 3 },
    })

    expect(snapshot.summary).not.toContain('attacking pressure')
  })

  it('credits defensive control from the opponent low-shots-on-target stat, not the perspective side', () => {
    const snapshot = buildMatchSnapshot({
      teamName: 'Manchester City',
      perspectiveIsHome: true,
      homeScore: 2,
      awayScore: 0,
      opponentStats: { shots_on_target: 1 },
    })

    expect(snapshot.summary).toContain('held the opponent to almost nothing on target')
  })

  it('mentions possession control only above the real 55% threshold', () => {
    const below = buildMatchSnapshot({
      teamName: 'Fulham', perspectiveIsHome: true, homeScore: 0, awayScore: 0,
      perspectiveStats: { possession_pct: 54 },
    })
    const above = buildMatchSnapshot({
      teamName: 'Fulham', perspectiveIsHome: true, homeScore: 0, awayScore: 0,
      perspectiveStats: { possession_pct: 61 },
    })

    expect(below.summary).not.toContain('possession')
    expect(above.summary).toContain('controlled the tempo with 61% possession')
  })

  it('sums yellow and red cards into a single real chip only when at least one was recorded', () => {
    const snapshot = buildMatchSnapshot({
      teamName: 'Fulham', perspectiveIsHome: true, homeScore: 1, awayScore: 0,
      perspectiveStats: { cards_yellow: 2, cards_red: 1 },
    })

    expect(snapshot.stats.find((s) => s.key === 'cards')).toEqual({ key: 'cards', label: 'Cards', value: '3' })
  })
})
