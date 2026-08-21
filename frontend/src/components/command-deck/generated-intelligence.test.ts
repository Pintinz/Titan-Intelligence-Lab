import { describe, expect, it } from 'vitest'
import { formatApproximateGoals, parseScoreGrid } from './generated-intelligence'

describe('formatApproximateGoals', () => {
  it('rounds the real modeled rate to a whole number, marked as an approximation', () => {
    expect(formatApproximateGoals(1.7)).toBe('≈2')
    expect(formatApproximateGoals(1.2)).toBe('≈1')
    expect(formatApproximateGoals(2.9)).toBe('≈3')
  })

  it('rounds down when the fractional part is under one half', () => {
    expect(formatApproximateGoals(0.49)).toBe('≈0')
  })
})

describe('parseScoreGrid', () => {
  it('detects a real 6x6 correct-score grid and reports its real bounds', () => {
    const distribution: Record<string, number> = { OTHER: 0.02 }
    for (let h = 0; h <= 5; h++) {
      for (let a = 0; a <= 5; a++) distribution[`${h}-${a}`] = 0.01
    }

    const grid = parseScoreGrid(distribution)

    expect(grid).toEqual({ homeMax: 5, awayMax: 5, otherMass: 0.02 })
  })

  it('returns null for a non-score-shaped distribution (e.g. Match Winner)', () => {
    const grid = parseScoreGrid({ HOME_WIN: 0.5, DRAW: 0.3, AWAY_WIN: 0.2 })

    expect(grid).toBeNull()
  })

  it('returns null for a binary market whose value coincidentally looks score-like', () => {
    // A single "2-1"-shaped key with no siblings isn't a real matrix — must not be misread as one.
    const grid = parseScoreGrid({ 'OVER': 0.6, 'UNDER': 0.4 })

    expect(grid).toBeNull()
  })

  it('reports zero OTHER mass honestly when the field is absent, never fabricating a remainder', () => {
    const distribution: Record<string, number> = {}
    for (let h = 0; h <= 2; h++) {
      for (let a = 0; a <= 2; a++) distribution[`${h}-${a}`] = 1 / 9
    }

    const grid = parseScoreGrid(distribution)

    expect(grid?.otherMass).toBe(0)
  })
})
