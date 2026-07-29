import { describe, expect, it } from 'vitest'
import { isAtLeast, ROLE_LEVEL } from '@/lib/api/types'

describe('ROLE_LEVEL ladder', () => {
  it('is strictly increasing in the documented order', () => {
    const order = [
      'guest',
      'free',
      'rewarded',
      'premium',
      'moderator',
      'analyst',
      'administrator',
      'super_administrator',
    ] as const
    for (let i = 1; i < order.length; i++) {
      expect(ROLE_LEVEL[order[i]]).toBeGreaterThan(ROLE_LEVEL[order[i - 1]])
    }
  })
})

describe('isAtLeast', () => {
  it('is true when the role is above the minimum', () => {
    expect(isAtLeast('administrator', 'analyst')).toBe(true)
  })

  it('is true when the role equals the minimum', () => {
    expect(isAtLeast('analyst', 'analyst')).toBe(true)
  })

  it('is false when the role is below the minimum', () => {
    expect(isAtLeast('free', 'administrator')).toBe(false)
  })
})
