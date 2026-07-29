import { describe, expect, it } from 'vitest'
import { SPORT_OPTIONS } from '@/lib/api/sports'

describe('SPORT_OPTIONS', () => {
  it('covers all four supported sports', () => {
    expect(SPORT_OPTIONS.map((s) => s.code)).toEqual(['football', 'basketball', 'baseball', 'table_tennis'])
  })

  it('gives every sport a human-readable label', () => {
    for (const sport of SPORT_OPTIONS) {
      expect(sport.label.length).toBeGreaterThan(0)
    }
  })
})
